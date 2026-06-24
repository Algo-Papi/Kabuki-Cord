from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

from .approvals import ApprovalQueue
from .browser import DiscordWebSession, discord_login_blocker_message
from .budget import BudgetManager
from .character import CharacterCardStore
from .character_memory import CharacterMemoryStore
from .config import AppConfig
from .discord_text import clean_discord_display_name
from .events import EventLog
from .llm import ReplyPlanner
from .memory import ConversationMemory
from .reaction_ledger import ReactionLedger
from .reactions import should_auto_react
from .reply_ledger import ReplyLedger, duplicate_reply_message
from .secrets import get_discord_credentials
from .topics import TopicTracker
from .user_instructions import UserInstructionStore


log = logging.getLogger(__name__)


class NhiZuesRunner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.memory = ConversationMemory(config.state_dir / "memory.json")
        self.topics = TopicTracker()
        self.budget = BudgetManager(
            config.state_dir / "usage.json",
            model=config.openai_model,
            max_daily_usd=config.max_daily_usd,
            max_session_usd=config.max_session_usd,
            max_calls_per_run=config.max_llm_calls_per_run,
        )
        self.planner = ReplyPlanner(
            api_key=config.openai_api_key,
            model=config.openai_model,
            enabled=config.llm_enabled,
            generate_drafts=(config.runtime_mode != "dry") or config.draft_in_dry_run,
            conversation_reply_enabled=config.conversation_reply_enabled,
            budget=self.budget,
            max_output_tokens=config.max_output_tokens,
            max_input_chars=config.max_input_chars,
            proactive_approval_required=config.proactive_approval_required,
            writing_mistake_rate=config.writing_mistake_rate,
            writing_quirk=config.writing_quirk,
            writing_misspellings=config.writing_misspellings,
        )
        self.characters = CharacterCardStore(config.character_dir, config.character_card)
        self.character_memory = CharacterMemoryStore(config.state_dir / "character_memory")
        self.approvals = ApprovalQueue(config.state_dir / "approvals.json")
        self.reply_ledger = ReplyLedger(config.state_dir / "sent_replies.json")
        self.reaction_ledger = ReactionLedger(config.state_dir / "reactions.json")
        self.user_instructions = UserInstructionStore(config.state_dir / "user_instructions.json")
        self.events = EventLog(config.state_dir / "events.json")
        self._target_cursor = 0
        self._own_author_ids: set[str] = set()

    async def run_once(self) -> None:
        await self._run(loop=False)

    async def run_forever(self) -> None:
        await self._run(loop=True)

    async def run_until_stopped(
        self,
        stop_event,
        *,
        on_cycle=None,
        on_targets_planned=None,
        on_target_start=None,
        on_target_complete=None,
    ) -> None:
        await self._run(
            loop=True,
            stop_event=stop_event,
            on_cycle=on_cycle,
            on_targets_planned=on_targets_planned,
            on_target_start=on_target_start,
            on_target_complete=on_target_complete,
        )

    async def run_until_stopped_in_session(
        self,
        session: DiscordWebSession,
        stop_event,
        *,
        on_cycle=None,
        on_targets_planned=None,
        on_target_start=None,
        on_target_complete=None,
    ) -> None:
        await self._run_in_session(
            session,
            loop=True,
            stop_event=stop_event,
            on_cycle=on_cycle,
            on_targets_planned=on_targets_planned,
            on_target_start=on_target_start,
            on_target_complete=on_target_complete,
            verify_login=False,
        )

    async def _run(
        self,
        *,
        loop: bool,
        stop_event=None,
        on_cycle=None,
        on_targets_planned=None,
        on_target_start=None,
        on_target_complete=None,
    ) -> None:
        async with DiscordWebSession(
            self.config.profile_dir,
            browser_channel=self.config.browser_channel,
            headless=self.config.headless,
        ) as session:
            await self._run_in_session(
                session,
                loop=loop,
                stop_event=stop_event,
                on_cycle=on_cycle,
                on_targets_planned=on_targets_planned,
                on_target_start=on_target_start,
                on_target_complete=on_target_complete,
                verify_login=True,
            )

    async def _run_in_session(
        self,
        session: DiscordWebSession,
        *,
        loop: bool,
        stop_event=None,
        on_cycle=None,
        on_targets_planned=None,
        on_target_start=None,
        on_target_complete=None,
        verify_login: bool,
    ) -> None:
        if not self.config.channels:
            raise ValueError("Configure at least one channel in NHI_ZUES_CHANNELS.")

        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.memory.load()

        if verify_login:
            credentials = get_discord_credentials()
            logged_in = await session.login_if_needed(
                email=credentials.email,
                password=credentials.password,
                timeout_seconds=45,
                allow_human_challenge=False,
            )
        else:
            await session.open_home()
            logged_in = await session.is_logged_in()
        if not logged_in:
            raise RuntimeError(discord_login_blocker_message(await session.account_blocker_state()))
        await self._remember_current_account_id(session)

        last_checked: dict[tuple[str, str], float] = {}
        while not _stop_requested(stop_event):
            planned_targets = self._due_targets(last_checked, apply_limit=False) if loop else list(self.config.channels)
            targets = self._limit_targets(planned_targets) if loop else planned_targets
            if on_targets_planned:
                on_targets_planned(planned_targets)
            if targets:
                await self._process_channels(
                    session,
                    targets,
                    planned_targets=planned_targets,
                    stop_event=stop_event,
                    on_target_start=on_target_start,
                    on_target_complete=on_target_complete,
                )
                now = time.monotonic()
                for target in targets:
                    last_checked[(target.server_id, target.channel_id)] = now
            if not loop:
                return

            sleep_seconds = self.config.scanner_cycle_sleep_seconds if targets else min(
                self.config.poll_seconds,
                self.config.scanner_cycle_sleep_seconds,
            )
            if on_cycle:
                on_cycle(sleep_seconds)
            if await _sleep_interruptible(stop_event, sleep_seconds):
                return

    async def _remember_current_account_id(self, session: DiscordWebSession) -> None:
        try:
            account_id = await session.current_user_id()
        except Exception:
            return
        if not account_id:
            return
        own_ids = set(getattr(self, "_own_author_ids", set()))
        own_ids.add(str(account_id))
        self._own_author_ids = own_ids

    def _due_targets(self, last_checked: dict[tuple[str, str], float], *, apply_limit: bool = True):
        now = time.monotonic()
        due = []
        for target in self.config.channels:
            key = (target.server_id, target.channel_id)
            interval = target.poll_seconds or self.config.poll_seconds
            if key not in last_checked or now - last_checked[key] >= interval:
                due.append(target)
        if not apply_limit:
            return due
        return self._limit_targets(due)

    def _limit_targets(self, targets):
        limit = max(1, self.config.scanner_max_channels_per_cycle)
        all_targets = list(self.config.channels)
        if not targets or not all_targets:
            return []
        due_keys = {(target.server_id, target.channel_id) for target in targets}
        start = int(getattr(self, "_target_cursor", 0) or 0) % len(all_targets)
        selected = []
        last_index = start
        for offset in range(len(all_targets)):
            index = (start + offset) % len(all_targets)
            target = all_targets[index]
            if (target.server_id, target.channel_id) not in due_keys:
                continue
            selected.append(target)
            last_index = index
            if len(selected) >= limit:
                break
        if selected:
            self._target_cursor = (last_index + 1) % len(all_targets)
        return selected

    async def _process_channels(
        self,
        session: DiscordWebSession,
        targets,
        *,
        planned_targets=None,
        stop_event=None,
        on_target_start=None,
        on_target_complete=None,
    ) -> None:
        for index, target in enumerate(targets):
            if index > 0:
                await self._channel_pacing_delay()
            if on_target_start:
                planned = list(planned_targets or targets)
                try:
                    planned_index = next(
                        item_index
                        for item_index, item in enumerate(planned)
                        if item.server_id == target.server_id and item.channel_id == target.channel_id
                    )
                except StopIteration:
                    planned_index = index
                on_target_start(target, planned_index, planned)
            await self._raise_if_account_blocked(session, target)
            current_url = await session.navigate_channel(target.server_id, target.channel_id)
            await self._raise_if_account_blocked(session, target)
            if f"/{target.channel_id}" not in current_url:
                log.warning(
                    "channel=%s redirected to %s; account may not have access",
                    target.channel_id,
                    current_url,
                )
                self.events.add(
                    event_type="channel_unavailable",
                    server_id=target.server_id,
                    channel_id=target.channel_id,
                    summary=f"Checked channel but Discord redirected to {current_url}.",
                )
                if on_target_complete:
                    on_target_complete(target, 0, 0)
                continue

            if await self._channel_settle_delay(stop_event):
                return
            visible_messages = await session.read_visible_messages(target.server_id, target.channel_id)
            fresh = self.memory.ingest(target.channel_id, visible_messages)
            character = self.characters.for_server(target.server_id, target.character_card)
            character_names = (character.name, *character.aliases)
            own_author_ids = set(getattr(self, "_own_author_ids", set()))
            own_author_ids.update(
                _own_author_ids_from_messages(visible_messages, character_names=character_names)
            )
            self._own_author_ids = own_author_ids
            fresh = _without_own_messages(
                fresh,
                character_names=character_names,
                own_author_ids=own_author_ids,
            )
            reaction_candidates = _recent_reaction_candidates(
                visible_messages,
                fresh,
                character_names=character_names,
                own_author_ids=own_author_ids,
            )
            force_laugh_ids = _recent_non_own_message_ids(
                visible_messages,
                character_names=character_names,
                own_author_ids=own_author_ids,
                limit=5,
            )
            reacted_message_ids = await self._process_reactions(
                session,
                target,
                reaction_candidates,
                fresh_count=len(fresh),
                force_laugh_ids=force_laugh_ids,
                character_names=character_names,
                own_author_ids=own_author_ids,
            )
            reply_fresh = [
                message
                for message in fresh
                if message.message_id not in reacted_message_ids
            ]
            snapshot = self.topics.update(target.channel_id, fresh)
            context = self.memory.context(target.channel_id)
            user_memories = self.memory.user_context_for(context)
            user_notes = self.user_instructions.for_users(
                [user.user_key for user in user_memories],
                server_id=target.server_id,
                channel_id=target.channel_id,
            )
            card_id = target.character_card or self.config.character_card
            character_memory = self.character_memory.load(card_id)
            if not target.engage_enabled:
                log.info(
                    "server=%s channel=%s visible=%s fresh=%s engage=false",
                    target.server_id,
                    target.channel_id,
                    len(visible_messages),
                    len(fresh),
                )
                self.events.add(
                    event_type="channel_checked",
                    server_id=target.server_id,
                    channel_id=target.channel_id,
                    summary=(
                        f"Reviewed {len(visible_messages)} visible message(s), "
                        f"{len(fresh)} new; Engage is off."
                    ),
                )
                self.memory.save()
                if on_target_complete:
                    on_target_complete(target, len(visible_messages), len(fresh))
                continue

            decision = await self.planner.plan(
                channel_id=target.channel_id,
                character=character,
                character_memory=character_memory,
                new_messages=reply_fresh,
                context=context,
                topics=snapshot,
                user_memories=user_memories,
                user_instructions=user_notes,
            )

            log.info(
                "server=%s character=%s channel=%s visible=%s fresh=%s users=%s topics=%s decision=%s",
                target.server_id,
                character.name,
                target.channel_id,
                len(visible_messages),
                len(fresh),
                len(user_memories),
                snapshot.top_topics,
                decision.reason,
            )
            self.events.add(
                event_type="channel_checked",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    f"Reviewed {len(visible_messages)} visible message(s), "
                    f"{len(fresh)} new; {decision.reason}."
                ),
            )
            if decision.should_reply and decision.draft:
                source_ids = tuple(message.message_id for message in reply_fresh)
                duplicate_message = duplicate_reply_message(
                    self.reply_ledger.find_overlap(
                        channel_id=target.channel_id,
                        source_message_ids=source_ids,
                    )
                )
                if duplicate_message:
                    log.info("duplicate reply blocked channel=%s", target.channel_id)
                    self.events.add(
                        event_type="duplicate_reply_blocked",
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=duplicate_message,
                        draft=decision.draft,
                    )
                    self.memory.save()
                    continue

                if self.config.runtime_mode == "dry":
                    log.info("dry mode draft for %s: %s", target.channel_id, decision.draft)
                    self.events.add(
                        event_type="dry_run",
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=decision.reason,
                        draft=decision.draft,
                    )
                elif _requires_approval(
                    self.config.runtime_mode,
                    decision.engagement_type,
                    auto_respond_enabled=target.auto_respond_enabled,
                ):
                    approval_reason = _approval_gate_reason(
                        self.config.runtime_mode,
                        decision.engagement_type,
                        auto_respond_enabled=target.auto_respond_enabled,
                    )
                    approval_summary = (
                        f"{decision.reason}; queued for approval because {approval_reason}"
                        if approval_reason
                        else decision.reason
                    )
                    existing = self.approvals.find_source_overlap(
                        channel_id=target.channel_id,
                        source_message_ids=source_ids,
                    )
                    if existing:
                        self.events.add(
                            event_type="duplicate_reply_blocked",
                            server_id=target.server_id,
                            channel_id=target.channel_id,
                            summary=(
                                "Duplicate approval skipped: an approval is already queued "
                                "for one or more of the same source messages."
                            ),
                            draft=decision.draft,
                        )
                        self.memory.save()
                        continue
                    item = self.approvals.add(
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        character_name=character.name,
                        engagement_type=decision.engagement_type,
                        reason=approval_summary,
                        draft=decision.draft,
                        source_messages=fresh,
                    )
                    log.info("queued approval=%s channel=%s", item.approval_id, target.channel_id)
                    self.events.add(
                        event_type="approval_queued",
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=approval_summary,
                        draft=decision.draft,
                    )
                else:
                    guard_reason = _auto_reply_guard_reason(
                        self.config,
                        self.reply_ledger,
                        channel_id=target.channel_id,
                        visible_messages=visible_messages,
                        character_names=character_names,
                        own_author_ids=own_author_ids,
                    )
                    if guard_reason:
                        log.info(
                            "auto reply guard blocked server=%s channel=%s reason=%s",
                            target.server_id,
                            target.channel_id,
                            guard_reason,
                        )
                        self.events.add(
                            event_type="reply_guard_blocked",
                            server_id=target.server_id,
                            channel_id=target.channel_id,
                            summary=guard_reason,
                            draft=decision.draft,
                        )
                        self.memory.save()
                        continue
                    await session.send_message(
                        decision.draft,
                        typing_enabled=self.config.typing_indicator_enabled,
                        typing_min_seconds=self.config.typing_min_seconds,
                        typing_max_seconds=self.config.typing_max_seconds,
                        typing_chars_per_second=self.config.typing_chars_per_second,
                    )
                    self.events.add(
                        event_type="message_sent",
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=decision.reason,
                        draft=decision.draft,
                    )
                    self.reply_ledger.record(
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        mode="auto",
                        draft=decision.draft,
                        source_message_ids=source_ids,
                    )

            self.memory.save()
            if on_target_complete:
                on_target_complete(target, len(visible_messages), len(fresh))

    async def _channel_pacing_delay(self) -> None:
        lower = max(0.0, self.config.scanner_min_channel_delay_seconds)
        upper = max(lower, self.config.scanner_max_channel_delay_seconds)
        if upper <= 0:
            return
        await asyncio.sleep(random.uniform(lower, upper))

    async def _channel_settle_delay(self, stop_event=None) -> bool:
        return await _sleep_interruptible(stop_event, self.config.scanner_channel_settle_seconds)

    async def _raise_if_account_blocked(self, session: DiscordWebSession, target) -> None:
        state = await session.account_blocker_state()
        if not state.get("blocked"):
            return
        message = discord_login_blocker_message(state)
        self.events.add(
            event_type="discord_account_challenge",
            server_id=getattr(target, "server_id", ""),
            channel_id=getattr(target, "channel_id", ""),
            summary=message,
        )
        raise RuntimeError(message)

    async def _process_reactions(
        self,
        session: DiscordWebSession,
        target,
        candidates,
        *,
        fresh_count: int,
        force_laugh_ids: set[str] | None = None,
        character_names: tuple[str, ...] = (),
        own_author_ids: set[str] | None = None,
    ) -> set[str]:
        if not getattr(target, "react_enabled", False):
            return set()
        if self.config.runtime_mode == "dry":
            self.events.add(
                event_type="reaction_skipped",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    "React is enabled, but Dry Mode blocks Discord reactions. "
                    f"fresh={fresh_count}, candidates={len(candidates)}."
                ),
            )
            return set()
        if self.config.reaction_max_per_channel <= 0:
            self.events.add(
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
            and float(getattr(self.config, "reaction_force_laugh_percent", 0.0) or 0.0) > 0
        )
        force_window_cap = _reaction_window_cap(
            self.config.reaction_force_laugh_percent,
            len(force_laugh_ids),
        )
        force_window_used = (
            sum(
                1
                for message_id in force_laugh_ids
                if self.reaction_ledger.has_reacted_to_message(
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
            if len(reacted_message_ids) >= self.config.reaction_max_per_channel:
                cap_reached = True
                break
            in_force_window = message.message_id in force_laugh_ids
            if _is_own_message(
                message,
                character_names=character_names,
                own_author_ids=own_author_ids,
            ):
                own_skipped += 1
                last_reason = "message is from the configured character/account"
                continue
            if self.reaction_ledger.has_reacted_to_message(
                channel_id=message.channel_id,
                message_id=message.message_id,
            ):
                ledgered += 1
                continue
            if force_window_enabled and in_force_window and force_window_remaining <= 0:
                force_window_capped += 1
                last_reason = (
                    "rolling reaction percentage cap reached for the recent non-own message window"
                )
                continue
            should_react, emoji, reason = should_auto_react(
                message.text,
                threshold=self.config.reaction_threshold,
                sample_percent=self.config.reaction_sample_percent,
                force_laugh_percent=(
                    self.config.reaction_force_laugh_percent
                    if in_force_window
                    else 0.0
                ),
                emoji_override=self.config.reaction_emoji_override,
            )
            if not should_react:
                ineligible += 1
                last_reason = reason
                continue
            try:
                attempted += 1
                result = await session.add_reaction(message.message_id, emoji)
            except Exception as exc:
                failed += 1
                self.events.add(
                    event_type="reaction_failed",
                    server_id=target.server_id,
                    channel_id=target.channel_id,
                    summary=f"Could not add {emoji} reaction: {exc}",
                    draft=message.text,
                )
                return reacted_message_ids
            if not result.get("applied"):
                already_present += 1
                self.reaction_ledger.record(
                    server_id=target.server_id,
                    message=message,
                    emoji=emoji,
                    reason=f"already present from this account; {reason}",
                )
                if force_window_enabled and in_force_window:
                    force_window_remaining = max(0, force_window_remaining - 1)
                self.events.add(
                    event_type="reaction_already_present",
                    server_id=target.server_id,
                    channel_id=target.channel_id,
                    summary=(
                        f"{emoji} reaction was already present from this account on "
                        f"{message.author}; path={result.get('path') or 'existing'}."
                    ),
                    draft=message.text,
                )
                continue

            self.reaction_ledger.record(
                server_id=target.server_id,
                message=message,
                emoji=emoji,
                reason=reason,
            )
            self.events.add(
                event_type="reaction_added",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    f"Added {emoji} reaction to {message.author}: "
                    f"{reason}; path={result.get('path') or 'existing'}."
                ),
                draft=message.text,
            )
            reacted_message_ids.add(message.message_id)
            if force_window_enabled and in_force_window:
                force_window_remaining = max(0, force_window_remaining - 1)
        if not reacted_message_ids:
            self.events.add(
                event_type="reaction_scan",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    "React scan made no new reaction. "
                    f"fresh={fresh_count}, candidates={len(candidates)}, ledgered={ledgered}, "
                    f"ineligible={ineligible}, attempted={attempted}, already_present={already_present}, "
                    f"failed={failed}, own_skipped={own_skipped}, cap_reached={str(cap_reached).lower()}, "
                    f"threshold={self.config.reaction_threshold}, sample={self.config.reaction_sample_percent:g}%"
                    f", force_laugh={self.config.reaction_force_laugh_percent:g}%"
                    f", force_window={force_window_used}/{force_window_cap}/{len(force_laugh_ids)}"
                    f", force_window_capped={force_window_capped}"
                    + (f", last_skip={last_reason}" if last_reason else "")
                    + "."
                ),
            )
        return reacted_message_ids


def _without_own_messages(
    messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
):
    own_author_ids = own_author_ids or set()
    if not character_names and not own_author_ids:
        return list(messages)
    return [
        message
        for message in messages
        if not _is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
        )
    ]


