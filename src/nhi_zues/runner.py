from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

from .approvals import ApprovalQueue
from .browser import DiscordWebSession, discord_login_blocker_message
from .budget import BudgetManager
from .character import CharacterCardStore
from .character_memory import CharacterMemoryStore
from .config import AppConfig
from .discarded_approvals import DiscardedApprovalStore, discarded_approval_message
from .events import EventLog
from .llm import ReplyPlanner
from .memory import ConversationMemory
from .output_guard import outgoing_block_reason
from .reaction_ledger import ReactionLedger
from .reaction_service import (
    process_reactions as _process_reactions_service,
    reaction_window_cap as _reaction_window_cap,  # noqa: F401 - compatibility export
    recent_non_own_message_ids as _recent_non_own_message_ids,
    recent_reaction_candidates as _recent_reaction_candidates,
    without_own_messages as _without_own_messages,
)
from .reply_policy import (
    approval_gate_reason as _approval_gate_reason,
    auto_reply_guard_reason as _auto_reply_guard_reason,
    own_author_ids_from_messages as _own_author_ids_from_messages,
    requires_approval as _requires_approval,
)
from .reply_ledger import ReplyLedger, duplicate_reply_message
from .safety_review import SafetyReviewQueue, detect_safety_review_findings
from . import scan_scheduler
from .secrets import get_discord_credentials
from .topics import TopicTracker
from .user_instructions import UserInstructionStore
from .models import DraftDecision, MessageRecord
from .transport import ChatTransport, TransportFactory


log = logging.getLogger(__name__)


@dataclass
class ChannelScanState:
    visible_messages: list[MessageRecord]
    fresh_messages: list[MessageRecord]
    character: object
    character_names: tuple[str, ...]
    own_message_ids: set[str]
    own_texts: set[str]
    own_author_ids: set[str]
    history_message_count: int = 0
    history_fresh_count: int = 0


@dataclass
class ReplyPlanningState:
    snapshot: object
    context: list[MessageRecord]
    user_memories: list
    user_notes: list
    character_memory: object


