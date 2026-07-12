from __future__ import annotations

from datetime import datetime, timezone

from .config import AppConfig
from . import own_identity
from .reply_ledger import ReplyLedger


def auto_reply_guard_reason(
    config: AppConfig,
    reply_ledger: ReplyLedger,
    *,
    channel_id: str,
    visible_messages,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    cooldown_seconds = max(0.0, float(getattr(config, "reply_cooldown_seconds", 0.0) or 0.0))
    if cooldown_seconds:
        latest = reply_ledger.latest_for_channel(channel_id=channel_id)
        latest_at = reply_created_at(latest)
        if latest_at is not None:
            age_seconds = (now - latest_at).total_seconds()
            if age_seconds < cooldown_seconds:
                return (
                    "Auto reply blocked by channel cooldown: "
                    f"last sent {format_seconds(age_seconds)} ago; "
                    f"cooldown is {format_seconds(cooldown_seconds)}."
                )

    max_per_window = max(0, int(getattr(config, "reply_max_per_window", 0) or 0))
    window_seconds = max(60.0, float(getattr(config, "reply_window_seconds", 3600.0) or 3600.0))
    if max_per_window:
        recent = reply_ledger.recent_for_channel(
            channel_id=channel_id,
            window_seconds=window_seconds,
            now=now,
        )
        if len(recent) >= max_per_window:
            return (
                "Auto reply blocked by channel rate limit: "
                f"{len(recent)} sent in the last {format_seconds(window_seconds)}; "
                f"limit is {max_per_window}."
            )

    if bool(getattr(config, "reply_require_intervening_user", True)):
        streak_reason = own_message_streak_guard_reason(
            visible_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )
        if streak_reason:
            return streak_reason

    return ""


def own_message_streak_guard_reason(
    messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
) -> str:
    visible = list(messages or [])
    last_own_index = -1
    for index, message in enumerate(visible):
        if is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        ):
            last_own_index = index
    if last_own_index < 0:
        return ""
    for message in visible[last_own_index + 1 :]:
        if not is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        ):
            return ""
    return (
        "Auto reply blocked because the last visible message in this channel is already "
        "from the character. Waiting for another user before posting again."
    )


def reply_created_at(reply) -> datetime | None:
    if reply is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(reply.created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def own_author_ids_from_messages(
    messages,
    *,
    character_names: tuple[str, ...],
    own_texts: set[str] | None = None,
) -> set[str]:
    return own_identity.own_author_ids_from_messages(
        messages,
        character_names=character_names,
        own_texts=own_texts,
    )


def is_own_message(
    message,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
) -> bool:
    return own_identity.is_own_message(
        message,
        character_names=character_names,
        own_author_ids=own_author_ids,
        own_message_ids=own_message_ids,
        own_texts=own_texts,
    )


def is_character_author(author: str, character_names: tuple[str, ...]) -> bool:
    return own_identity.is_character_author(author, character_names)


def normalize_author(value: str) -> str:
    return own_identity.normalize_author(value)


def format_seconds(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0))))
    minutes, remainder = divmod(value, 60)
    if minutes <= 0:
        return f"{remainder}s"
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {remainder:02d}s"


def requires_approval(
    runtime_mode: str,
    engagement_type: str,
    *,
    auto_respond_enabled: bool,
) -> bool:
    mode = str(runtime_mode or "dry").lower()
    kind = str(engagement_type or "").lower()
    if mode == "live_fire":
        return True
    if not auto_respond_enabled:
        return True
    if mode == "semi_auto":
        return kind in {"proactive", "manual"}
    return False


def approval_gate_reason(
    runtime_mode: str,
    engagement_type: str,
    *,
    auto_respond_enabled: bool,
) -> str:
    mode = str(runtime_mode or "dry").lower()
    kind = str(engagement_type or "").lower()
    if mode == "live_fire":
        return "Review every draft mode requires approval before live delivery"
    if not auto_respond_enabled:
        return "Auto is off for this channel"
    if mode == "semi_auto" and kind in {"proactive", "manual"}:
        return "Limited autonomous mode reviews new starts and manual drafts"
    return ""
