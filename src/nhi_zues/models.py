from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class MessageRecord:
    server_id: str
    channel_id: str
    message_id: str
    author: str
    author_id: str | None
    text: str
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class UserMemory:
    user_key: str
    display_name: str
    stable_user_id: str | None
    message_count: int
    recent_topics: tuple[str, ...]
    last_seen_at: datetime
    summary: str = ""


@dataclass(frozen=True)
class DraftDecision:
    should_reply: bool
    reason: str
    draft: str | None = None
    engagement_type: str = "none"
    requires_approval: bool = False
