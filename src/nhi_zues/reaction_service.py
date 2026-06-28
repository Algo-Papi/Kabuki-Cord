from __future__ import annotations

import math
from datetime import datetime, timezone

from . import own_identity
from .reactions import should_auto_react
from .reply_policy import is_own_message


REACTION_FAILURE_BACKOFF_SECONDS = 1800.0
REACTION_FAILURE_BACKOFF_THRESHOLD = 2


async def process_reactions(
    *,
    config,
    events,
    reaction_ledger,
    session,
    target,
    candidates,
    fresh_count: int,
    force_laugh_ids: set[str] | None = None,
    character_names: tuple[str, ...] = (),
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
) -> set[str]:
    if not getattr(target, "react_enabled", False):
        return set()
    if config.runtime_mode == "dry":
        events.add(
            event_type="reaction_skipped",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                "React is enabled, but Dry Mode blocks Discord reactions. "
                f"fresh={fresh_count}, candidates={len(candidates)}."
            ),
        )
        return set()
    if config.reaction_max_per_channel <= 0:
        events.add(
            event_type="reaction_skipped",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                "React is enabled, but the per-scan reaction cap is 0. "
                f"fresh={fresh_count}, candidates={len(candidates)}."
            ),
        )
        return set()
    failure_backoff_remaining = reaction_failure_backoff_remaining(
        reaction_ledger,
        channel_id=target.channel_id,
        backoff_seconds=max(
            REACTION_FAILURE_BACKOFF_SECONDS,
            float(getattr(config, "reaction_cooldown_seconds", 0.0) or 0.0) * 2,
        ),
        failure_threshold=REACTION_FAILURE_BACKOFF_THRESHOLD,
    )
    if failure_backoff_remaining > 0:
        events.add(
            event_type="reaction_skipped",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                "React is temporarily backed off for this channel after repeated "
                "Discord reaction UI failures. "
                f"fresh={fresh_count}, candidates={len(candidates)}, "
                f"backoff_remaining={math.ceil(failure_backoff_remaining)}s."
            ),
        )
        return set()
    cooldown_remaining = reaction_cooldown_remaining(
        reaction_ledger,
        channel_id=target.channel_id,
        cooldown_seconds=getattr(config, "reaction_cooldown_seconds", 0.0),
    )
    if cooldown_remaining > 0:
        events.add(
            event_type="reaction_skipped",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                "React is enabled, but this channel is in reaction cooldown. "
                f"fresh={fresh_count}, candidates={len(candidates)}, "
                f"cooldown_remaining={math.ceil(cooldown_remaining)}s."
            ),
        )
        return set()

    reacted_message_ids: set[str] = set()
    ledgered = 0
    ineligible = 0
    attempted = 0
    already_present = 0
    failed = 0
    own_skipped = 0
    cap_reached = False
    last_reason = ""
    force_laugh_ids = force_laugh_ids or set()
    own_author_ids = own_author_ids or set()
    force_window_enabled = (
        bool(force_laugh_ids)
        and float(getattr(config, "reaction_force_laugh_percent", 0.0) or 0.0) > 0
    )
    force_window_cap = reaction_window_cap(
        config.reaction_force_laugh_percent,
        len(force_laugh_ids),
    )
    force_window_used = (
        sum(
            1
            for message_id in force_laugh_ids
            if _has_attempted_reaction(
                reaction_ledger,
                channel_id=target.channel_id,
                message_id=message_id,
            )
        )
        if force_window_enabled
        else 0
    )
    force_window_remaining = max(0, force_window_cap - force_window_used)
    force_window_capped = 0
    for message in candidates:
        if len(reacted_message_ids) >= config.reaction_max_per_channel:
            cap_reached = True
            break
        in_force_window = message.message_id in force_laugh_ids
        if is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        ):
            own_skipped += 1
            last_reason = "message is from the configured character/account"
            continue
        if _has_attempted_reaction(
            reaction_ledger,
            channel_id=message.channel_id,
            message_id=message.message_id,
        ):
            ledgered += 1
            continue
        if force_window_enabled and in_force_window and force_window_remaining <= 0:
            force_window_capped += 1
            last_reason = "rolling reaction percentage cap reached for the recent non-own message window"
            continue
        force_window_fill = force_window_enabled and in_force_window and force_window_remaining > 0
        should_react, emoji, reason = should_auto_react(
            message.text,
            threshold=config.reaction_threshold,
            sample_percent=config.reaction_sample_percent,
            force_laugh_percent=100.0 if force_window_fill else 0.0,
            emoji_override=config.reaction_emoji_override,
        )
        if not should_react:
            ineligible += 1
            last_reason = reason
            continue
        if force_window_fill:
            reason = force_window_fill_reason(reason, config.reaction_force_laugh_percent)
        try:
            attempted += 1
            result = await session.add_reaction(message.message_id, emoji)
        except Exception as exc:
            failed += 1
            reaction_ledger.record(
                server_id=target.server_id,
                message=message,
                emoji=emoji,
                reason=f"failed reaction attempt; {exc}",
                verified=False,
            )
            events.add(
                event_type="reaction_failed",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=f"Could not add {emoji} reaction: {exc}",
                draft=message.text,
            )
            return reacted_message_ids
        if result.get("already_present"):
            already_present += 1
            reaction_ledger.record(
                server_id=target.server_id,
                message=message,
                emoji=emoji,
                reason=f"already present from this account; {reason}",
            )
            if force_window_enabled and in_force_window:
                force_window_remaining = max(0, force_window_remaining - 1)
            events.add(
                event_type="reaction_already_present",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    f"{emoji} reaction was already present from this account on "
                    f"{message.author}; path={result.get('path') or 'existing'}."
                ),
                draft=message.text,
                message_id=message.message_id,
                target_message_id=message.message_id,
                target_author=message.author,
                emoji=emoji,
            )
            continue
        if not result.get("applied"):
            failed += 1
            reaction_ledger.record(
                server_id=target.server_id,
                message=message,
                emoji=emoji,
                reason=f"unverified reaction attempt; path={result.get('path') or 'unverified'}",
                verified=False,
            )
            events.add(
                event_type="reaction_failed",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    f"Could not verify {emoji} reaction on {message.author}; "
                    f"path={result.get('path') or 'unverified'}."
                ),
                draft=message.text,
                message_id=message.message_id,
                target_message_id=message.message_id,
                target_author=message.author,
                emoji=emoji,
            )
            return reacted_message_ids

        reaction_ledger.record(
            server_id=target.server_id,
            message=message,
            emoji=emoji,
            reason=reason,
        )
        events.add(
            event_type="reaction_added",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                f"Added {emoji} reaction to {message.author}: "
                f"{reason}; path={result.get('path') or 'existing'}."
            ),
            draft=message.text,
            message_id=message.message_id,
            target_message_id=message.message_id,
            target_author=message.author,
            emoji=emoji,
        )
        reacted_message_ids.add(message.message_id)
        if force_window_enabled and in_force_window:
            force_window_remaining = max(0, force_window_remaining - 1)
    if not reacted_message_ids:
        events.add(
            event_type="reaction_scan",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                "React scan made no new reaction. "
                f"fresh={fresh_count}, candidates={len(candidates)}, ledgered={ledgered}, "
                f"ineligible={ineligible}, attempted={attempted}, already_present={already_present}, "
                f"failed={failed}, own_skipped={own_skipped}, cap_reached={str(cap_reached).lower()}, "
                f"threshold={config.reaction_threshold}, sample={config.reaction_sample_percent:g}%"
                f", force_recent={config.reaction_force_laugh_percent:g}%"
                f", force_window={force_window_used}/{force_window_cap}/{len(force_laugh_ids)}"
                f", force_window_capped={force_window_capped}"
                + (f", last_skip={last_reason}" if last_reason else "")
                + "."
            ),
        )
    return reacted_message_ids


