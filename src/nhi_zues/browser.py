from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from .discord_text import clean_discord_display_name
from .models import MessageRecord
from .selectors import TEXTBOX


class DiscordWebSession:
    def __init__(self, profile_dir: Path, *, browser_channel: str | None, headless: bool) -> None:
        self.profile_dir = profile_dir
        self.browser_channel = browser_channel
        self.headless = headless
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "DiscordWebSession":
        profile_dir = self.profile_dir.resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        args = ["--disable-blink-features=AutomationControlled"]
        launch_headless = self.headless
        if self.headless:
            # Discord does not reliably reuse the signed-in profile in true headless mode.
            # Use an off-screen headful window for silent automation instead.
            launch_headless = False
            args.extend(["--window-position=-32000,-32000", "--window-size=1440,1000"])
        else:
            # Manual login/open-channel flows must override any off-screen bounds saved
            # by the same persistent Chrome profile during silent automation.
            args.extend(["--window-position=80,80", "--window-size=1440,1000"])
        try:
            self._context = await self._launch_context(profile_dir, launch_headless, args)
        except Exception as exc:
            if not _profile_in_use_error(exc):
                raise
            _close_profile_browsers(profile_dir)
            await asyncio.sleep(1.0)
            self._context = await self._launch_context(profile_dir, launch_headless, args)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        return self

    async def _launch_context(
        self,
        profile_dir: Path,
        launch_headless: bool,
        args: list[str],
    ) -> BrowserContext:
        return await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=self.browser_channel,
            headless=launch_headless,
            viewport={"width": 1440, "height": 1000},
            args=args,
        )

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser session is not started.")
        return self._page

    async def is_logged_in(self) -> bool:
        return await self._is_logged_in()

    async def current_user_id(self) -> str | None:
        try:
            value = await self.page.evaluate(
                """
                () => {
                    const userSettings = document.querySelector('[aria-label="User Settings"]')
                        || Array.from(document.querySelectorAll('[aria-label]'))
                            .find((node) => /user settings/i.test(node.getAttribute("aria-label") || ""));
                    const roots = [];
                    let node = userSettings;
                    for (let index = 0; node && index < 8; index += 1) {
                        roots.push(node);
                        node = node.parentElement;
                    }
                    roots.push(document.querySelector('[class*="panels"]'));
                    for (const root of roots.filter(Boolean)) {
                        const avatar = root.querySelector('img[src*="/avatars/"]');
                        const match = avatar?.src?.match(/\\/avatars\\/(\\d+)\\//);
                        if (match) return match[1];
                    }
                    return null;
                }
                """
            )
        except Exception:
            return None
        return str(value).strip() if value else None

    async def show_for_human(self) -> None:
        await self._set_window_bounds(left=80, top=80, width=1440, height=1000)

    async def hide_for_automation(self) -> None:
        await self._set_window_bounds(left=-32000, top=-32000, width=1440, height=1000)

    async def _set_window_bounds(self, *, left: int, top: int, width: int, height: int) -> None:
        if self._context is None:
            return
        cdp = None
        try:
            cdp = await self._context.new_cdp_session(self.page)
            info = await cdp.send("Browser.getWindowForTarget")
            window_id = info.get("windowId")
            if window_id is None:
                return
            await cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height,
                        "windowState": "normal",
                    },
                },
            )
        except Exception:
            return
        finally:
            if cdp is not None:
                try:
                    await cdp.detach()
                except Exception:
                    pass

    async def open_home(self) -> None:
        await self.page.goto("https://discord.com/channels/@me", wait_until="domcontentloaded")
        await self.page.wait_for_timeout(1500)

    async def discover_servers(self) -> list[dict[str, str]]:
        await self.open_home()
        try:
            await self.page.wait_for_function(
                """
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href*="/channels/"]'));
                    const treeItems = Array.from(
                        document.querySelectorAll('[data-list-item-id^="guildsnav___"]')
                    );
                    return anchors.some((node) => /\\/channels\\/\\d{5,}/.test(node.getAttribute("href") || ""))
                        || treeItems.some((node) => /guildsnav___\\d{5,}/.test(node.getAttribute("data-list-item-id") || ""));
                }
                """,
                timeout=15_000,
            )
        except Exception:
            await self.page.wait_for_timeout(1500)

        await self._reset_guild_nav_scroll()
        seen: dict[str, dict[str, str]] = {}
        last_count = -1
        stable_bottom_rounds = 0
        for _ in range(60):
            for row in await self._visible_server_rows():
                seen[row["server_id"]] = row

            at_bottom = await self._scroll_guild_nav()
            if at_bottom and len(seen) == last_count:
                stable_bottom_rounds += 1
            else:
                stable_bottom_rounds = 0
            last_count = len(seen)
            if at_bottom and stable_bottom_rounds >= 2:
                break

        return list(seen.values())

    async def _visible_server_rows(self) -> list[dict[str, str]]:
        rows = await self.page.evaluate(
            """
            () => {
                const guildNav = document.querySelector('[data-list-id="guildsnav"]');
                const seen = new Map();
                const cleanLabel = (value) => String(value || "")
                    .replace(/^\\s*unread messages?,\\s*/i, "")
                    .replace(/^\\s*\\d+\\s+mentions?,\\s*/i, "")
                    .replace(/^\\s*\\d+\\s+unread messages?,\\s*/i, "")
                    .replace(/,?\\s*\\d+\\s+unread messages?.*$/i, "")
                    .replace(/,?\\s*unread.*$/i, "")
                    .trim();
                const remember = (serverId, label, iconUrl = "") => {
                    if (seen.has(serverId)) return;
                    seen.set(serverId, { server_id: serverId, label: cleanLabel(label), icon_url: iconUrl || "" });
                };

                const anchors = Array.from(
                    (guildNav || document).querySelectorAll('a[href*="/channels/"]')
                );
                for (const anchor of anchors) {
                    const href = anchor.getAttribute("href") || "";
                    const match = href.match(/\\/channels\\/(\\d{5,})/);
                    if (!match) continue;
                    const serverId = match[1];
                    const labelledNode = anchor.querySelector("[aria-label], [title]");
                    const rawLabel =
                        anchor.getAttribute("aria-label") ||
                        anchor.getAttribute("title") ||
                        labelledNode?.getAttribute("aria-label") ||
                        labelledNode?.getAttribute("title") ||
                        anchor.textContent ||
                        "";
                    const iconUrl = anchor.querySelector("img[src]")?.getAttribute("src") || "";
                    remember(serverId, rawLabel, iconUrl);
                }

                const treeItems = Array.from(
                    (guildNav || document).querySelectorAll('[data-list-item-id^="guildsnav___"]')
                );
                for (const item of treeItems) {
                    const marker = item.getAttribute("data-list-item-id") || "";
                    const match = marker.match(/^guildsnav___(\\d{5,})$/);
                    if (!match) continue;
                    const labelNode = item.querySelector('[data-dnd-name]');
                    const rawLabel =
                        labelNode?.getAttribute("data-dnd-name") ||
                        item.getAttribute("aria-label") ||
                        item.getAttribute("title") ||
                        item.textContent ||
                        "";
                    const iconUrl = item.querySelector("img[src]")?.getAttribute("src") || "";
                    remember(match[1], rawLabel, iconUrl);
                }
                return Array.from(seen.values());
            }
            """
        )
        return [
            {
                "server_id": str(row["server_id"]),
                "label": str(row.get("label") or ""),
                "icon_url": str(row.get("icon_url") or ""),
            }
            for row in rows
            if row.get("server_id")
        ]

    async def _scroll_guild_nav(self) -> bool:
        return bool(
            await self.page.evaluate(
                """
                () => {
                    const firstServer = document.querySelector('[data-list-item-id^="guildsnav___"]');
                    const guildNav = document.querySelector('[data-list-id="guildsnav"]');
                    const starts = [guildNav, firstServer?.parentElement].filter(Boolean);
                    let scroller = null;
                    for (const start of starts) {
                        let cursor = start;
                        while (cursor && cursor !== document.body) {
                            if (cursor.scrollHeight > cursor.clientHeight + 20) {
                                scroller = cursor;
                                break;
                            }
                            cursor = cursor.parentElement;
                        }
                        if (scroller) break;
                    }
                    if (!scroller) return true;
                    const before = scroller.scrollTop;
                    scroller.scrollTop = Math.min(
                        scroller.scrollTop + Math.max(scroller.clientHeight * 0.85, 420),
                        scroller.scrollHeight
                    );
                    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
                    const atBottom = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4;
                    return atBottom || scroller.scrollTop === before;
                }
                """
            )
        )

    async def _reset_guild_nav_scroll(self) -> None:
        await self.page.evaluate(
            """
            () => {
                const firstServer = document.querySelector('[data-list-item-id^="guildsnav___"]');
                const guildNav = document.querySelector('[data-list-id="guildsnav"]');
                const starts = [guildNav, firstServer?.parentElement].filter(Boolean);
                for (const start of starts) {
                    let cursor = start;
                    while (cursor && cursor !== document.body) {
                        if (cursor.scrollHeight > cursor.clientHeight + 20) {
                            cursor.scrollTop = 0;
                            cursor.dispatchEvent(new Event("scroll", { bubbles: true }));
                            return;
                        }
                        cursor = cursor.parentElement;
                    }
                }
            }
            """
        )

    async def discover_channels(self, server_id: str) -> list[dict[str, str]]:
        await self._open_server(server_id)
        try:
            await self.page.wait_for_function(
                """
                (serverId) => Array.from(
                    document.querySelectorAll('[data-list-item-id^="channels___"]')
                ).some((node) => {
                    const marker = node.getAttribute("data-list-item-id") || "";
                    const href = node.getAttribute("href") || "";
                    return /^channels___\\d{5,}$/.test(marker)
                        && (href.includes(`/channels/${serverId}/`) || node.getAttribute("aria-label"));
                })
                """,
                server_id,
                timeout=18_000,
            )
        except Exception:
            await self.page.wait_for_timeout(1500)

        await self._expand_channel_categories()
        await self._reset_channel_sidebar_scroll()
        seen: dict[str, dict[str, str]] = {}
        last_count = -1
        stable_bottom_rounds = 0
        for _ in range(40):
            rows = await self._visible_channel_rows(server_id)
            for row in rows:
                seen[row["channel_id"]] = row

            at_bottom = await self._scroll_channel_sidebar()
            if at_bottom and len(seen) == last_count:
                stable_bottom_rounds += 1
            else:
                stable_bottom_rounds = 0
            last_count = len(seen)

            if at_bottom and stable_bottom_rounds >= 2:
                break

        for forum in [row for row in list(seen.values()) if row.get("channel_type") == "forum"][:20]:
            for thread in await self._discover_forum_threads(server_id, forum):
                seen[thread["channel_id"]] = thread

        return list(seen.values())

    async def _open_server(self, server_id: str) -> None:
        selector = f'[data-list-item-id="guildsnav___{server_id}"]'
        try:
            item = self.page.locator(selector).first
            if await item.count():
                await item.scroll_into_view_if_needed(timeout=5_000)
                await item.click(timeout=10_000)
            else:
                await self.page.goto(f"https://discord.com/channels/{server_id}", wait_until="domcontentloaded")
        except Exception:
            await self.page.goto(f"https://discord.com/channels/{server_id}", wait_until="domcontentloaded")

        try:
            await self.page.wait_for_function(
                "(serverId) => location.href.includes(`/channels/${serverId}`)",
                server_id,
                timeout=15_000,
            )
        except Exception:
            await self.page.wait_for_timeout(1500)

    async def _visible_channel_rows(self, server_id: str) -> list[dict[str, str]]:
        rows = await self.page.evaluate(
            """
            (serverId) => {
                const rows = [];
                const cleanLabel = (value) => String(value || "")
                    .replace(/^\\s*unread,\\s*/i, "")
                    .replace(/^\\s*unread messages?,\\s*/i, "")
                    .replace(/^\\s*\\d+\\s+mentions?,\\s*/i, "")
                    .replace(/^\\s*\\d+\\s+unread messages?,\\s*/i, "")
                    .replace(/\\s*\\((text|forum|voice|stage|announcement) channel\\)\\s*$/i, "")
                    .replace(/\\s*\\(voice chat\\)\\s*$/i, "")
                    .trim();
                const channelType = (value, text) => {
                    const raw = `${value || ""} ${text || ""}`.toLowerCase();
                    if (raw.includes("(announcement channel)") || raw.startsWith("announcement")) return "announcement";
                    if (raw.includes("(forum channel)") || raw.startsWith("forum")) return "forum";
                    if (raw.includes("(thread)") || raw.includes("thread channel")) return "thread";
                    if (raw.includes("(voice channel)") || raw.startsWith("voice")) return "voice";
                    if (raw.includes("(stage channel)") || raw.startsWith("stage")) return "stage";
                    return "text";
                };
                const categoryFor = (node) => {
                    let cursor = node;
                    while (cursor) {
                        cursor = cursor.previousElementSibling;
                        const category = cursor?.querySelector?.('[aria-label$="(category)"]');
                        const categoryLabel = category?.getAttribute("aria-label");
                        if (categoryLabel) {
                            return categoryLabel
                                .replace(/\\s*\\(category\\)\\s*$/i, "")
                                .replace(/^\\s*[-\\u2500]+\\s*/, "")
                                .trim();
                        }
                    }
                    return "";
                };
                const candidates = Array.from(
                    document.querySelectorAll('[data-list-item-id^="channels___"]')
                );
                for (const node of candidates) {
                    const marker = node.getAttribute("data-list-item-id") || "";
                    const markerMatch = marker.match(/^channels___(\\d{5,})$/);
                    if (!markerMatch) continue;
                    const href = node.getAttribute("href") || "";
                    const hrefMatch = href.match(new RegExp(`/channels/${serverId}/(\\\\d{5,})`));
                    const channelId = hrefMatch?.[1] || markerMatch[1];
                    const rawLabel = node.getAttribute("aria-label") || node.textContent || "";
                    const type = channelType(rawLabel, node.textContent || "");
                    const canScan = Boolean(hrefMatch) && (
                        type === "text" || type === "forum" || type === "announcement" || type === "thread"
                    );
                    if (!rawLabel || !canScan) continue;
                    rows.push({
                        channel_id: channelId,
                        label: cleanLabel(rawLabel),
                        channel_type: type,
                        category: categoryFor(node),
                        can_scan: String(canScan),
                    });
                }
                return rows;
            }
            """,
            server_id,
        )
        return [
            {
                "channel_id": str(row["channel_id"]),
                "label": str(row.get("label") or ""),
                "channel_type": str(row.get("channel_type") or "text"),
                "category": str(row.get("category") or ""),
                "can_scan": str(row.get("can_scan") or "false"),
            }
            for row in rows
            if row.get("channel_id") and row.get("label")
        ]

    async def _expand_channel_categories(self) -> None:
        try:
            await self.page.evaluate(
                """
                () => {
                    const firstChannel = document.querySelector('[data-list-item-id^="channels___"]');
                    let root = firstChannel?.parentElement || document.querySelector('[data-list-id="channels"]');
                    while (root && root !== document.body) {
                        if (root.scrollHeight > root.clientHeight + 20) break;
                        root = root.parentElement;
                    }
                    root = root || document;
                    const collapsed = Array.from(root.querySelectorAll('[aria-expanded="false"]')).filter((node) => {
                        const label = node.getAttribute("aria-label") || node.textContent || "";
                        return label && !/server|guild|user settings|direct messages/i.test(label);
                    });
                    for (const node of collapsed.slice(0, 80)) {
                        try { node.click(); } catch {}
                    }
                }
                """
            )
            await self.page.wait_for_timeout(700)
        except Exception:
            return

    async def _discover_forum_threads(self, server_id: str, forum: dict[str, str]) -> list[dict[str, str]]:
        parent_id = str(forum.get("channel_id") or "")
        if not parent_id:
            return []
        await self.navigate_channel(server_id, parent_id)
        await self._load_forum_posts()
        rows = await self.page.evaluate(
            """
            ({ serverId, parentId, parentLabel, category }) => {
                const cleanLabel = (value) => String(value || "")
                    .replace(/\\s+/g, " ")
                    .replace(/^#\\s*/, "")
                    .replace(/^(new|unread)\\s+/i, "")
                    .trim();
                const main =
                    document.querySelector('[role="main"]')
                    || document.querySelector('[class*="chatContent"]')
                    || document;
                const seen = new Map();
                for (const anchor of Array.from(main.querySelectorAll(`a[href*="/channels/${serverId}/"]`))) {
                    const href = anchor.getAttribute("href") || "";
                    const match = href.match(new RegExp(`/channels/${serverId}/(\\\\d{5,})`));
                    const threadId = match?.[1] || "";
                    if (!threadId || threadId === parentId || seen.has(threadId)) continue;
                    const rawLabel =
                        anchor.getAttribute("aria-label")
                        || anchor.querySelector('h3, [class*="title"], [class*="name"]')?.textContent
                        || anchor.textContent
                        || "";
                    const label = cleanLabel(rawLabel).split("\\n")[0].slice(0, 120).trim();
                    if (!label || /^\\d+$/.test(label)) continue;
                    seen.set(threadId, {
                        channel_id: threadId,
                        label,
                        channel_type: "thread",
                        category: parentLabel ? `${parentLabel} threads` : (category || "Forum threads"),
                        parent_channel_id: parentId,
                        can_scan: "true",
                    });
                }
                return Array.from(seen.values()).slice(0, 100);
            }
            """,
            {
                "serverId": server_id,
                "parentId": parent_id,
                "parentLabel": str(forum.get("label") or ""),
                "category": str(forum.get("category") or ""),
            },
        )
        return [
            {
                "channel_id": str(row["channel_id"]),
                "label": str(row.get("label") or ""),
                "channel_type": "thread",
                "category": str(row.get("category") or ""),
                "parent_channel_id": str(row.get("parent_channel_id") or parent_id),
                "can_scan": "true",
            }
            for row in rows
            if row.get("channel_id") and row.get("label")
        ]

    async def _load_forum_posts(self) -> None:
        last_count = -1
        stable_rounds = 0
        for _ in range(10):
            count = await self.page.evaluate(
                """
                () => {
                    const main =
                        document.querySelector('[role="main"]')
                        || document.querySelector('[class*="chatContent"]')
                        || document;
                    const anchors = main.querySelectorAll('a[href*="/channels/"]').length;
                    let scroller = main;
                    while (scroller && scroller !== document.body) {
                        if (scroller.scrollHeight > scroller.clientHeight + 20) break;
                        scroller = scroller.parentElement;
                    }
                    if (scroller && scroller !== document.body) {
                        scroller.scrollTop = Math.min(
                            scroller.scrollTop + Math.max(scroller.clientHeight * 0.9, 500),
                            scroller.scrollHeight
                        );
                        scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
                    } else {
                        window.scrollTo(0, document.body.scrollHeight);
                    }
                    return anchors;
                }
                """
            )
            if count == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_count = count
            if stable_rounds >= 2:
                break
            await self.page.wait_for_timeout(500)

    async def _scroll_channel_sidebar(self) -> bool:
        return bool(
            await self.page.evaluate(
                """
                () => {
                    const firstChannel = document.querySelector('[data-list-item-id^="channels___"]');
                    const channelList = document.querySelector('[data-list-id="channels"]');
                    const starts = [channelList, firstChannel?.parentElement].filter(Boolean);
                    let scroller = null;
                    for (const start of starts) {
                        let cursor = start;
                        while (cursor && cursor !== document.body) {
                            if (cursor.scrollHeight > cursor.clientHeight + 20) {
                                scroller = cursor;
                                break;
                            }
                            cursor = cursor.parentElement;
                        }
                        if (scroller) break;
                    }
                    if (!scroller || scroller === document.body) return true;
                    const before = scroller.scrollTop;
                    scroller.scrollTop = Math.min(
                        scroller.scrollTop + Math.max(scroller.clientHeight * 0.8, 400),
                        scroller.scrollHeight
                    );
                    const atBottom = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4;
                    return atBottom || scroller.scrollTop === before;
                }
                """
            )
        )

    async def _reset_channel_sidebar_scroll(self) -> None:
        await self.page.evaluate(
            """
            () => {
                const firstChannel = document.querySelector('[data-list-item-id^="channels___"]');
                const channelList = document.querySelector('[data-list-id="channels"]');
                const starts = [channelList, firstChannel?.parentElement].filter(Boolean);
                let scroller = null;
                for (const start of starts) {
                    let cursor = start;
                    while (cursor && cursor !== document.body) {
                        if (cursor.scrollHeight > cursor.clientHeight + 20) {
                            scroller = cursor;
                            break;
                        }
                        cursor = cursor.parentElement;
                    }
                    if (scroller) break;
                }
                if (scroller && scroller !== document.body) {
                    scroller.scrollTop = 0;
                    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
                }
            }
            """
        )

    async def login_if_needed(
        self,
        *,
        email: str | None = None,
        password: str | None = None,
        timeout_seconds: int = 180,
        allow_human_challenge: bool = True,
    ) -> bool:
        await self.open_home()
        if await self._is_logged_in():
            return True

        login_form = self.page.locator('input[name="email"], input[type="email"]').first
        if email and password:
            try:
                await login_form.wait_for(state="visible", timeout=15_000)
            except Exception:
                pass
        if await login_form.count() and email and password:
            await login_form.fill(email)
            password_input = self.page.locator('input[name="password"], input[type="password"]').first
            await password_input.wait_for(state="visible", timeout=15_000)
            await password_input.fill(password)
            await password_input.press("Enter")
            if not allow_human_challenge:
                await self.page.wait_for_timeout(2500)
                blocker = await self.account_blocker_state()
                if blocker.get("blocked"):
                    return False

        try:
            await self.page.wait_for_function(
                """
                () => {
                    const authenticatedShell = document.querySelector('[aria-label="User Settings"]')
                        || document.querySelector('[data-list-id="guildsnav"]');
                    return location.href.includes("/channels/")
                        && !location.href.includes("/login")
                        && !document.querySelector('input[name="email"], input[type="email"]')
                        && Boolean(authenticatedShell);
                }
                """,
                timeout=timeout_seconds * 1000,
            )
        except Exception:
            return await self._is_logged_in()
        return True

    async def login_blocker_state(self) -> dict[str, object]:
        return await self.page.evaluate(
            """
            () => {
                const visible = (node) => {
                    if (!node) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const bodyText = (document.body?.innerText || "").replace(/\\s+/g, " ").trim();
                const lowered = bodyText.toLowerCase();
                return {
                    url: location.href,
                    login_form_visible: Boolean(Array.from(
                        document.querySelectorAll('input[name="email"], input[type="email"]')
                    ).find(visible)),
                    human_verification: lowered.includes("are you human")
                        || lowered.includes("not a robot")
                        || lowered.includes("confirm you're not a robot")
                        || lowered.includes("confirm you’re not a robot"),
                    two_factor: lowered.includes("two-factor")
                        || lowered.includes("2fa")
                        || lowered.includes("authentication code"),
                    body_preview: bodyText.slice(0, 240),
                };
            }
            """
        )

    async def account_blocker_state(self) -> dict[str, object]:
        return await self.page.evaluate(
            """
            () => {
                const visible = (node) => {
                    if (!node) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const bodyText = (document.body?.innerText || "").replace(/\\s+/g, " ").trim();
                const lowered = bodyText.toLowerCase();
                const loginFormVisible = Boolean(Array.from(
                    document.querySelectorAll('input[name="email"], input[type="email"]')
                ).find(visible));
                const humanVerification = lowered.includes("are you human")
                    || lowered.includes("not a robot")
                    || lowered.includes("confirm you're not a robot")
                    || lowered.includes("confirm you are not a robot")
                    || lowered.includes("verify that you are human");
                const twoFactor = lowered.includes("two-factor")
                    || lowered.includes("2fa")
                    || lowered.includes("authentication code");
                const passwordReset = lowered.includes("reset your password")
                    || lowered.includes("change your password")
                    || lowered.includes("choose a new password")
                    || lowered.includes("new password");
                const accountActionRequired = lowered.includes("suspicious activity")
                    || lowered.includes("unusual activity")
                    || lowered.includes("something's going on here")
                    || lowered.includes("verify your account")
                    || lowered.includes("verify your identity")
                    || lowered.includes("phone verification")
                    || lowered.includes("verify by phone")
                    || lowered.includes("email verification");
                const loginUrl = location.href.includes("/login");
                const hasMessages = document.querySelectorAll('[id^="chat-messages-"]').length > 0;
                const hasComposer = Boolean(Array.from(document.querySelectorAll(
                    '[data-slate-editor="true"][role="textbox"], div[role="textbox"][contenteditable="true"]'
                )).find(visible));
                const securitySurface = loginUrl
                    || loginFormVisible
                    || !location.href.includes("/channels/")
                    || (!hasMessages && !hasComposer);
                const blocked = loginFormVisible
                    || loginUrl
                    || (securitySurface && (
                        humanVerification
                        || twoFactor
                        || passwordReset
                        || accountActionRequired
                    ));
                return {
                    url: location.href,
                    login_form_visible: loginFormVisible,
                    login_url: loginUrl,
                    human_verification: humanVerification,
                    two_factor: twoFactor,
                    password_reset: passwordReset,
                    account_action_required: accountActionRequired,
                    blocked,
                    body_preview: bodyText.slice(0, 240),
                };
            }
            """
        )

    async def navigate_channel(self, server_id: str, channel_id: str, *, message_id: str = "") -> str:
        message_token = _discord_message_token(message_id)
        target_url = f"https://discord.com/channels/{server_id}/{channel_id}"
        if message_token:
            target_url = f"{target_url}/{message_token}"
        await self.page.goto(
            target_url,
            wait_until="commit",
        )
        try:
            await self.page.wait_for_function(
                """
                (channelId) => {
                    const inTarget = location.href.includes(channelId);
                    const redirectedHome = location.href.includes("/channels/@me");
                    const hasRows = document.querySelectorAll('[id^="chat-messages-"]').length > 0;
                    const hasComposer = Boolean(document.querySelector(
                        '[data-slate-editor="true"][role="textbox"], div[role="textbox"][contenteditable="true"]'
                    ));
                    return (inTarget && (hasRows || hasComposer)) || (!inTarget && redirectedHome);
                }
                """,
                channel_id,
                timeout=18_000,
            )
        except Exception:
            try:
                await self.page.locator('[role="textbox"]').last.wait_for(state="visible", timeout=5_000)
            except Exception:
                await self.page.wait_for_timeout(1500)
        return self.page.url

    async def writable_channel_state(self) -> dict[str, object]:
        return await self.page.evaluate(
            """
            () => {
                const visible = (node) => {
                    if (!node) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const composer = Array.from(document.querySelectorAll(
                    '[data-slate-editor="true"][role="textbox"], div[role="textbox"][contenteditable="true"]'
                )).find(visible);
                const bodyText = (document.body?.innerText || "").replace(/\\s+/g, " ").trim();
                const lowered = bodyText.toLowerCase();
                const notices = [
                    "you do not have permission to send messages in this channel",
                    "sending messages in this channel has been disabled",
                    "you must complete a few more steps before you can talk",
                    "you do not have access to this channel",
                    "this channel is read only",
                    "this is a read-only channel",
                    "follow channel"
                ];
                const notice = notices.find((term) => lowered.includes(term)) || "";
                const titleNode =
                    document.querySelector('section[aria-label*="Channel header"] h1')
                    || document.querySelector('[class*="title"] h1')
                    || document.querySelector('[aria-label$="(channel)"]');
                return {
                    url: location.href,
                    title: (titleNode?.textContent || document.title || "").trim(),
                    has_composer: Boolean(composer),
                    has_messages: document.querySelectorAll('[id^="chat-messages-"]').length > 0,
                    notice,
                };
            }
            """
        )

    async def wait_for_writable_channel(self, *, timeout_ms: int = 15_000) -> dict[str, object]:
        try:
            await self.page.wait_for_function(
                """
                () => {
                    const visible = (node) => {
                        if (!node) return false;
                        const rect = node.getBoundingClientRect();
                        const style = window.getComputedStyle(node);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== "none"
                            && style.visibility !== "hidden";
                    };
                    return Array.from(document.querySelectorAll(
                        '[data-slate-editor="true"][role="textbox"], div[role="textbox"][contenteditable="true"]'
                    )).some(visible);
                }
                """,
                timeout=timeout_ms,
            )
        except Exception:
            pass

        state = await self.writable_channel_state()
        if state.get("has_composer"):
            return state

        url = str(state.get("url") or "")
        notice = str(state.get("notice") or "")
        if "/channels/@me" in url:
            raise RuntimeError("Discord redirected away from the target channel. The draft was not sent and remains queued.")
        if notice:
            raise RuntimeError(f"Discord is blocking sends here: {notice}. The draft was not sent and remains queued.")
        if state.get("has_messages"):
            raise RuntimeError(
                "Discord loaded the channel messages but no writable message composer is visible. "
                "This usually means the channel is read-only, the account lacks send permission, "
                "or Discord is showing a gate/notice. The draft was not sent and remains queued."
            )
        raise RuntimeError(
            "Discord did not finish loading a writable message composer for this channel. "
            "The draft was not sent and remains queued."
        )

    async def read_visible_messages(self, server_id: str, channel_id: str) -> list[MessageRecord]:
        await self.ensure_latest_messages_visible()
        return await self._read_message_records_from_dom(server_id, channel_id)

    async def message_dom_diagnostics(self) -> dict[str, object]:
        return await self.page.evaluate(
            """
            () => {
                const rawNodes = Array.from(document.querySelectorAll('[id^="chat-messages-"]'));
                const validNodes = rawNodes.filter((node) => /^chat-messages-\\d{5,}-\\d{5,}$/.test(node.id || ""));
                const ownMessageText = (node) => {
                    const candidates = Array.from(node.querySelectorAll('[class*="messageContent"]'));
                    return candidates.find((candidate) => {
                        const quoted = candidate.closest(
                            '[class*="repliedMessage"], [class*="repliedTextContent"], [class*="threadMessageAccessory"]'
                        );
                        return !quoted;
                    }) || candidates.at(-1) || null;
                };
                const textRows = validNodes.filter((node) => (ownMessageText(node)?.textContent || "").trim());
                const bodyPreview = (document.body?.innerText || "")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .slice(0, 240);
                return {
                    url: window.location.href,
                    raw_chat_nodes: rawNodes.length,
                    valid_message_id_nodes: validNodes.length,
                    text_rows: textRows.length,
                    empty_text_rows: Math.max(0, validNodes.length - textRows.length),
                    first_id: validNodes[0]?.id || "",
                    last_id: validNodes.at(-1)?.id || "",
                    body_preview: bodyPreview,
                };
            }
            """
        )

    async def read_channel_history(
        self,
        server_id: str,
        channel_id: str,
        *,
        limit: int = 320,
        scroll_rounds: int = 30,
    ) -> list[MessageRecord]:
        await self.ensure_latest_messages_visible()
        seen: dict[str, MessageRecord] = {}
        for message in await self._read_message_records_from_dom(server_id, channel_id):
            seen[message.message_id] = message

        stable_rounds = 0
        last_count = len(seen)
        for _ in range(max(scroll_rounds, 1)):
            oldest_before = await self._first_visible_message_id()
            at_top = await self._scroll_messages_up()
            if oldest_before:
                try:
                    await self.page.wait_for_function(
                        """
                        (oldest) => {
                            const first = Array.from(document.querySelectorAll('[id^="chat-messages-"]'))
                                .find((node) => /^chat-messages-\\d{5,}-\\d{5,}$/.test(node.id || ""));
                            return first && first.id && first.id !== oldest;
                        }
                        """,
                        oldest_before,
                        timeout=1_400,
                    )
                except Exception:
                    await self.page.wait_for_timeout(650)
            else:
                await self.page.wait_for_timeout(650)
            for message in await self._read_message_records_from_dom(server_id, channel_id):
                seen[message.message_id] = message
            oldest_after = await self._first_visible_message_id()
            if len(seen) == last_count and oldest_after == oldest_before:
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_count = len(seen)
            if len(seen) >= limit or (at_top and stable_rounds >= 3) or stable_rounds >= 5:
                break

        messages = sorted(seen.values(), key=_message_sort_value)
        return messages[-limit:]

    async def _read_message_records_from_dom(self, server_id: str, channel_id: str) -> list[MessageRecord]:
        rows = await self.page.evaluate(
            """
            () => {
                const rows = [];
                let lastAuthor = "";
                let lastAuthorId = null;
                const ownMessageText = (node) => {
                    const candidates = Array.from(node.querySelectorAll('[class*="messageContent"]'));
                    return candidates.find((candidate) => {
                        const quoted = candidate.closest(
                            '[class*="repliedMessage"], [class*="repliedTextContent"], [class*="threadMessageAccessory"]'
                        );
                        return !quoted;
                    }) || candidates.at(-1) || null;
                };
                const authorFrom = (node, header) => {
                    const authorNode =
                        node.querySelector('[id^="message-username-"]')
                        || header?.querySelector('[class*="username"], [class*="user-name"], [data-text]')
                        || null;
                    return (authorNode?.getAttribute("data-text") || authorNode?.textContent || "").trim();
                };
                const avatarIdFrom = (node) => {
                    const avatar = node.querySelector('img[src*="/avatars/"]');
                    const avatarMatch = avatar?.src?.match(/\\/avatars\\/(\\d+)\\//);
                    return avatarMatch ? avatarMatch[1] : null;
                };
                for (const node of Array.from(document.querySelectorAll('[id^="chat-messages-"]'))) {
                    if (!/^chat-messages-\\d{5,}-\\d{5,}$/.test(node.id || "")) continue;
                    const textNode = ownMessageText(node);
                    const header = node.querySelector('h3, [id^="message-username-"]');
                    const authorNode = header
                        ? header.querySelector('[class*="username"], [class*="user-name"], [data-text]')
                        : null;
                    const explicitAuthor = authorFrom(node, header);
                    const explicitAuthorId = avatarIdFrom(node);
                    const hasExplicitAuthor = Boolean(explicitAuthor || authorNode);
                    const author = hasExplicitAuthor ? explicitAuthor : lastAuthor;
                    const authorId = hasExplicitAuthor ? explicitAuthorId : lastAuthorId;
                    if (hasExplicitAuthor && explicitAuthor) {
                        lastAuthor = explicitAuthor;
                        lastAuthorId = explicitAuthorId;
                    }
                    rows.push({
                        id: node.id || "",
                        author,
                        authorId,
                        text: textNode ? textNode.textContent.trim() : "",
                    });
                }
                return rows.filter((row) => row.id && row.text);
            }
            """
        )
        return [
            MessageRecord(
                server_id=server_id,
                channel_id=channel_id,
                message_id=row["id"],
                author=clean_discord_display_name(row.get("author") or "unknown"),
                author_id=row.get("authorId"),
                text=row["text"],
            )
            for row in rows
        ]

    async def _scroll_messages_up(self) -> bool:
        return bool(
            await self.page.evaluate(
                """
                () => {
                    const firstMessage = Array.from(document.querySelectorAll('[id^="chat-messages-"]'))
                        .find((node) => /^chat-messages-\\d{5,}-\\d{5,}$/.test(node.id || ""));
                    const isScrollable = (node) => {
                        if (!node) return false;
                        const style = window.getComputedStyle(node);
                        return /(auto|scroll)/.test(style.overflowY || "")
                            && node.scrollHeight > node.clientHeight + 20;
                    };
                    let scroller = firstMessage;
                    while (scroller && scroller !== document.body) {
                        if (isScrollable(scroller)) break;
                        scroller = scroller.parentElement;
                    }
                    if (!scroller || scroller === document.body) {
                        const candidates = Array.from(document.querySelectorAll("main, section, div"))
                            .filter((node) => isScrollable(node) && (!firstMessage || node.contains(firstMessage)));
                        scroller = candidates.at(-1) || null;
                    }
                    if (!scroller) return true;
                    const before = scroller.scrollTop;
                    scroller.scrollTop = Math.max(
                        scroller.scrollTop - Math.max(scroller.clientHeight * 1.15, 800),
                        0
                    );
                    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
                    return scroller.scrollTop <= 4 || scroller.scrollTop === before;
                }
                """
            )
        )

    async def ensure_latest_messages_visible(self) -> None:
        try:
            await self.page.keyboard.press("End")
            await self.page.wait_for_timeout(350)
            await self.page.evaluate(
                """
                () => {
                    const firstMessage = Array.from(document.querySelectorAll('[id^="chat-messages-"]'))
                        .find((node) => /^chat-messages-\\d{5,}-\\d{5,}$/.test(node.id || ""));
                    const isScrollable = (node) => {
                        if (!node) return false;
                        const style = window.getComputedStyle(node);
                        return /(auto|scroll)/.test(style.overflowY || "")
                            && node.scrollHeight > node.clientHeight + 20;
                    };
                    let scroller = firstMessage;
                    while (scroller && scroller !== document.body) {
                        if (isScrollable(scroller)) {
                            scroller.scrollTop = scroller.scrollHeight;
                            break;
                        }
                        scroller = scroller.parentElement;
                    }
                }
                """
            )
            await self.page.keyboard.press("End")
            await self.page.wait_for_timeout(700)
        except Exception:
            await self.page.wait_for_timeout(500)

    async def send_message(
        self,
        text: str,
        *,
        reply_to_message_id: str = "",
        reply_fallback_to_channel: bool = False,
        typing_enabled: bool = False,
        typing_min_seconds: float = 2.5,
        typing_max_seconds: float = 18.0,
        typing_chars_per_second: float = 10.0,
    ) -> dict[str, object]:
        await self.wait_for_writable_channel(timeout_ms=15_000)
        delivery: dict[str, object] = {"reply_fallback_used": False, "reply_error": ""}
        if reply_to_message_id:
            try:
                await self._prepare_reply_to_message(reply_to_message_id)
            except Exception as exc:
                if not reply_fallback_to_channel:
                    raise
                delivery = {
                    "reply_fallback_used": True,
                    "reply_error": str(exc),
                }
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(250)
        before_message_ids = await self._visible_message_ids()
        textbox = self.page.locator(TEXTBOX).last
        await textbox.wait_for(state="visible", timeout=15_000)
        await textbox.click()
        if typing_enabled:
            await textbox.fill("")
            duration = _typing_duration(
                text,
                min_seconds=typing_min_seconds,
                max_seconds=typing_max_seconds,
                chars_per_second=typing_chars_per_second,
            )
            delay_ms = max(15, int((duration * 1000) / max(len(text), 1)))
            await textbox.type(text, delay=delay_ms)
        else:
            await textbox.fill(text)
        await self._dismiss_editor_popovers()
        await textbox.press("Enter")
        delivery.update(
            await self._wait_for_sent_message(
                text,
                before_message_ids=before_message_ids,
                timeout_ms=25_000,
            )
        )
        return delivery

    async def _dismiss_editor_popovers(self) -> None:
        try:
            has_editor_popover = await self.page.evaluate(
                """
                () => {
                    const visible = (node) => {
                        if (!node) return false;
                        const rect = node.getBoundingClientRect();
                        const style = window.getComputedStyle(node);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== "none"
                            && style.visibility !== "hidden";
                    };
                    return Array.from(document.querySelectorAll(
                        '[role="listbox"], [class*="autocomplete"], [class*="autocompleteInner"], [class*="autocompleteScroller"]'
                    )).some(visible);
                }
                """
            )
            if has_editor_popover:
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(200)
        except Exception:
            return

    async def _visible_message_ids(self) -> list[str]:
        return await self.page.evaluate(
            """
            () => Array.from(document.querySelectorAll('[id^="chat-messages-"]'))
                .map((node) => node.id || "")
                .filter((id) => /^chat-messages-\\d{5,}-\\d{5,}$/.test(id))
            """
        )

    async def _first_visible_message_id(self) -> str:
        ids = await self._visible_message_ids()
        return ids[0] if ids else ""

    async def _wait_for_sent_message(
        self,
        text: str,
        *,
        before_message_ids: list[str],
        timeout_ms: int,
    ) -> dict[str, object]:
        try:
            sent_handle = await self.page.wait_for_function(
                """
                ({ expected, beforeIds }) => {
                    const normalize = (value) => String(value || "")
                        .replace(/[\\u200B-\\u200D\\uFEFF]/g, "")
                        .replace(/\\s+/g, " ")
                        .trim();
                    const target = normalize(expected);
                    const targetWithoutPrefix = normalize(target
                        .replace(/^<@!?\\d+>\\s+/, "")
                        .replace(/^@\\S+(?:\\s+\\S+){0,3}\\s+/, "")
                    );
                    const usefulTargets = [target, targetWithoutPrefix].filter((item) => item.length >= 24);
                    const before = new Set(beforeIds || []);
                    const messages = Array.from(document.querySelectorAll('[id^="chat-messages-"]'));
                    const matchesRendered = (rendered) => {
                        if (!rendered || !target) return false;
                        if (rendered === target || rendered.includes(target) || target.includes(rendered)) {
                            return true;
                        }
                        return usefulTargets.some((candidate) => {
                            const head = candidate.slice(0, 120);
                            const tail = candidate.slice(-120);
                            return (head.length >= 24 && rendered.includes(head))
                                || (tail.length >= 24 && rendered.includes(tail));
                        });
                    };
                    const match = messages.find((node) => {
                        if (before.has(node.id || "")) return false;
                        const renderedCandidates = Array.from(node.querySelectorAll('[class*="messageContent"]'))
                            .map((content) => normalize(content?.textContent || ""))
                            .filter(Boolean);
                        renderedCandidates.push(normalize(node.textContent || ""));
                        return renderedCandidates.some(matchesRendered);
                    });
                    return match ? (match.id || true) : false;
                }
                """,
                {"expected": text, "beforeIds": before_message_ids},
                timeout=timeout_ms,
            )
            sent_message_id = await sent_handle.json_value()
            return {
                "confirmed": True,
                "assumed_sent": False,
                "confirmation_warning": "",
                "message_id": str(sent_message_id or ""),
            }
        except Exception as exc:
            state = await self.writable_channel_state()
            composer_text = await self._composer_text()
            after_message_ids = await self._visible_message_ids()
            before = set(before_message_ids or [])
            new_message_count = len([message_id for message_id in after_message_ids if message_id not in before])
            new_message_ids = [message_id for message_id in after_message_ids if message_id not in before]
            if _draft_still_in_composer(text, composer_text):
                detail = "The draft still appears to be sitting in the composer, so Discord did not submit it."
            elif composer_text.strip():
                detail = "The composer still contains text after Enter, so Discord likely blocked or redirected the send."
            else:
                await self.page.wait_for_timeout(4_000)
                late_message_ids = await self._visible_message_ids()
                late_new_message_ids = [
                    message_id for message_id in late_message_ids if message_id not in before
                ]
                if late_new_message_ids:
                    return {
                        "confirmed": False,
                        "assumed_sent": True,
                        "message_id": str(late_new_message_ids[-1]),
                        "confirmation_warning": (
                            "Discord cleared the composer and rendered a new message after the "
                            "normal confirmation window. Treated as delivered to avoid a duplicate send."
                        ),
                    }
                detail = "The composer cleared, but Kabuki could not match a newly rendered Discord message."
                if new_message_count > 0:
                    return {
                        "confirmed": False,
                        "assumed_sent": True,
                        "message_id": str(new_message_ids[-1] if new_message_ids else ""),
                        "confirmation_warning": (
                            "Discord cleared the composer and rendered a new message, but Kabuki "
                            "could not text-match the new message. Treated as delivered to avoid a duplicate send."
                        ),
                    }
            raise RuntimeError(
                "Discord did not confirm the message appeared after pressing Enter. "
                f"url={state.get('url')}; has_composer={state.get('has_composer')}; "
                f"has_messages={state.get('has_messages')}; notice={state.get('notice') or 'none'}. "
                f"{detail} The draft remains queued so you can inspect Discord before retrying."
            ) from exc

    async def _prepare_reply_to_message(self, message_id: str) -> None:
        safe_id = str(message_id or "").strip()
        if not safe_id:
            return
        message = self.page.locator(f"#{safe_id}").first
        try:
            await message.wait_for(state="visible", timeout=8_000)
            await message.scroll_into_view_if_needed(timeout=5_000)
            await message.hover(timeout=5_000)
        except Exception as exc:
            raise RuntimeError(
                "Discord could not find the selected message to reply to. "
                "Refresh the channel, regenerate the draft from a recent poster, then retry. "
                "No message was sent."
            ) from exc

        if await self._click_visible_reply_action(message):
            await self.page.wait_for_timeout(500)
            return

        try:
            await message.click(button="right", timeout=5_000)
            await self.page.wait_for_timeout(350)
            if await self._click_context_reply_action():
                await self.page.wait_for_timeout(500)
                return
        except Exception:
            pass

        raise RuntimeError(
            "Discord did not expose a Reply action for the selected message. "
            "The draft remains queued and no message was sent."
        )

    async def add_reaction(self, message_id: str, emoji: str = "😂") -> dict[str, object]:
        safe_id = str(message_id or "").strip()
        if not safe_id:
            raise RuntimeError("Missing Discord message ID for reaction.")
        message = self.page.locator(f"#{safe_id}").first
        try:
            await message.wait_for(state="visible", timeout=8_000)
            await message.scroll_into_view_if_needed(timeout=5_000)
            await message.hover(timeout=5_000)
            await self.page.wait_for_timeout(350)
            await self._reveal_message_actions(message)
        except Exception as exc:
            raise RuntimeError("Discord could not find the selected message to react to.") from exc

        if await self._message_has_own_reaction(message, emoji):
            return {"applied": False, "already_present": True, "emoji": emoji, "path": "own-existing"}
        unverified_paths: list[str] = []
        if await self._click_quick_reaction(message, emoji):
            if await self._wait_for_own_reaction(message, emoji, timeout_ms=3_000):
                return {"applied": True, "already_present": False, "emoji": emoji, "path": "quick"}
            unverified_paths.append("quick")
            try:
                await message.hover(timeout=2_000)
                await self.page.wait_for_timeout(250)
            except Exception:
                pass
        if await self._click_add_reaction_action(message):
            await self.page.wait_for_timeout(450)
            if await self._select_emoji_from_picker(emoji):
                if await self._wait_for_own_reaction(message, emoji, timeout_ms=6_000):
                    return {"applied": True, "already_present": False, "emoji": emoji, "path": "picker"}
                unverified_paths.append("picker")

        if unverified_paths:
            await self._dismiss_open_popouts()
            return {
                "applied": False,
                "already_present": False,
                "verification_failed": True,
                "emoji": emoji,
                "path": "+".join(unverified_paths) + "-unverified",
            }

        controls = await self._reaction_control_snapshot(message)
        await self._dismiss_open_popouts()
        detail = f" Visible controls near message: {controls}." if controls else ""
        raise RuntimeError(
            "Discord did not expose a usable Add Reaction control for the selected message."
            f"{detail}"
        )

    async def _wait_for_own_reaction(self, message, emoji: str, *, timeout_ms: int) -> bool:
        deadline = max(int(timeout_ms), 0)
        elapsed = 0
        step = 250
        while elapsed <= deadline:
            if await self._message_has_own_reaction(message, emoji):
                return True
            await self.page.wait_for_timeout(step)
            elapsed += step
        return False

    async def _message_has_own_reaction(self, message, emoji: str) -> bool:
        emoji_query = _emoji_search_query(emoji)
        try:
            return bool(
                await message.evaluate(
                    """
                    (messageNode, args) => {
                        const emoji = args.emoji || "";
                        const query = args.query || "";
                        const emojiPattern = (() => {
                            if (query === "joy") return /joy|laugh|face with tears/i;
                            if (query === "rofl") return /rofl|rolling on the floor/i;
                            if (query === "thumbsup") return /thumbs?\\s*up|thumbsup/i;
                            if (query === "pray") return /pray|folded hands|please/i;
                            if (query === "eyes") return /eyes/i;
                            if (query === "heart") return /heart/i;
                            return null;
                        })();
                        const queryMatch = (label) => (
                            query && label.toLowerCase().includes(String(query).toLowerCase())
                        );
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const messageRect = messageNode.getBoundingClientRect();
                        const nearMessage = (node) => {
                            const rect = node.getBoundingClientRect();
                            return rect.bottom >= messageRect.top - 80
                                && rect.top <= messageRect.bottom + 140
                                && rect.left >= messageRect.left - 20;
                        };
                        const nodes = [
                            ...Array.from(messageNode.querySelectorAll('[aria-label], [title], button, [role="button"]')),
                            ...Array.from(document.querySelectorAll('[aria-label], [title], button, [role="button"]'))
                                .filter((node) => visible(node) && nearMessage(node))
                        ];
                        return nodes.some((node) => {
                            const label = [
                                node.getAttribute("aria-label") || "",
                                node.getAttribute("title") || "",
                                node.getAttribute("data-list-item-id") || "",
                                node.textContent || ""
                            ].join(" ");
                            if (!label.includes(emoji) && !(emojiPattern && emojiPattern.test(label)) && !queryMatch(label)) return false;
                            const selected = /true|mixed/i.test(node.getAttribute("aria-pressed") || "")
                                || /true/i.test(node.getAttribute("aria-selected") || "")
                                || /selected|active|pressed/i.test(node.className || "");
                            return selected
                                || /you reacted|your reaction|remove(?: your)? reaction|unreact|click to remove|press to remove|already reacted/i.test(label)
                                || /remove/i.test(label);
                        });
                    }
                    """,
                    {"emoji": emoji, "query": emoji_query},
                )
            )
        except Exception:
            return False

    async def _click_quick_reaction(self, message, emoji: str) -> bool:
        try:
            return bool(
                await message.evaluate(
                    """
                    (messageNode, emoji) => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const msgRect = messageNode.getBoundingClientRect();
                        const candidates = Array.from(document.querySelectorAll(
                            'button[aria-label], [role="button"][aria-label], [aria-label], button'
                        )).filter((node) => {
                            if (!visible(node)) return false;
                            const label = `${node.getAttribute("aria-label") || ""} ${node.getAttribute("title") || ""} ${node.textContent || ""}`;
                            const wantsLaugh = emoji === "😂";
                            if (!label.includes(emoji) && !(wantsLaugh && /joy|laugh|face with tears/i.test(label))) return false;
                            const rect = node.getBoundingClientRect();
                            const nearVertically = rect.bottom >= msgRect.top - 90 && rect.top <= msgRect.bottom + 130;
                            const toTheRight = rect.left >= msgRect.left;
                            return nearVertically && toTheRight;
                        }).sort((left, right) => {
                            const a = left.getBoundingClientRect();
                            const b = right.getBoundingClientRect();
                            return Math.abs(a.top - msgRect.top) - Math.abs(b.top - msgRect.top);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """,
                    emoji,
                )
            )
        except Exception:
            return False

    async def _click_add_reaction_action(self, message) -> bool:
        await self._dismiss_open_popouts()
        await self._reveal_message_actions(message)
        if await self._click_visible_reaction_action(message):
            return True
        if await self._click_more_reaction_action(message):
            return True
        try:
            await message.click(button="right", timeout=5_000)
            await self.page.wait_for_timeout(350)
            return await self._click_context_reaction_action()
        except Exception:
            return False

    async def _click_visible_reaction_action(self, message) -> bool:
        try:
            return bool(
                await message.evaluate(
                    """
                    (messageNode) => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const msgRect = messageNode.getBoundingClientRect();
                        const candidates = Array.from(document.querySelectorAll(
                            'button, [role="button"], [aria-label], [title]'
                        )).filter((node) => {
                            const label = [
                                node.getAttribute("aria-label") || "",
                                node.getAttribute("title") || "",
                                node.getAttribute("data-list-item-id") || "",
                                node.textContent || ""
                            ].join(" ");
                            if (!/add\\s+reaction|\\breact\\b|emoji|smile|smiley/i.test(label) || !visible(node)) return false;
                            if (/super|reply|forward|thread|more|copy|edit|delete|pin|mark unread/i.test(label)) return false;
                            const rect = node.getBoundingClientRect();
                            const nearVertically = rect.bottom >= msgRect.top - 90 && rect.top <= msgRect.bottom + 130;
                            const toTheRight = rect.left >= msgRect.left;
                            return nearVertically && toTheRight;
                        }).sort((left, right) => {
                            const score = (node) => {
                                const label = `${node.getAttribute("aria-label") || ""} ${node.getAttribute("title") || ""} ${node.textContent || ""}`;
                                if (/add\\s+reaction/i.test(label)) return 0;
                                if (/\\breact\\b/i.test(label)) return 1;
                                if (/emoji|smile|smiley/i.test(label)) return 2;
                                return 3;
                            };
                            const scoreDiff = score(left) - score(right);
                            if (scoreDiff) return scoreDiff;
                            const a = left.getBoundingClientRect();
                            const b = right.getBoundingClientRect();
                            return Math.abs(a.top - msgRect.top) - Math.abs(b.top - msgRect.top);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """
                )
            )
        except Exception:
            return False

    async def _reveal_message_actions(self, message) -> None:
        try:
            await message.hover(timeout=2_000)
        except Exception:
            pass
        try:
            box = await message.bounding_box(timeout=2_000)
            if box:
                x = max(box["x"] + 8, box["x"] + box["width"] - 72)
                y = box["y"] + min(max(box["height"] * 0.3, 12), max(box["height"] - 8, 12))
                await self.page.mouse.move(x, y)
                await self.page.wait_for_timeout(200)
        except Exception:
            pass
        try:
            await message.evaluate(
                """
                (messageNode) => {
                    const eventInit = { bubbles: true, cancelable: true, view: window };
                    let node = messageNode;
                    for (let index = 0; node && index < 8; index += 1) {
                        for (const type of ["mouseover", "mouseenter", "mousemove"]) {
                            node.dispatchEvent(new MouseEvent(type, eventInit));
                        }
                        node = node.parentElement;
                    }
                }
                """
            )
            await self.page.wait_for_timeout(300)
        except Exception:
            pass

    async def _click_more_reaction_action(self, message) -> bool:
        if not await self._click_visible_more_action(message):
            return False
        await self.page.wait_for_timeout(350)
        return await self._click_context_reaction_action()

    async def _click_visible_more_action(self, message) -> bool:
        try:
            return bool(
                await message.evaluate(
                    """
                    (messageNode) => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const msgRect = messageNode.getBoundingClientRect();
                        const candidates = Array.from(document.querySelectorAll(
                            'button, [role="button"], [aria-label], [title]'
                        )).filter((node) => {
                            if (!visible(node)) return false;
                            const label = [
                                node.getAttribute("aria-label") || "",
                                node.getAttribute("title") || "",
                                node.getAttribute("data-list-item-id") || "",
                                node.textContent || ""
                            ].join(" ");
                            if (!/more|additional|message actions|open menu|ellipsis|options/i.test(label)) return false;
                            if (/server|channel|user settings|help|inbox|member/i.test(label)) return false;
                            const rect = node.getBoundingClientRect();
                            const nearVertically = rect.bottom >= msgRect.top - 90 && rect.top <= msgRect.bottom + 130;
                            const toTheRight = rect.left >= msgRect.left;
                            return nearVertically && toTheRight;
                        }).sort((left, right) => {
                            const a = left.getBoundingClientRect();
                            const b = right.getBoundingClientRect();
                            return Math.abs(a.top - msgRect.top) - Math.abs(b.top - msgRect.top);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """
                )
            )
        except Exception:
            return False

    async def _click_context_reaction_action(self) -> bool:
        try:
            return bool(
                await self.page.evaluate(
                    """
                    () => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const candidates = Array.from(document.querySelectorAll(
                            '[role="menuitem"], [role="menuitemradio"], [role="option"], button, [aria-label], [role="button"]'
                        )).filter((node) => {
                            const label = [
                                node.getAttribute("aria-label") || "",
                                node.getAttribute("title") || "",
                                node.getAttribute("data-list-item-id") || "",
                                node.textContent || ""
                            ].join(" ");
                            return /add\\s+reaction|\\breact\\b/i.test(label)
                                && !/super|reply|forward|thread|copy|edit|delete|pin|mark unread/i.test(label)
                                && visible(node);
                        }).sort((left, right) => {
                            const score = (node) => {
                                const label = `${node.getAttribute("aria-label") || ""} ${node.getAttribute("title") || ""} ${node.textContent || ""}`;
                                if (/add\\s+reaction/i.test(label)) return 0;
                                if (/\\breact\\b/i.test(label)) return 1;
                                return 2;
                            };
                            return score(left) - score(right);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """
                )
            )
        except Exception:
            return False

    async def _reaction_control_snapshot(self, message) -> list[str]:
        try:
            values = await message.evaluate(
                """
                (messageNode) => {
                    const visible = (node) => {
                        if (!node) return false;
                        const rect = node.getBoundingClientRect();
                        const style = window.getComputedStyle(node);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== "none"
                            && style.visibility !== "hidden";
                    };
                    const msgRect = messageNode.getBoundingClientRect();
                    return Array.from(document.querySelectorAll(
                        'button, [role="button"], [role="menuitem"], [role="option"], [aria-label], [title]'
                    )).filter((node) => {
                        if (!visible(node)) return false;
                        const rect = node.getBoundingClientRect();
                        return rect.bottom >= msgRect.top - 120
                            && rect.top <= msgRect.bottom + 160
                            && rect.left >= msgRect.left - 20;
                    }).map((node) => [
                        node.getAttribute("aria-label") || "",
                        node.getAttribute("title") || "",
                        node.getAttribute("data-list-item-id") || "",
                        (node.textContent || "").trim()
                    ].filter(Boolean).join(" | ").replace(/\\s+/g, " ").trim())
                    .filter(Boolean)
                    .slice(0, 10);
                }
                """
            )
        except Exception:
            return []
        return [str(item) for item in values or [] if str(item).strip()]

    async def _dismiss_open_popouts(self) -> None:
        try:
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(150)
        except Exception:
            pass

    async def _select_emoji_from_picker(self, emoji: str) -> bool:
        emoji_query = _emoji_search_query(emoji)
        try:
            search = self.page.locator(
                'input[placeholder*="Search"], input[aria-label*="Search"], [role="textbox"][aria-label*="Search"]'
            ).last
            if await search.count():
                await search.fill(emoji_query, timeout=3_000)
                await self.page.wait_for_timeout(450)
        except Exception:
            pass

        try:
            return bool(
                await self.page.evaluate(
                    """
                    ({ emoji, query }) => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const pattern = new RegExp(query === "joy" ? "joy|laugh|face with tears" : query, "i");
                        const candidates = Array.from(document.querySelectorAll(
                            '[role="gridcell"], [role="option"], button[aria-label], [aria-label], [role="button"]'
                        )).filter((node) => {
                            if (!visible(node)) return false;
                            const label = `${node.getAttribute("aria-label") || ""} ${node.getAttribute("title") || ""} ${node.textContent || ""}`;
                            return label.includes(emoji) || pattern.test(label);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """,
                    {"emoji": emoji, "query": emoji_query},
                )
            )
        except Exception:
            return False

    async def _click_visible_reply_action(self, message) -> bool:
        try:
            return bool(
                await message.evaluate(
                    """
                    (messageNode) => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const msgRect = messageNode.getBoundingClientRect();
                        const candidates = Array.from(document.querySelectorAll(
                            'button[aria-label], [role="button"][aria-label], [aria-label]'
                        )).filter((node) => {
                            const label = `${node.getAttribute("aria-label") || ""} ${node.textContent || ""}`;
                            if (!/\\breply\\b/i.test(label) || !visible(node)) return false;
                            const rect = node.getBoundingClientRect();
                            const nearVertically = rect.bottom >= msgRect.top - 80 && rect.top <= msgRect.bottom + 120;
                            const toTheRight = rect.left >= msgRect.left;
                            return nearVertically && toTheRight;
                        }).sort((left, right) => {
                            const a = left.getBoundingClientRect();
                            const b = right.getBoundingClientRect();
                            return Math.abs(a.top - msgRect.top) - Math.abs(b.top - msgRect.top);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """
                )
            )
        except Exception:
            return False

    async def _click_context_reply_action(self) -> bool:
        try:
            return bool(
                await self.page.evaluate(
                    """
                    () => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const candidates = Array.from(document.querySelectorAll(
                            '[role="menuitem"], [role="menuitemradio"], [aria-label], [role="button"]'
                        )).filter((node) => {
                            const label = `${node.getAttribute("aria-label") || ""} ${node.textContent || ""}`;
                            return /\\breply\\b/i.test(label) && visible(node);
                        });
                        if (!candidates.length) return false;
                        candidates[0].click();
                        return true;
                    }
                    """
                )
            )
        except Exception as exc:
            raise RuntimeError(
                "Discord did not expose a Reply action for the selected message. "
                "The draft remains queued and no message was sent."
            ) from exc

    async def _composer_text(self) -> str:
        try:
            return await self.page.evaluate(
                """
                () => {
                    const visible = (node) => {
                        if (!node) return false;
                        const rect = node.getBoundingClientRect();
                        const style = window.getComputedStyle(node);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== "none"
                            && style.visibility !== "hidden";
                    };
                    const composers = Array.from(document.querySelectorAll(
                        '[data-slate-editor="true"][role="textbox"], div[role="textbox"][contenteditable="true"]'
                    )).filter(visible);
                    const composer = composers[composers.length - 1];
                    return (composer?.innerText || composer?.textContent || "").trim();
                }
                """
            )
        except Exception:
            return ""

    async def _is_logged_in(self) -> bool:
        if "/login" in self.page.url:
            return False
        if not self.page.url.startswith("https://discord.com/channels/"):
            return False
        try:
            return bool(
                await self.page.evaluate(
                    """
                    () => {
                        const visible = (node) => {
                            if (!node) return false;
                            const rect = node.getBoundingClientRect();
                            const style = window.getComputedStyle(node);
                            return rect.width > 0
                                && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const loginVisible = Array.from(document.querySelectorAll(
                            'input[name="email"], input[type="email"]'
                        )).some(visible);
                        const authenticatedShell = document.querySelector('[aria-label="User Settings"]')
                            || document.querySelector('[data-list-id="guildsnav"]');
                        return !loginVisible && Boolean(authenticatedShell);
                    }
                    """
                )
            )
        except Exception:
            return False


