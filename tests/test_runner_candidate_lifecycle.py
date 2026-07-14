from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.approvals import ApprovalQueue
from nhi_zues.budget import BudgetManager
from nhi_zues.character import CharacterCard
from nhi_zues.config import ChannelTarget
from nhi_zues.llm import ReplyPlanner
from nhi_zues.memory import ConversationMemory
from nhi_zues.models import DraftDecision, MessageRecord
from nhi_zues.runner import NhiZuesRunner
from nhi_zues.topics import TopicTracker


SERVER_ID = "server-1"
CHANNEL_ID = "channel-1"


def message(message_id: str, text: str, *, author: str = "Rook") -> MessageRecord:
    return MessageRecord(
        server_id=SERVER_ID,
        channel_id=CHANNEL_ID,
        message_id=message_id,
        author=author,
        author_id=f"user-{author.lower()}",
        text=text,
    )


class EventSink:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, **kwargs) -> None:
        self.items.append(kwargs)


class CharacterStoreStub:
    character = CharacterCard(
        name="Test Character",
        system_prompt="Stay concise.",
        style_rules=(),
        engagement_rules=(),
        response_moves=(),
        voice_examples=(),
        avoid_examples=(),
        aliases=("test",),
        trigger_keywords=("audio",),
    )

    def for_server(self, server_id: str, card: str | None):
        return self.character


class ReplyLedgerStub:
    def own_message_ids_for_channel(self, *, channel_id: str) -> set[str]:
        return set()

    def own_texts_for_channel(self, *, channel_id: str) -> set[str]:
        return set()

    def find_overlap(self, *, channel_id: str, source_message_ids):
        return []


class DiscardedApprovalStub:
    def find_overlap(self, *, channel_id: str, source_message_ids):
        return []


class VisibleMessageSession:
    def __init__(self) -> None:
        self.visible: list[MessageRecord] = []

    async def read_visible_messages(
        self,
        server_id: str,
        channel_id: str,
    ) -> list[MessageRecord]:
        return list(self.visible)


class ReactionRecorder:
    def __init__(self, *, applied_ids: set[str] | None = None) -> None:
        self.applied_ids = set(applied_ids or ())
        self.calls: list[list[str]] = []

    async def __call__(self, session, target, candidates, **kwargs) -> set[str]:
        candidate_ids = [item.message_id for item in candidates]
        self.calls.append(candidate_ids)
        if not target.react_enabled:
            return set()
        return set(candidate_ids).intersection(self.applied_ids)