def without_own_messages(
    messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
):
    return own_identity.without_own_messages(
        messages,
        character_names=character_names,
        own_author_ids=own_author_ids,
        own_message_ids=own_message_ids,
        own_texts=own_texts,
    )


def recent_reaction_candidates(
    visible_messages,
    fresh_messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
    max_visible: int = 12,
):
    candidates = []
    seen_ids = set()
    for message in without_own_messages(
        fresh_messages,
        character_names=character_names,
        own_author_ids=own_author_ids,
        own_message_ids=own_message_ids,
        own_texts=own_texts,
    ):
        if message.message_id in seen_ids:
            continue
        candidates.append(message)
        seen_ids.add(message.message_id)
    for message in reversed(
        without_own_messages(
            visible_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )
    ):
        if len(candidates) >= max_visible:
            break
        if message.message_id in seen_ids:
            continue
        candidates.append(message)
        seen_ids.add(message.message_id)
    return candidates


def recent_non_own_message_ids(
    visible_messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: set[str] | None = None,
    limit: int,
) -> set[str]:
    message_ids: list[str] = []
    for message in reversed(
        without_own_messages(
            visible_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )
    ):
        message_id = str(getattr(message, "message_id", "") or "")
        if not message_id or message_id in message_ids:
            continue
        message_ids.append(message_id)
        if len(message_ids) >= limit:
            break
    return set(message_ids)