def _typing_duration(
    text: str,
    *,
    min_seconds: float,
    max_seconds: float,
    chars_per_second: float,
) -> float:
    chars = max(len(text.strip()), 1)
    cps = max(float(chars_per_second or 10.0), 1.0)
    lower = max(float(min_seconds or 0), 0.0)
    upper = max(float(max_seconds or lower), lower)
    return min(max(chars / cps, lower), upper)


def _normalized_message_text(value: str) -> str:
    return " ".join(str(value or "").replace("\u200b", "").replace("\ufeff", "").split())


def _draft_still_in_composer(expected: str, composer_text: str) -> bool:
    expected_text = _normalized_message_text(expected)
    actual_text = _normalized_message_text(composer_text)
    if not expected_text or not actual_text:
        return False
    return expected_text in actual_text or actual_text in expected_text


def _message_sort_value(message: MessageRecord) -> int:
    try:
        return int(str(message.message_id).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _discord_message_token(message_id: str) -> str:
    raw = str(message_id or "").strip()
    if not raw:
        return ""
    if raw.startswith("chat-messages-"):
        return raw.rsplit("-", 1)[-1]
    return raw


def _emoji_search_query(emoji: str) -> str:
    return {
        "😂": "joy",
        "🤣": "rofl",
        "👍": "thumbsup",
        "🙏": "pray",
        "👀": "eyes",
        "\U0001f914": "thinking",
        "❤️": "heart",
        "❤": "heart",
    }.get(str(emoji or "").strip(), str(emoji or "joy").strip() or "joy")


def _profile_in_use_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "opening in existing browser session" in message
        or "user data directory is already in use" in message
        or "profile appears to be in use" in message
        or "singletonlock" in message
        or "processsingleton" in message
    )


