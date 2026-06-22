from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

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
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        args = ["--disable-blink-features=AutomationControlled"]
        launch_headless = self.headless
        if self.headless:
            # Discord does not reliably reuse the signed-in profile in true headless mode.
            # Use an off-screen headful window for silent automation instead.
            launch_headless = False
            args.extend(["--window-position=-32000,-32000", "--window-size=1440,1000"])
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel=self.browser_channel,
            headless=launch_headless,
            viewport={"width": 1440, "height": 1000},
            args=args,
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        return self

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

        await self._reset_channel_sidebar_scroll()
        seen: dict[str, dict[str, str]] = {}
        last_count = -1
        stable_rounds = 0
        for _ in range(12):
            rows = await self._visible_channel_rows(server_id)
            for row in rows:
                seen[row["channel_id"]] = row

            if len(seen) == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_count = len(seen)

            at_bottom = await self._scroll_channel_sidebar()
            if at_bottom and stable_rounds >= 1:
                break

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
                        type === "text" || type === "forum" || type === "announcement"
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

    async def _scroll_channel_sidebar(self) -> bool:
        return bool(
            await self.page.evaluate(
                """
                () => {
                    const firstChannel = document.querySelector('[data-list-item-id^="channels___"]');
                    let scroller = firstChannel?.parentElement || null;
                    while (scroller && scroller !== document.body) {
                        if (scroller.scrollHeight > scroller.clientHeight + 20) break;
                        scroller = scroller.parentElement;
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
                let scroller = firstChannel?.parentElement || null;
                while (scroller && scroller !== document.body) {
                    if (scroller.scrollHeight > scroller.clientHeight + 20) break;
                    scroller = scroller.parentElement;
                }
                if (scroller && scroller !== document.body) {
                    scroller.scrollTop = 0;
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
                blocker = await self.login_blocker_state()
                if blocker.get("human_verification"):
                    return False

        try:
            await self.page.wait_for_function(
                """
                () => location.href.includes("/channels/")
                    && !location.href.includes("/login")
                    && !document.querySelector('input[name="email"], input[type="email"]')
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

    async def navigate_channel(self, server_id: str, channel_id: str) -> str:
        await self.page.goto(
            f"https://discord.com/channels/{server_id}/{channel_id}",
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
        rows = await self.page.evaluate(
            """
            () => {
                const rows = [];
                let lastAuthor = "";
                let lastAuthorId = null;
                for (const node of Array.from(document.querySelectorAll('[id^="chat-messages-"]'))) {
                    const textNode = node.querySelector('[class*="messageContent"]');
                    const header = node.querySelector('h3');
                    const authorNode = header
                        ? header.querySelector('[class*="username"], [class*="user-name"]')
                        : null;
                    const avatar = node.querySelector('img[class*="avatar_"][src*="/avatars/"]');
                    const avatarMatch = avatar?.src?.match(/\\/avatars\\/(\\d+)\\//);
                    const author = authorNode
                        ? (authorNode.getAttribute("data-text") || authorNode.textContent || "").trim()
                        : lastAuthor;
                    const authorId = avatarMatch ? avatarMatch[1] : lastAuthorId;
                    if (author) lastAuthor = author;
                    if (authorId) lastAuthorId = authorId;
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
                author=row.get("author") or "unknown",
                author_id=row.get("authorId"),
                text=row["text"],
            )
            for row in rows
        ]

    async def ensure_latest_messages_visible(self) -> None:
        try:
            await self.page.keyboard.press("End")
            await self.page.wait_for_timeout(350)
            await self.page.evaluate(
                """
                () => {
                    const firstMessage = document.querySelector('[id^="chat-messages-"]');
                    let scroller = firstMessage?.parentElement || null;
                    while (scroller && scroller !== document.body) {
                        if (scroller.scrollHeight > scroller.clientHeight + 20) {
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
        typing_enabled: bool = False,
        typing_min_seconds: float = 2.5,
        typing_max_seconds: float = 18.0,
        typing_chars_per_second: float = 10.0,
    ) -> None:
        await self.wait_for_writable_channel(timeout_ms=15_000)
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
        await textbox.press("Enter")
        await self._wait_for_sent_message(text, before_message_ids=before_message_ids, timeout_ms=15_000)

    async def _visible_message_ids(self) -> list[str]:
        return await self.page.evaluate(
            """
            () => Array.from(document.querySelectorAll('[id^="chat-messages-"]'))
                .map((node) => node.id || "")
                .filter(Boolean)
            """
        )

    async def _wait_for_sent_message(
        self,
        text: str,
        *,
        before_message_ids: list[str],
        timeout_ms: int,
    ) -> None:
        try:
            await self.page.wait_for_function(
                """
                ({ expected, beforeIds }) => {
                    const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                    const target = normalize(expected);
                    const before = new Set(beforeIds || []);
                    const messages = Array.from(document.querySelectorAll('[id^="chat-messages-"]'));
                    return messages.some((node) => {
                        if (before.has(node.id || "")) return false;
                        const content = node.querySelector('[class*="messageContent"]');
                        return normalize(content?.textContent || "") === target;
                    });
                }
                """,
                {"expected": text, "beforeIds": before_message_ids},
                timeout=timeout_ms,
            )
        except Exception as exc:
            state = await self.writable_channel_state()
            raise RuntimeError(
                "Discord did not confirm the message appeared after pressing Enter. "
                f"url={state.get('url')}; has_composer={state.get('has_composer')}; "
                f"has_messages={state.get('has_messages')}; notice={state.get('notice') or 'none'}. "
                "The draft remains queued so you can inspect Discord before retrying."
            ) from exc

    async def _is_logged_in(self) -> bool:
        if "/login" in self.page.url:
            return False
        if not self.page.url.startswith("https://discord.com/channels/"):
            return False
        try:
            return not await self.page.locator('input[name="email"], input[type="email"]').first.is_visible(
                timeout=500
            )
        except Exception:
            return True


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


def discord_login_blocker_message(state: dict[str, object]) -> str:
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