def _recent_reaction_candidates(
    visible_messages,
    fresh_messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    max_visible: int = 12,
):
    candidates = []
    seen_ids = set()
    for message in _without_own_messages(
        fresh_messages,
        character_names=character_names,
        own_author_ids=own_author_ids,
    ):
        if message.message_id in seen_ids:
            continue
        candidates.append(message)
        seen_ids.add(message.message_id)
    for message in reversed(
        _without_own_messages(
            visible_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
        )
    ):
        if len(candidates) >= max_visible:
            break
        if message.message_id in seen_ids:
            continue
        candidates.append(message)
        seen_ids.add(message.message_id)
    return candidates


def _recent_non_own_message_ids(
    visible_messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    limit: int,
) -> set[str]:
    message_ids: list[str] = []
    for message in reversed(
        _without_own_messages(
            visible_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
        )
    ):
        message_id = str(getattr(message, "message_id", "") or "")
        if not message_id or message_id in message_ids:
            continue
        message_ids.append(message_id)
        if len(message_ids) >= limit:
            break
    return set(message_ids)


def _reaction_window_cap(percent: float, window_size: int) -> int:
    percent = max(0.0, min(float(percent or 0.0), 100.0))
    window_size = max(0, int(window_size or 0))
    return int(window_size * (percent / 100.0))


