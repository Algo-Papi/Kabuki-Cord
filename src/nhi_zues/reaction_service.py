from __future__ import annotations

import math

from . import own_identity
from .reactions import should_auto_react
from .reply_policy import is_own_message


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
            if reaction_ledger.has_reacted_to_message(
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
        if reaction_ledger.has_reacted_to_message(
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
            continue

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


def force_window_fill_reason(reason: str, percent: float) -> str:
    label = f"force reaction target fill ({float(percent or 0.0):g}% target)"
    return str(reason or "").replace("force reaction sample accepted (100%)", label)