class AccumulatingPlanner:
    """Defers one fragment and drafts only after a second fragment arrives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def plan(self, **kwargs) -> DraftDecision:
        source_ids = tuple(item.message_id for item in kwargs["new_messages"])
        self.calls.append(source_ids)
        if len(source_ids) == 1:
            return DraftDecision(
                False,
                "candidate needs adjacent context",
                source_message_ids=source_ids,
                reason_code="awaiting_context",
            )
        return DraftDecision(
            True,
            "two adjacent fragments form a grounded reply opportunity",
            draft="the cleaner edit still losing detail is the interesting part",
            engagement_type="conversation",
            source_message_ids=source_ids,
            reason_code="thread_continuation",
            eligible_source_count=len(source_ids),
            model_call_count=1,
        )


class PlannerRaises:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, **kwargs) -> DraftDecision:
        self.calls += 1
        raise RuntimeError("planner exploded")


class EligibleWithoutDraftPlanner:
    def __init__(self, reserved_id: str) -> None:
        self.reserved_id = reserved_id
        self.calls: list[tuple[str, ...]] = []

    async def plan(self, **kwargs) -> DraftDecision:
        self.calls.append(tuple(item.message_id for item in kwargs["new_messages"]))
        return DraftDecision(
            True,
            "reply candidate is eligible but generation is unavailable",
            draft=None,
            engagement_type="conversation",
            source_message_ids=(self.reserved_id,),
            reason_code="model_unavailable",
            eligible_source_count=1,
        )


class HardSkipPlanner:
    async def plan(self, **kwargs) -> DraftDecision:
        source_ids = tuple(item.message_id for item in kwargs["new_messages"])
        return DraftDecision(
            False,
            "candidate has no reply cue",
            source_message_ids=source_ids,
            reason_code="conversation_disabled",
        )


class AlwaysDeferredPlanner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def plan(self, **kwargs) -> DraftDecision:
        source_ids = tuple(item.message_id for item in kwargs["new_messages"])
        self.calls.append(source_ids)
        return DraftDecision(
            False,
            "candidate still needs more context",
            source_message_ids=source_ids,
            reason_code="awaiting_context",
        )


class DraftingPlanner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def plan(self, **kwargs) -> DraftDecision:
        source_ids = tuple(item.message_id for item in kwargs["new_messages"])
        self.calls.append(source_ids)
        return DraftDecision(
            True,
            "changed planner settings can now produce a draft",
            draft="changed settings now allow this draft",
            engagement_type="conversation",
            source_message_ids=source_ids,
            reason_code="compact_opinion",
            eligible_source_count=len(source_ids),
        )


class CountingPlanner:
    def __init__(self, delegate: ReplyPlanner) -> None:
        self.delegate = delegate
        self.calls: list[tuple[str, ...]] = []
        self.decisions: list[DraftDecision] = []

    async def plan(self, **kwargs) -> DraftDecision:
        self.calls.append(tuple(item.message_id for item in kwargs["new_messages"]))
        decision = await self.delegate.plan(**kwargs)
        self.decisions.append(decision)
        return decision


def real_planner(
    root: Path,
    *,
    conversation_reply_enabled: bool,
) -> CountingPlanner:
    budget = BudgetManager(
        root / "usage.json",
        model="gpt-5.4-mini",
        max_daily_usd=1.0,
        max_session_usd=1.0,
        max_calls_per_run=10,
    )
    return CountingPlanner(
        ReplyPlanner(
            api_key=None,
            model="gpt-5.4-mini",
            enabled=False,
            generate_drafts=True,
            conversation_reply_enabled=conversation_reply_enabled,
            budget=budget,
            max_output_tokens=100,
            max_input_chars=12_000,
            proactive_approval_required=True,
            writing_mistake_rate=0.0,
            writing_quirk="",
            writing_misspellings="",
        )
    )


def build_runner(
    root: Path,
    *,
    planner,
    reactions: ReactionRecorder | None = None,
    candidate_ttl_seconds: float = 30 * 60,
    max_candidates_per_channel: int = 12,
    candidate_batch_size: int = 8,
) -> NhiZuesRunner:
    app = NhiZuesRunner.__new__(NhiZuesRunner)
    app.config = SimpleNamespace(
        runtime_mode="live_fire",
        scanner_history_backfill_limit=0,
        scanner_history_scroll_rounds=1,
        character_card="default.json",
    )
    app.memory = ConversationMemory(
        root / "memory.json",
        candidate_ttl_seconds=candidate_ttl_seconds,
        max_candidates_per_channel=max_candidates_per_channel,
        candidate_batch_size=candidate_batch_size,
    )
    app.memory.load()
    app.characters = CharacterStoreStub()
    app.reply_ledger = ReplyLedgerStub()
    app.discarded_approvals = DiscardedApprovalStub()
    app.approvals = ApprovalQueue(root / "approvals.json")
    app.topics = TopicTracker()
    app.user_instructions = SimpleNamespace(for_users=lambda *args, **kwargs: [])
    app.character_memory = SimpleNamespace(load=lambda card_id: SimpleNamespace())
    app.events = EventSink()
    app.planner = planner
    app._own_author_ids = set()
    app._process_reactions = reactions or ReactionRecorder()
    return app


async def scan(
    app: NhiZuesRunner,
    session: VisibleMessageSession,
    target: ChannelTarget,
    visible: list[MessageRecord],
):
    session.visible = visible
    state = await app._capture_channel_state(session, target)
    await app._process_regular_channel(session, target, state)
    return state


class RunnerCandidateLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_fragment_waits_for_new_context_then_queues_one_batch(self) -> None:
        with TemporaryDirectory() as tmp:
            planner = AccumulatingPlanner()
            app = build_runner(Path(tmp), planner=planner)
            session = VisibleMessageSession()
            target = ChannelTarget(
                server_id=SERVER_ID,
                channel_id=CHANNEL_ID,
                react_enabled=False,
                auto_respond_enabled=False,
            )
            first = message("message-1", "it sounds worse though")
            support = message("message-2", "the edit is cleaner", author="Mara")

            await scan(app, session, target, [first])

            self.assertEqual([("message-1",)], planner.calls)
            self.assertEqual(
                {"pending": 0, "deferred": 1, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )
            first_event = app.events.items[-1]
            self.assertEqual("awaiting_context", first_event["reason_code"])
            self.assertEqual(1, first_event["metrics"]["pending"])
            self.assertEqual(1, first_event["metrics"]["deferred"])
            self.assertEqual(0, first_event["metrics"]["model_called"])

            await scan(app, session, target, [first])

            self.assertEqual(
                [("message-1",)],
                planner.calls,
                "an unchanged deferred generation must not call the planner again",
            )
            unchanged_event = app.events.items[-1]
            self.assertEqual("no_new_messages", unchanged_event["reason_code"])
            self.assertEqual(0, unchanged_event["metrics"]["pending"])
            self.assertEqual(0, unchanged_event["metrics"]["model_called"])
            self.assertEqual(
                {"pending": 0, "deferred": 1, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )

            await scan(app, session, target, [first, support])

            self.assertEqual(
                [("message-1",), ("message-1", "message-2")],
                planner.calls,
                "new context should reopen and pass the accumulated batch",
            )
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
                "queuing the draft should resolve every source in the evaluated batch",
            )
            [approval] = app.approvals.list()
            self.assertEqual(("message-1", "message-2"), approval.source_message_ids)

            draft_event = app.events.items[-2]
            self.assertEqual("thread_continuation", draft_event["reason_code"])
            self.assertEqual(1, draft_event["metrics"]["pending"])
            self.assertEqual(2, draft_event["metrics"]["eligible"])
            self.assertEqual(1, draft_event["metrics"]["model_called"])
            self.assertEqual(1, draft_event["metrics"]["model_requests"])
            approval_event = app.events.items[-1]
            self.assertEqual("approval_queued", approval_event["reason_code"])
            self.assertEqual({"draft_queued": 1}, approval_event["metrics"])

    async def test_planner_exception_leaves_observed_generation_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            planner = PlannerRaises()
            app = build_runner(Path(tmp), planner=planner)
            session = VisibleMessageSession()
            target = ChannelTarget(server_id=SERVER_ID, channel_id=CHANNEL_ID)
            source = message("message-1", "this needs a closer look")

            session.visible = [source]
            state = await app._capture_channel_state(session, target)
            with self.assertRaisesRegex(RuntimeError, "planner exploded"):
                await app._process_regular_channel(session, target, state)

            self.assertEqual(1, planner.calls)
            self.assertEqual(
                {"pending": 1, "deferred": 0, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )
            ready = app.memory.ready_reply_candidates(CHANNEL_ID)
            self.assertEqual(("message-1",), ready.message_ids)

    async def test_reply_worthy_source_is_reserved_from_reactions(self) -> None:
        with TemporaryDirectory() as tmp:
            reply_source = message("reply-source", "the edit is clearly worse")
            reactions = ReactionRecorder(applied_ids={reply_source.message_id})
            planner = EligibleWithoutDraftPlanner(reply_source.message_id)
            app = build_runner(Path(tmp), planner=planner, reactions=reactions)
            session = VisibleMessageSession()
            target = ChannelTarget(
                server_id=SERVER_ID,
                channel_id=CHANNEL_ID,
                react_enabled=True,
                auto_respond_enabled=True,
            )

            await scan(app, session, target, [reply_source])

            self.assertEqual([(reply_source.message_id,)], planner.calls)
            self.assertEqual([[]], reactions.calls)
            eligible = app.memory.eligible_reply_candidates(CHANNEL_ID)
            self.assertIsNotNone(eligible)
            self.assertEqual((reply_source.message_id,), eligible.message_ids)
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 1},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )

            checked_event = app.events.items[-1]
            self.assertEqual("model_unavailable", checked_event["reason_code"])
            self.assertEqual(1, checked_event["metrics"]["eligible"])
            self.assertEqual(0, checked_event["metrics"]["model_called"])

    async def test_hard_skip_can_react_and_finishes_with_no_active_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            source = message("reaction-source", "lmao that transition")
            reactions = ReactionRecorder(applied_ids={source.message_id})
            app = build_runner(
                Path(tmp),
                planner=HardSkipPlanner(),
                reactions=reactions,
            )
            session = VisibleMessageSession()
            target = ChannelTarget(
                server_id=SERVER_ID,
                channel_id=CHANNEL_ID,
                react_enabled=True,
                auto_respond_enabled=True,
            )

            await scan(app, session, target, [source])

            self.assertEqual([[source.message_id]], reactions.calls)
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )
            checked_event = app.events.items[-1]
            self.assertEqual("conversation_disabled", checked_event["reason_code"])
            self.assertEqual(1, checked_event["metrics"]["rejected"])

    async def test_zero_candidate_ttl_falls_back_to_one_scan_planner_input(self) -> None:
        with TemporaryDirectory() as tmp:
            source = message("message-1", "the edit is clearly worse")
            planner = EligibleWithoutDraftPlanner(source.message_id)
            app = build_runner(
                Path(tmp),
                planner=planner,
                candidate_ttl_seconds=0,
            )
            session = VisibleMessageSession()
            target = ChannelTarget(server_id=SERVER_ID, channel_id=CHANNEL_ID)

            first_state = await scan(app, session, target, [source])

            self.assertEqual([(source.message_id,)], planner.calls)
            self.assertEqual(0, first_state.reply_candidates_observed)
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )

            await scan(app, session, target, [source])

            self.assertEqual(
                [(source.message_id,)],
                planner.calls,
                "TTL zero should retain legacy one-scan behavior, not replay seen rows",
            )

    async def test_deferred_and_eligible_rows_stay_reserved_on_same_runner_unchanged_scan(self) -> None:
        cases = (
            (
                "deferred",
                lambda source: AccumulatingPlanner(),
                {"pending": 0, "deferred": 1, "eligible": 0},
            ),
            (
                "eligible",
                lambda source: EligibleWithoutDraftPlanner(source.message_id),
                {"pending": 0, "deferred": 0, "eligible": 1},
            ),
        )
        for status, planner_factory, expected_counts in cases:
            with self.subTest(status=status), TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = message(f"{status}-source", "it sounds worse though")
                target = ChannelTarget(
                    server_id=SERVER_ID,
                    channel_id=CHANNEL_ID,
                    react_enabled=True,
                )
                planner = planner_factory(source)
                reactions = ReactionRecorder(applied_ids={source.message_id})
                app = build_runner(root, planner=planner, reactions=reactions)
                session = VisibleMessageSession()

                await scan(app, session, target, [source])
                self.assertEqual(
                    expected_counts,
                    app.memory.reply_candidate_counts(CHANNEL_ID),
                )

                await scan(app, session, target, [source])

                self.assertEqual(1, len(planner.calls))
                self.assertEqual([[], []], reactions.calls)
                self.assertEqual(
                    expected_counts,
                    app.memory.reply_candidate_counts(CHANNEL_ID),
                )
                checked_event = app.events.items[-1]
                self.assertEqual("no_new_messages", checked_event["reason_code"])

    async def test_deferred_overflow_reserves_all_twelve_not_only_ready_batch(self) -> None:
        with TemporaryDirectory() as tmp:
            sources = [
                message(f"message-{index:02d}", f"fragment number {index}")
                for index in range(12)
            ]
            planner = AlwaysDeferredPlanner()
            reactions = ReactionRecorder(
                applied_ids={source.message_id for source in sources}
            )
            app = build_runner(
                Path(tmp),
                planner=planner,
                reactions=reactions,
                max_candidates_per_channel=12,
                candidate_batch_size=8,
            )
            session = VisibleMessageSession()
            target = ChannelTarget(
                server_id=SERVER_ID,
                channel_id=CHANNEL_ID,
                react_enabled=True,
            )

            await scan(app, session, target, sources)
            await scan(app, session, target, sources)

            self.assertEqual(
                [tuple(source.message_id for source in sources[-8:])],
                planner.calls,
            )
            self.assertEqual([[], []], reactions.calls)
            active = app.memory.active_reply_candidates(CHANNEL_ID)
            self.assertIsNotNone(active)
            self.assertEqual(
                tuple(source.message_id for source in sources),
                active.message_ids,
            )
            self.assertEqual(
                {"pending": 0, "deferred": 12, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )
            self.assertEqual("no_new_messages", app.events.items[-1]["reason_code"])

    async def test_fresh_runner_replays_persisted_candidate_once_for_changed_planner(self) -> None:
        cases = (
            ("deferred", lambda source: AlwaysDeferredPlanner()),
            ("eligible", lambda source: EligibleWithoutDraftPlanner(source.message_id)),
        )
        for status, first_planner_factory in cases:
            with self.subTest(status=status), TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = message(f"{status}-source", "it sounds worse though")
                target = ChannelTarget(server_id=SERVER_ID, channel_id=CHANNEL_ID)
                first_runner = build_runner(
                    root,
                    planner=first_planner_factory(source),
                )
                first_session = VisibleMessageSession()
                await scan(first_runner, first_session, target, [source])

                changed_planner = DraftingPlanner()
                fresh_runner = build_runner(root, planner=changed_planner)
                fresh_session = VisibleMessageSession()
                replay_state = await scan(fresh_runner, fresh_session, target, [source])

                self.assertEqual([], replay_state.fresh_messages)
                self.assertEqual([(source.message_id,)], changed_planner.calls)
                [approval] = fresh_runner.approvals.list()
                self.assertEqual((source.message_id,), approval.source_message_ids)
                self.assertEqual(
                    {"pending": 0, "deferred": 0, "eligible": 0},
                    fresh_runner.memory.reply_candidate_counts(CHANNEL_ID),
                )

                await scan(fresh_runner, fresh_session, target, [source])

                self.assertEqual(
                    [(source.message_id,)],
                    changed_planner.calls,
                    "a fresh runner may replay persisted state once, never once per scan",
                )

    async def test_zero_candidate_ttl_hard_skip_records_one_shot_rejection(self) -> None:
        with TemporaryDirectory() as tmp:
            source = message("one-shot-source", "plain uncued fragment")
            app = build_runner(
                Path(tmp),
                planner=HardSkipPlanner(),
                candidate_ttl_seconds=0,
            )
            session = VisibleMessageSession()
            target = ChannelTarget(server_id=SERVER_ID, channel_id=CHANNEL_ID)

            await scan(app, session, target, [source])

            checked_event = app.events.items[-1]
            self.assertEqual("conversation_disabled", checked_event["reason_code"])
            self.assertEqual(1, checked_event["metrics"]["rejected"])
            self.assertEqual(0, checked_event["metrics"]["pending"])
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )

    async def test_no_card_cue_is_terminal_and_remains_available_to_reactions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = message("reaction-source", "lmao that transition")
            planner = real_planner(root, conversation_reply_enabled=False)
            reactions = ReactionRecorder(applied_ids={source.message_id})
            app = build_runner(root, planner=planner, reactions=reactions)
            session = VisibleMessageSession()
            target = ChannelTarget(
                server_id=SERVER_ID,
                channel_id=CHANNEL_ID,
                engage_enabled=True,
                react_enabled=True,
            )

            await scan(app, session, target, [source])

            self.assertEqual([(source.message_id,)], planner.calls)
            self.assertEqual("no_card_cue", planner.decisions[0].reason_code)
            self.assertFalse(planner.decisions[0].should_reply)
            self.assertEqual([[source.message_id]], reactions.calls)
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )
            checked_event = app.events.items[-1]
            self.assertEqual("no_card_cue", checked_event["reason_code"])
            self.assertEqual(1, checked_event["metrics"]["rejected"])

    async def test_real_planner_accumulates_thin_fragments_until_compact_opinion(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner = real_planner(root, conversation_reply_enabled=True)
            app = build_runner(root, planner=planner)
            session = VisibleMessageSession()
            target = ChannelTarget(server_id=SERVER_ID, channel_id=CHANNEL_ID)
            first = message("message-1", "the edit is clean")
            second = message("message-2", "the mix has depth")
            opinion = message("message-3", "but the remaster sounds worse")

            await scan(app, session, target, [first])
            self.assertEqual("insufficient_substance", planner.decisions[-1].reason_code)
            self.assertEqual(
                {"pending": 0, "deferred": 1, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )

            await scan(app, session, target, [first])
            self.assertEqual([(first.message_id,)], planner.calls)

            await scan(app, session, target, [first, second])
            self.assertEqual("insufficient_substance", planner.decisions[-1].reason_code)
            self.assertEqual(
                {"pending": 0, "deferred": 2, "eligible": 0},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )

            await scan(app, session, target, [first, second, opinion])

            self.assertEqual(
                [
                    (first.message_id,),
                    (first.message_id, second.message_id),
                    (first.message_id, second.message_id, opinion.message_id),
                ],
                planner.calls,
            )
            final_decision = planner.decisions[-1]
            self.assertTrue(final_decision.should_reply)
            self.assertIsNone(final_decision.draft)
            self.assertEqual("compact_opinion", final_decision.reason_code)
            self.assertEqual(0, final_decision.model_call_count)
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 3},
                app.memory.reply_candidate_counts(CHANNEL_ID),
            )
            self.assertEqual(0, planner.delegate.budget.summary()["records"])
            checked_event = app.events.items[-1]
            self.assertEqual("compact_opinion", checked_event["reason_code"])
            self.assertEqual(3, checked_event["metrics"]["eligible"])
            self.assertEqual(0, checked_event["metrics"]["model_requests"])


if __name__ == "__main__":
    unittest.main()