def _auto_reply_guard_reason(
    config: AppConfig,
    reply_ledger: ReplyLedger,
    *,
    channel_id: str,
    visible_messages,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    cooldown_seconds = max(0.0, float(getattr(config, "reply_cooldown_seconds", 0.0) or 0.0))
    if cooldown_seconds:
        latest = reply_ledger.latest_for_channel(channel_id=channel_id)
        latest_at = _reply_created_at(latest)
        if latest_at is not None:
            age_seconds = (now - latest_at).total_seconds()
            if age_seconds < cooldown_seconds:
                return (
                    "Auto reply blocked by channel cooldown: "
                    f"last sent {_format_seconds(age_seconds)} ago; "
                    f"cooldown is {_format_seconds(cooldown_seconds)}."
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
                f"{len(recent)} sent in the last {_format_seconds(window_seconds)}; "
                f"limit is {max_per_window}."
            )

    if bool(getattr(config, "reply_require_intervening_user", True)):
        streak_reason = _own_message_streak_guard_reason(
            visible_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
        )
        if streak_reason:
            return streak_reason

    return ""


def _own_message_streak_guard_reason(
    messages,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
) -> str:
    visible = list(messages or [])
    last_own_index = -1
    for index, message in enumerate(visible):
        if _is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
        ):
            last_own_index = index
    if last_own_index < 0:
        return ""
    for message in visible[last_own_index + 1 :]:
        if not _is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
        ):
            return ""
    return (
        "Auto reply blocked because the last visible message in this channel is already "
        "from the character. Waiting for another user before posting again."
    )


