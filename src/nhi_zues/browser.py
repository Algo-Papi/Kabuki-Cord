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
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel=self.browser_channel,
            headless=self.headless,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
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
                const remember = (serverId, label) => {
                    if (seen.has(serverId)) return;
                    seen.set(serverId, { server_id: serverId, label: cleanLabel(label) });
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
                    remember(serverId, rawLabel);
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
                    remember(match[1], rawLabel);
                }
                return Array.from(seen.values());
            }
            """
        )
        return [
            {"server_id": str(row["server_id"]), "label": str(row.get("label") or "")}
            for row in rows
            if row.get("server_id")
        ]

    async def login_if_needed(
        self,
        *,
        email: str | None = None,
        password: str | None = None,
        timeout_seconds: int = 180,
    ) -> bool:
        await self.open_home()
        if await self._is_logged_in():
            return True

        login_form = self.page.locator('input[name="email"], input[type="email"]').first
        if await login_form.count() and email and password:
            await login_form.fill(email)
            password_input = self.page.locator('input[name="password"], input[type="password"]').first
            await password_input.fill(password)
            await password_input.press("Enter")

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
                    return (inTarget && hasRows) || (!inTarget && redirectedHome);
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

    async def read_visible_messages(self, server_id: str, channel_id: str) -> list[MessageRecord]:
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

    async def send_message(self, text: str) -> None:
        textbox = self.page.locator(TEXTBOX).last
        await textbox.wait_for(state="visible", timeout=15_000)
        await textbox.click()
        await textbox.fill(text)
        await textbox.press("Enter")
        await asyncio.sleep(0.5)

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
