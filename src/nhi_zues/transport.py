from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Protocol

from .models import MessageRecord


class ChatTransport(Protocol):
    """Runtime boundary for the external chat client transport."""

    async def open_home(self) -> None: ...

    async def is_logged_in(self) -> bool: ...

    async def current_user_id(self) -> str | None: ...

    async def login_if_needed(
        self,
        *,
        email: str | None = None,
        password: str | None = None,
        timeout_seconds: int = 180,
        allow_human_challenge: bool = True,
    ) -> bool: ...

    async def account_blocker_state(self) -> dict[str, object]: ...

    async def navigate_channel(
        self,
        server_id: str,
        channel_id: str,
        *,
        message_id: str = "",
    ) -> str: ...

    async def read_visible_messages(
        self,
        server_id: str,
        channel_id: str,
    ) -> list[MessageRecord]: ...

    async def read_channel_history(
        self,
        server_id: str,
        channel_id: str,
        *,
        limit: int = 320,
        scroll_rounds: int = 30,
    ) -> list[MessageRecord]: ...

    async def ensure_latest_messages_visible(self) -> None: ...

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
    ) -> dict[str, object]: ...


class TransportFactory(Protocol):
    def __call__(
        self,
        profile_dir: Path,
        *,
        browser_channel: str | None,
        headless: bool,
    ) -> AbstractAsyncContextManager[ChatTransport]: ...


class BrowserDiagnosticsTransport(ChatTransport, Protocol):
    """Optional browser-only diagnostics kept outside core planning policy."""

    @property
    def page(self) -> Any: ...