def _reply_created_at(reply) -> datetime | None:
    if reply is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(reply.created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _own_author_ids_from_messages(messages, *, character_names: tuple[str, ...]) -> set[str]:
    own_ids: set[str] = set()
    for message in messages or []:
        if not _is_character_author(getattr(message, "author", ""), character_names):
            continue
        author_id = str(getattr(message, "author_id", "") or "").strip()
        if author_id:
            own_ids.add(author_id)
    return own_ids


def _is_own_message(
    message,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
) -> bool:
    author_id = str(getattr(message, "author_id", "") or "").strip()
    if author_id and author_id in (own_author_ids or set()):
        return True
    return _is_character_author(getattr(message, "author", ""), character_names)


def _is_character_author(author: str, character_names: tuple[str, ...]) -> bool:
    cleaned_author = _normalize_author(author)
    if not cleaned_author:
        return False
    names = {_normalize_author(name) for name in character_names if name}
    if cleaned_author in names:
        return True
    compact_author = cleaned_author.replace(" ", "")
    return bool(compact_author and compact_author in {name.replace(" ", "") for name in names})


def _normalize_author(value: str) -> str:
    return " ".join(clean_discord_display_name(str(value or "")).lower().split())


def _format_seconds(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0))))
    minutes, remainder = divmod(value, 60)
    if minutes <= 0:
        return f"{remainder}s"
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {remainder:02d}s"


def _requires_approval(
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


def _approval_gate_reason(
    runtime_mode: str,
    engagement_type: str,
    *,
    auto_respond_enabled: bool,
) -> str:
    mode = str(runtime_mode or "dry").lower()
    kind = str(engagement_type or "").lower()
    if mode == "live_fire":
        return "Live Fire requires review for every draft"
    if not auto_respond_enabled:
        return "Auto is off for this channel"
    if mode == "semi_auto" and kind in {"proactive", "manual"}:
        return "Semi Auto reviews new starts and manual drafts"
    return ""


def _stop_requested(stop_event) -> bool:
    return bool(stop_event is not None and stop_event.is_set())


async def _sleep_interruptible(stop_event, seconds: float) -> bool:
    wait_seconds = max(0.0, float(seconds or 0.0))
    if wait_seconds <= 0:
        return _stop_requested(stop_event)
    if stop_event is not None:
        return bool(await asyncio.to_thread(stop_event.wait, wait_seconds))
    await asyncio.sleep(wait_seconds)
    return False