def reaction_window_cap(percent: float, window_size: int) -> int:
    percent = max(0.0, min(float(percent or 0.0), 100.0))
    window_size = max(0, int(window_size or 0))
    if percent <= 0.0 or window_size <= 0:
        return 0
    return min(window_size, max(1, math.ceil(window_size * (percent / 100.0))))


def reaction_cooldown_remaining(
    reaction_ledger,
    *,
    channel_id: str,
    cooldown_seconds: float,
    now: datetime | None = None,
) -> float:
    cooldown = max(0.0, float(cooldown_seconds or 0.0))
    if cooldown <= 0:
        return 0.0
    latest = None
    last_attempt_at = getattr(reaction_ledger, "last_attempt_at", None)
    if callable(last_attempt_at):
        latest = last_attempt_at(channel_id=channel_id)
    last_reaction_at = getattr(reaction_ledger, "last_reaction_at", None)
    if latest is None and callable(last_reaction_at):
        latest = last_reaction_at(channel_id=channel_id)
    if latest is None:
        return 0.0
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    elapsed = max(0.0, (current - latest.astimezone(timezone.utc)).total_seconds())
    return max(0.0, cooldown - elapsed)


def reaction_failure_backoff_remaining(
    reaction_ledger,
    *,
    channel_id: str,
    backoff_seconds: float,
    failure_threshold: int,
    now: datetime | None = None,
) -> float:
    threshold = max(1, int(failure_threshold or 1))
    backoff = max(0.0, float(backoff_seconds or 0.0))
    if backoff <= 0:
        return 0.0
    recent_unverified_count = getattr(reaction_ledger, "recent_unverified_count", None)
    if not callable(recent_unverified_count):
        return 0.0
    current = now or datetime.now(timezone.utc)
    failures = recent_unverified_count(
        channel_id=channel_id,
        within_seconds=backoff,
        now=current,
    )
    if failures < threshold:
        return 0.0
    last_attempt_at = getattr(reaction_ledger, "last_attempt_at", None)
    if not callable(last_attempt_at):
        return backoff
    latest = last_attempt_at(channel_id=channel_id)
    if latest is None:
        return backoff
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    elapsed = max(0.0, (current - latest.astimezone(timezone.utc)).total_seconds())
    return max(0.0, backoff - elapsed)


def _has_attempted_reaction(reaction_ledger, *, channel_id: str, message_id: str) -> bool:
    has_attempted = getattr(reaction_ledger, "has_attempted_to_message", None)
    if callable(has_attempted):
        return bool(has_attempted(channel_id=channel_id, message_id=message_id))
    return bool(reaction_ledger.has_reacted_to_message(channel_id=channel_id, message_id=message_id))


def force_window_fill_reason(reason: str, percent: float) -> str:
    label = f"force reaction target fill ({float(percent or 0.0):g}% target)"
    return str(reason or "").replace("force reaction sample accepted (100%)", label)