def _close_profile_browsers(profile_dir: Path) -> None:
    if sys.platform != "win32":
        return
    profile = str(profile_dir.resolve())
    script = f"""
$needle = "--user-data-dir={profile}"
Get-CimInstance Win32_Process |
  Where-Object {{
    $_.CommandLine -and
    $_.CommandLine.IndexOf($needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
  }} |
  ForEach-Object {{
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }}
"""
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            check=False,
            timeout=8,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception:
        return


def discord_login_blocker_message(state: dict[str, object]) -> str:
    if state.get("password_reset"):
        return (
            "Discord is requiring a password reset or account security action. Pause "
            "Kabuki-Cord, complete the visible Discord flow yourself, then leave the "
            "scanner off for a cooldown before retrying. No message was sent."
        )
    if state.get("account_action_required"):
        return (
            "Discord is asking for account verification or another security action. "
            "Kabuki-Cord has stopped this operation. Open Sign In, complete the visible "
            "Discord flow yourself, then retry later. No message was sent."
        )
    if state.get("human_verification"):
        return (
            "Discord is showing a human verification check. Click Sign In, complete the "
            "visible Discord check, then retry. No message was sent."
        )
    if state.get("two_factor"):
        return (
            "Discord is asking for an authentication code. Click Sign In, complete the "
            "visible Discord login, then retry. No message was sent."
        )
    if state.get("login_form_visible"):
        return (
            "Discord is on the login screen. Click Sign In, complete the visible Discord "
            "login, then retry. No message was sent."
        )
    return (
        "Discord is not signed in. Click Sign In, complete the visible Discord login, "
        "then retry. No message was sent."
    )