class NhiZuesRunner:
    def __init__(
        self,
        config: AppConfig,
        *,
        start_cursor: int = 0,
        completed_loop_count: int = 0,
        transport_factory: TransportFactory = DiscordWebSession,
    ) -> None:
        self.config = config
        self.transport_factory = transport_factory
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
        self.discarded_approvals = DiscardedApprovalStore(config.state_dir / "discarded_approvals.json")
        self.reply_ledger = ReplyLedger(config.state_dir / "sent_replies.json")
        self.reaction_ledger = ReactionLedger(config.state_dir / "reactions.json")
        self.safety_reviews = SafetyReviewQueue(config.state_dir / "safety_review.json")
        self.user_instructions = UserInstructionStore(config.state_dir / "user_instructions.json")
        self.events = EventLog(config.state_dir / "events.json")
        channel_count = len(config.channels)
        self._target_cursor = int(start_cursor or 0) % channel_count if channel_count else 0
        self._completed_loop_count = max(0, int(completed_loop_count or 0))
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
        session: ChatTransport,
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
        async with self.transport_factory(
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
        session: ChatTransport,
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
        await self._prepare_discord_session(session, verify_login=verify_login)
        await self._run_scan_cycles(
            session,
            loop=loop,
            stop_event=stop_event,
            on_cycle=on_cycle,
            on_targets_planned=on_targets_planned,
            on_target_start=on_target_start,
            on_target_complete=on_target_complete,
        )

    async def _prepare_discord_session(
        self,
        session: ChatTransport,
        *,
        verify_login: bool,
    ) -> None:
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

    async def _run_scan_cycles(
        self,
        session: ChatTransport,
        *,
        loop: bool,
        stop_event=None,
        on_cycle=None,
        on_targets_planned=None,
        on_target_start=None,
        on_target_complete=None,
    ) -> None:
        while not _stop_requested(stop_event):
            planned_targets, targets, will_complete_loop, completed_in_loop = self._cycle_targets(loop)
            loop_state = self._loop_state(
                planned_targets=planned_targets,
                selected_targets=targets,
                will_complete_loop=will_complete_loop,
                completed_in_loop=completed_in_loop,
            )
            if on_targets_planned:
                on_targets_planned(planned_targets, loop_state)
            if targets:
                await self._process_channels(
                    session,
                    targets,
                    planned_targets=planned_targets,
                    loop_state=loop_state,
                    stop_event=stop_event,
                    on_target_start=on_target_start,
                    on_target_complete=on_target_complete,
                )
                if loop and will_complete_loop:
                    self._completed_loop_count = int(getattr(self, "_completed_loop_count", 0) or 0) + 1
            if not loop:
                return

            sleep_seconds = self.config.scanner_cycle_sleep_seconds
            loop_state = self._loop_state(
                planned_targets=self._planned_targets(),
                selected_targets=(),
                will_complete_loop=False,
            )
            if on_cycle:
                on_cycle(sleep_seconds, loop_state)
            if await _sleep_interruptible(stop_event, sleep_seconds):
                return

    def _cycle_targets(self, loop: bool) -> tuple[list, list, bool, int]:
        planned_targets = self._planned_targets() if loop else list(self.config.channels)
        if not loop:
            return planned_targets, planned_targets, True, 0
        completed_in_loop = self._loop_cursor()
        targets, will_complete_loop = self._select_targets(planned_targets)
        return planned_targets, targets, will_complete_loop, completed_in_loop

    async def _remember_current_account_id(self, session: ChatTransport) -> None:
        try:
            account_id = await session.current_user_id()
        except Exception:
            return
        if not account_id:
            return
        own_ids = set(getattr(self, "_own_author_ids", set()))
        own_ids.add(str(account_id))
        self._own_author_ids = own_ids

    def _planned_targets(self):
        return scan_scheduler.planned_targets(self.config, getattr(self, "_target_cursor", 0))

    def _active_targets(self):
        return scan_scheduler.active_targets(self.config)

    def _select_targets(self, targets):
        selected, next_cursor, completed_loop = scan_scheduler.select_targets(
            self.config,
            getattr(self, "_target_cursor", 0),
            targets,
        )
        self._target_cursor = next_cursor
        return selected, completed_loop

    def _limit_targets(self, targets):
        selected, next_cursor = scan_scheduler.limit_targets(
            self.config,
            targets,
            getattr(self, "_target_cursor", 0),
        )
        self._target_cursor = next_cursor
        return selected

    def _loop_cursor(self) -> int:
        return scan_scheduler.normalized_cursor(self.config, getattr(self, "_target_cursor", 0))

    def _target_index(self, target) -> int:
        return scan_scheduler.target_index(self.config, target)

    def _loop_state(
        self,
        *,
        planned_targets,
        selected_targets,
        will_complete_loop: bool,
        target=None,
        completed_in_loop: int | None = None,
    ) -> dict[str, int | bool]:
        return scan_scheduler.loop_state(
            self.config,
            getattr(self, "_target_cursor", 0),
            getattr(self, "_completed_loop_count", 0),
            planned_targets=planned_targets,
            selected_targets=selected_targets,
            will_complete_loop=will_complete_loop,
            target=target,
            completed_in_loop=completed_in_loop,
        )

    async def _process_channels(
        self,
        session: ChatTransport,
        targets,
        *,
        planned_targets=None,
        loop_state=None,
        stop_event=None,
        on_target_start=None,
        on_target_complete=None,
    ) -> None:
        planned = list(planned_targets or targets)
        for index, target in enumerate(targets):
            if index > 0:
                await self._channel_pacing_delay()
            self._notify_target_start(
                target,
                index,
                targets,
                planned,
                loop_state,
                on_target_start,
            )
            if not await self._open_channel_or_record_unavailable(session, target):
                self._notify_target_complete(
                    target,
                    targets,
                    planned,
                    loop_state,
                    on_target_complete,
                    visible_count=0,
                    fresh_count=0,
                )
                continue

            if await self._channel_settle_delay(stop_event):
                return

            state = await self._capture_channel_state(session, target)
            if getattr(target, "safety_review_enabled", False):
                visible_count, fresh_count = await self._process_safety_review_channel(
                    session,
                    target,
                    state,
                )
            else:
                await self._process_regular_channel(session, target, state)
                visible_count = len(state.visible_messages)
                fresh_count = len(state.fresh_messages)

            self._notify_target_complete(
                target,
                targets,
                planned,
                loop_state,
                on_target_complete,
                visible_count=visible_count,
                fresh_count=fresh_count,
            )

    def _notify_target_start(
        self,
        target,
        fallback_index: int,
        targets,
        planned: list,
        loop_state,
        callback,
    ) -> None:
        if not callback:
            return
        planned_index = self._planned_index(planned, target, fallback=fallback_index)
        target_index = self._target_index(target)
        target_loop_state = self._loop_state(
            planned_targets=planned,
            selected_targets=targets,
            will_complete_loop=bool((loop_state or {}).get("will_complete_loop")),
            target=target,
            completed_in_loop=max(0, target_index),
        )
        callback(target, planned_index, planned, target_loop_state)

    def _notify_target_complete(
        self,
        target,
        targets,
        planned: list,
        loop_state,
        callback,
        *,
        visible_count: int,
        fresh_count: int,
    ) -> None:
        if not callback:
            return
        target_index = self._target_index(target)
        complete_loop_state = self._loop_state(
            planned_targets=planned,
            selected_targets=targets,
            will_complete_loop=bool((loop_state or {}).get("will_complete_loop")),
            target=target,
            completed_in_loop=max(0, target_index + 1),
        )
        callback(target, visible_count, fresh_count, complete_loop_state)

    @staticmethod
    def _planned_index(planned: list, target, *, fallback: int) -> int:
        try:
            return next(
                item_index
                for item_index, item in enumerate(planned)
                if item.server_id == target.server_id and item.channel_id == target.channel_id
            )
        except StopIteration:
            return fallback

    async def _open_channel_or_record_unavailable(
        self,
        session: ChatTransport,
        target,
    ) -> bool:
        await self._raise_if_account_blocked(session, target)
        current_url = await session.navigate_channel(target.server_id, target.channel_id)
        await self._raise_if_account_blocked(session, target)
        if f"/{target.channel_id}" in current_url:
            return True
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
        return False

    async def _capture_channel_state(
        self,
        session: ChatTransport,
        target,
    ) -> ChannelScanState:
        visible_messages = await session.read_visible_messages(target.server_id, target.channel_id)
        fresh_messages = self.memory.ingest(target.channel_id, visible_messages)
        history_message_count = 0
        history_fresh_count = 0
        if self._scanner_history_backfill_enabled(target):
            history_messages = await self._read_scan_history(session, target)
            history_message_count = len(history_messages)
            if history_messages:
                history_fresh_count = len(self.memory.ingest(target.channel_id, history_messages))
                await session.ensure_latest_messages_visible()
        self.memory.save()
        character = self.characters.for_server(target.server_id, target.character_card)
        character_names = (character.name, *character.aliases)
        own_message_ids = self.reply_ledger.own_message_ids_for_channel(channel_id=target.channel_id)
        own_texts = self.reply_ledger.own_texts_for_channel(channel_id=target.channel_id)
        own_author_ids = self._update_own_author_ids(
            visible_messages,
            character_names=character_names,
            own_texts=own_texts,
        )
        fresh_messages = _without_own_messages(
            fresh_messages,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )
        return ChannelScanState(
            visible_messages=visible_messages,
            fresh_messages=fresh_messages,
            character=character,
            character_names=character_names,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
            own_author_ids=own_author_ids,
            history_message_count=history_message_count,
            history_fresh_count=history_fresh_count,
        )

    def _scanner_history_backfill_enabled(self, target) -> bool:
        if getattr(target, "safety_review_enabled", False):
            return False
        return int(getattr(self.config, "scanner_history_backfill_limit", 0) or 0) > 0

    async def _read_scan_history(self, session: ChatTransport, target) -> list[MessageRecord]:
        limit = max(0, int(getattr(self.config, "scanner_history_backfill_limit", 0) or 0))
        if limit <= 0:
            return []
        scroll_rounds = max(1, int(getattr(self.config, "scanner_history_scroll_rounds", 8) or 8))
        try:
            return await session.read_channel_history(
                target.server_id,
                target.channel_id,
                limit=limit,
                scroll_rounds=scroll_rounds,
            )
        except Exception as exc:
            log.warning(
                "server=%s channel=%s scan_history_backfill_failed=%s",
                target.server_id,
                target.channel_id,
                exc,
            )
            self.events.add(
                event_type="channel_history_backfill_failed",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=f"Scanner could not refresh channel history during this visit: {exc}",
            )
            return []

    def _update_own_author_ids(
        self,
        messages: list[MessageRecord],
        *,
        character_names: tuple[str, ...],
        own_texts,
    ) -> set[str]:
        own_author_ids = set(getattr(self, "_own_author_ids", set()))
        own_author_ids.update(
            _own_author_ids_from_messages(
                messages,
                character_names=character_names,
                own_texts=own_texts,
            )
        )
        self._own_author_ids = own_author_ids
        return own_author_ids

    async def _process_safety_review_channel(
        self,
        session: ChatTransport,
        target,
        state: ChannelScanState,
    ) -> tuple[int, int]:
        review_source, fresh_messages, review_source_label = await self._read_safety_review_source(
            session,
            target,
            state,
        )
        review_messages = _without_own_messages(
            review_source,
            character_names=state.character_names,
            own_author_ids=state.own_author_ids,
            own_message_ids=state.own_message_ids,
            own_texts=state.own_texts,
        )
        findings = detect_safety_review_findings(review_messages)
        added = self.safety_reviews.add_findings(
            server_id=target.server_id,
            server_label=getattr(target, "server_label", ""),
            channel_id=target.channel_id,
            channel_label=getattr(target, "label", ""),
            findings=findings,
        )
        event_type = "safety_review_flagged" if added else "safety_review_scan"
        sweep_scope = (
            "other servers are skipped"
            if getattr(self.config, "safety_review_exclusive", True)
            else "other observed channels stay in rotation"
        )
        self.events.add(
            event_type=event_type,
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                f"Dojo Sweep scanned {len(review_messages)} non-own {review_source_label} message(s), "
                f"{len(fresh_messages)} new; queued {len(added)} new review item(s). "
                f"Replies/reactions are disabled for this sweep target; {sweep_scope}."
            ),
            draft="\n".join(item.text for item in added[:3]),
        )
        log.info(
            "server=%s channel=%s safety_review=true source=%s scanned=%s fresh=%s queued=%s",
            target.server_id,
            target.channel_id,
            review_source_label,
            len(review_messages),
            len(fresh_messages),
            len(added),
        )
        self.memory.save()
        return len(review_source), len(fresh_messages)

    async def _read_safety_review_source(
        self,
        session: ChatTransport,
        target,
        state: ChannelScanState,
    ) -> tuple[list[MessageRecord], list[MessageRecord], str]:
        try:
            review_source = await session.read_channel_history(
                target.server_id,
                target.channel_id,
                limit=int(getattr(self.config, "safety_review_history_limit", 420) or 420),
                scroll_rounds=int(getattr(self.config, "safety_review_scroll_rounds", 45) or 45),
            )
        except Exception as exc:
            log.warning(
                "server=%s channel=%s safety_review_history_failed=%s",
                target.server_id,
                target.channel_id,
                exc,
            )
            self.events.add(
                event_type="safety_review_scan",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    "Dojo Sweep could not back-scroll channel history, so it fell back "
                    f"to {len(state.visible_messages)} currently visible message(s): {exc}"
                ),
            )
            return state.visible_messages, state.fresh_messages, "visible"

        if not review_source:
            diagnostics = await self._message_dom_diagnostics(session, target)
            diagnostic_summary = _format_safety_review_dom_diagnostics(diagnostics)
            if state.visible_messages:
                self.events.add(
                    event_type="safety_review_scan",
                    server_id=target.server_id,
                    channel_id=target.channel_id,
                    summary=(
                        "Dojo Sweep found no extractable back-scroll history rows "
                        f"({diagnostic_summary}), so it fell back to "
                        f"{len(state.visible_messages)} currently visible message(s)."
                    ),
                )
                return state.visible_messages, state.fresh_messages, "visible"
            self.events.add(
                event_type="safety_review_scan",
                server_id=target.server_id,
                channel_id=target.channel_id,
                summary=(
                    "Dojo Sweep found no extractable history or visible message rows "
                    f"({diagnostic_summary}). Discord may not have loaded readable "
                    "message rows for this channel yet."
                ),
            )
            return [], [], "history-empty"

        fresh_messages = self.memory.ingest(target.channel_id, review_source)
        state.own_author_ids = self._update_own_author_ids(
            review_source,
            character_names=state.character_names,
            own_texts=state.own_texts,
        )
        return review_source, fresh_messages, "history"

    async def _message_dom_diagnostics(self, session: ChatTransport, target) -> dict[str, object]:
        diagnostics = getattr(session, "message_dom_diagnostics", None)
        if not callable(diagnostics):
            return {}
        try:
            result = await diagnostics()
        except Exception as exc:
            log.warning(
                "server=%s channel=%s safety_review_dom_diagnostics_failed=%s",
                target.server_id,
                target.channel_id,
                exc,
            )
            return {"diagnostic_error": str(exc)}
        return result if isinstance(result, dict) else {}

    async def _process_regular_channel(
        self,
        session: ChatTransport,
        target,
        state: ChannelScanState,
    ) -> None:
        reacted_message_ids = await self._process_channel_reactions(session, target, state)
        reply_fresh = [
            message
            for message in state.fresh_messages
            if message.message_id not in reacted_message_ids
        ]
        planning = self._build_reply_planning_state(target, state)
        if not target.engage_enabled:
            self._record_engage_disabled(target, state)
            self.memory.save()
            return

        decision = await self.planner.plan(
            channel_id=target.channel_id,
            character=state.character,
            character_memory=planning.character_memory,
            new_messages=reply_fresh,
            context=planning.context,
            topics=planning.snapshot,
            user_memories=planning.user_memories,
            user_instructions=planning.user_notes,
        )
        self._record_planner_decision(target, state, planning, decision)
        await self._handle_reply_decision(session, target, state, decision, reply_fresh)
        self.memory.save()

    async def _process_channel_reactions(
        self,
        session: ChatTransport,
        target,
        state: ChannelScanState,
    ) -> set[str]:
        reaction_candidates = _recent_reaction_candidates(
            state.visible_messages,
            state.fresh_messages,
            character_names=state.character_names,
            own_author_ids=state.own_author_ids,
            own_message_ids=state.own_message_ids,
            own_texts=state.own_texts,
        )
        force_laugh_ids = _recent_non_own_message_ids(
            state.visible_messages,
            character_names=state.character_names,
            own_author_ids=state.own_author_ids,
            own_message_ids=state.own_message_ids,
            own_texts=state.own_texts,
            limit=5,
        )
        return await self._process_reactions(
            session,
            target,
            reaction_candidates,
            fresh_count=len(state.fresh_messages),
            force_laugh_ids=force_laugh_ids,
            character_names=state.character_names,
            own_author_ids=state.own_author_ids,
            own_message_ids=state.own_message_ids,
            own_texts=state.own_texts,
        )

    def _build_reply_planning_state(self, target, state: ChannelScanState) -> ReplyPlanningState:
        snapshot = self.topics.update(target.channel_id, state.fresh_messages)
        context = self.memory.context(target.channel_id, limit=80)
        user_memories = self.memory.user_context_for(context, limit=10)
        user_notes = self.user_instructions.for_users(
            [user.user_key for user in user_memories],
            server_id=target.server_id,
            channel_id=target.channel_id,
        )
        card_id = target.character_card or self.config.character_card
        character_memory = self.character_memory.load(card_id)
        return ReplyPlanningState(
            snapshot=snapshot,
            context=context,
            user_memories=user_memories,
            user_notes=user_notes,
            character_memory=character_memory,
        )

    def _record_engage_disabled(self, target, state: ChannelScanState) -> None:
        log.info(
            "server=%s channel=%s visible=%s fresh=%s engage=false",
            target.server_id,
            target.channel_id,
            len(state.visible_messages),
            len(state.fresh_messages),
        )
        self.events.add(
            event_type="channel_checked",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                f"Reviewed {len(state.visible_messages)} visible message(s), "
                f"{len(state.fresh_messages)} new; Engage is off."
                f"{_scan_history_summary(state)}"
            ),
        )

    def _record_planner_decision(
        self,
        target,
        state: ChannelScanState,
        planning: ReplyPlanningState,
        decision: DraftDecision,
    ) -> None:
        log.info(
            "server=%s character=%s channel=%s visible=%s fresh=%s users=%s topics=%s decision=%s",
            target.server_id,
            state.character.name,
            target.channel_id,
            len(state.visible_messages),
            len(state.fresh_messages),
            len(planning.user_memories),
            planning.snapshot.top_topics,
            decision.reason,
        )
        self.events.add(
            event_type="channel_checked",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=(
                f"Reviewed {len(state.visible_messages)} visible message(s), "
                f"{len(state.fresh_messages)} new; {decision.reason}."
                f"{_scan_history_summary(state)}"
            ),
        )

    async def _handle_reply_decision(
        self,
        session: ChatTransport,
        target,
        state: ChannelScanState,
        decision: DraftDecision,
        reply_fresh: list[MessageRecord],
    ) -> None:
        if not decision.should_reply or not decision.draft:
            return
        if self._record_output_block_if_needed(target, decision):
            return
        source_ids = tuple(decision.source_message_ids or tuple(message.message_id for message in reply_fresh))
        source_messages = _messages_by_ids(state.fresh_messages, source_ids) or _messages_by_ids(reply_fresh, source_ids) or reply_fresh
        if self._record_discarded_source_if_needed(target, decision, source_ids):
            return
        if self._record_duplicate_reply_if_needed(target, decision, source_ids):
            return
        if self.config.runtime_mode == "dry":
            self._record_dry_run_decision(target, decision)
            return
        if _requires_approval(
            self.config.runtime_mode,
            decision.engagement_type,
            auto_respond_enabled=target.auto_respond_enabled,
        ):
            self._queue_approval_decision(target, state, decision, source_ids, source_messages)
            return
        await self._send_auto_reply_decision(session, target, state, decision, source_ids, source_messages)

    def _record_output_block_if_needed(self, target, decision: DraftDecision) -> bool:
        output_block = outgoing_block_reason(decision.draft)
        if not output_block:
            return False
        log.info("output guard blocked draft channel=%s", target.channel_id)
        self.events.add(
            event_type="output_guard_blocked",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=output_block,
            draft=decision.draft,
        )
        return True

    def _record_discarded_source_if_needed(
        self,
        target,
        decision: DraftDecision,
        source_ids: tuple[str, ...],
    ) -> bool:
        discarded_message = discarded_approval_message(
            self.discarded_approvals.find_overlap(
                channel_id=target.channel_id,
                source_message_ids=source_ids,
            )
        )
        if not discarded_message:
            return False
        log.info("discarded approval suppressed channel=%s", target.channel_id)
        self.events.add(
            event_type="discarded_approval_suppressed",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=discarded_message,
            draft=decision.draft,
        )
        return True

    def _record_duplicate_reply_if_needed(
        self,
        target,
        decision: DraftDecision,
        source_ids: tuple[str, ...],
    ) -> bool:
        duplicate_message = duplicate_reply_message(
            self.reply_ledger.find_overlap(
                channel_id=target.channel_id,
                source_message_ids=source_ids,
            )
        )
        if not duplicate_message:
            return False
        log.info("duplicate reply blocked channel=%s", target.channel_id)
        self.events.add(
            event_type="duplicate_reply_blocked",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=duplicate_message,
            draft=decision.draft,
        )
        return True

    def _record_dry_run_decision(self, target, decision: DraftDecision) -> None:
        log.info("dry mode draft for %s: %s", target.channel_id, decision.draft)
        self.events.add(
            event_type="dry_run",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=decision.reason,
            draft=decision.draft,
        )

    def _queue_approval_decision(
        self,
        target,
        state: ChannelScanState,
        decision: DraftDecision,
        source_ids: tuple[str, ...],
        source_messages: list[MessageRecord],
    ) -> None:
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
            return
        item = self.approvals.add(
            server_id=target.server_id,
            channel_id=target.channel_id,
            character_name=state.character.name,
            engagement_type=decision.engagement_type,
            reason=approval_summary,
            draft=decision.draft,
            source_messages=source_messages,
        )
        log.info("queued approval=%s channel=%s", item.approval_id, target.channel_id)
        self.events.add(
            event_type="approval_queued",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=approval_summary,
            draft=decision.draft,
        )

    async def _send_auto_reply_decision(
        self,
        session: ChatTransport,
        target,
        state: ChannelScanState,
        decision: DraftDecision,
        source_ids: tuple[str, ...],
        source_messages: list[MessageRecord],
    ) -> None:
        guard_reason = _auto_reply_guard_reason(
            self.config,
            self.reply_ledger,
            channel_id=target.channel_id,
            visible_messages=state.visible_messages,
            character_names=state.character_names,
            own_author_ids=state.own_author_ids,
            own_message_ids=state.own_message_ids,
            own_texts=state.own_texts,
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
            return
        delivery = await session.send_message(
            decision.draft,
            typing_enabled=self.config.typing_indicator_enabled,
            typing_min_seconds=self.config.typing_min_seconds,
            typing_max_seconds=self.config.typing_max_seconds,
            typing_chars_per_second=self.config.typing_chars_per_second,
        )
        target_message = source_messages[-1] if source_messages else None
        self.events.add(
            event_type="message_sent",
            server_id=target.server_id,
            channel_id=target.channel_id,
            summary=decision.reason,
            draft=decision.draft,
            message_id=str(delivery.get("message_id") or ""),
            target_message_id=str(source_ids[-1] if source_ids else ""),
            target_author=str(getattr(target_message, "author", "") or ""),
        )
        self.reply_ledger.record(
            server_id=target.server_id,
            channel_id=target.channel_id,
            mode="auto",
            draft=decision.draft,
            source_message_ids=source_ids,
            message_id=str(delivery.get("message_id") or ""),
        )

    async def _channel_pacing_delay(self) -> None:
        lower = max(0.0, self.config.scanner_min_channel_delay_seconds)
        upper = max(lower, self.config.scanner_max_channel_delay_seconds)
        if upper <= 0:
            return
        await asyncio.sleep(random.uniform(lower, upper))

    async def _channel_settle_delay(self, stop_event=None) -> bool:
        return await _sleep_interruptible(stop_event, self.config.scanner_channel_settle_seconds)

    async def _raise_if_account_blocked(self, session: ChatTransport, target) -> None:
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
        session: ChatTransport,
        target,
        candidates,
        *,
        fresh_count: int,
        force_laugh_ids: set[str] | None = None,
        character_names: tuple[str, ...] = (),
        own_author_ids: set[str] | None = None,
        own_message_ids: set[str] | None = None,
        own_texts: set[str] | None = None,
    ) -> set[str]:
        return await _process_reactions_service(
            config=self.config,
            events=self.events,
            reaction_ledger=self.reaction_ledger,
            session=session,
            target=target,
            candidates=candidates,
            fresh_count=fresh_count,
            force_laugh_ids=force_laugh_ids,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )


def _messages_by_ids(messages: list[MessageRecord], message_ids: tuple[str, ...]) -> list[MessageRecord]:
    wanted = {str(message_id) for message_id in message_ids if str(message_id or "").strip()}
    if not wanted:
        return []
    return [message for message in messages if message.message_id in wanted]


def _scan_history_summary(state: ChannelScanState) -> str:
    history_count = int(getattr(state, "history_message_count", 0) or 0)
    if history_count <= 0:
        return ""
    fresh_count = int(getattr(state, "history_fresh_count", 0) or 0)
    return f" Scanner history refresh read {history_count}, {fresh_count} new to memory."


def _format_safety_review_dom_diagnostics(diagnostics: dict[str, object]) -> str:
    if not diagnostics:
        return "no DOM diagnostics available"
    if diagnostics.get("diagnostic_error"):
        return f"diagnostics failed: {diagnostics.get('diagnostic_error')}"
    fields = (
        ("raw_chat_nodes", "raw"),
        ("valid_message_id_nodes", "valid"),
        ("text_rows", "text"),
        ("empty_text_rows", "empty"),
        ("first_id", "first"),
        ("last_id", "last"),
    )
    parts = [
        f"{label}={diagnostics.get(key)}"
        for key, label in fields
        if diagnostics.get(key) not in (None, "")
    ]
    url = str(diagnostics.get("url") or "").strip()
    if url:
        parts.append(f"url={url[:120]}")
    preview = " ".join(str(diagnostics.get("body_preview") or "").split())
    if preview:
        parts.append(f"body={preview[:120]}")
    return ", ".join(parts) or "no DOM diagnostics available"


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
