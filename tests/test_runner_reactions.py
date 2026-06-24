from __future__ import annotations

import unittest
from types import SimpleNamespace

from nhi_zues.config import ChannelTarget
from nhi_zues.discarded_approvals import DiscardedApproval
from nhi_zues.models import MessageRecord
from nhi_zues.models import DraftDecision
from nhi_zues.runner import (
    NhiZuesRunner,
    _recent_non_own_message_ids,
    _recent_reaction_candidates,
    _reaction_window_cap,
)
from nhi_zues.reactions import LAUGH_EMOJI, THUMBS_UP_EMOJI


class EventSink:
    def __init__(self) -> None:
        self.items = []

    def add(self, **kwargs) -> None:
        self.items.append(kwargs)


class ReactionLedgerStub:
    def __init__(self, reacted_ids: set[str] | None = None) -> None:
        self.reacted_ids = reacted_ids or set()
        self.records = []

    def has_reacted_to_message(self, *, channel_id: str, message_id: str) -> bool:
        return message_id in self.reacted_ids

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)
        self.reacted_ids.add(kwargs["message"].message_id)


class ReplyLedgerStateStub:
    def own_message_ids_for_channel(self, *, channel_id: str) -> set[str]:
        return set()

    def own_texts_for_channel(self, *, channel_id: str) -> set[str]:
        return set()

    def find_overlap(self, *, channel_id: str, source_message_ids):
        return []


class DiscardedApprovalStub:
    def __init__(self, overlaps=None):
        self.overlaps = list(overlaps or [])

    def find_overlap(self, *, channel_id: str, source_message_ids):
        return self.overlaps


class ApprovalsShouldNotQueue:
    def find_source_overlap(self, *, channel_id: str, source_message_ids):
        raise AssertionError("approval duplicate check should not run after discard suppression")

    def add(self, **kwargs):
        raise AssertionError("discarded source should not queue another approval")


class SessionStub:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls = []

    async def add_reaction(self, message_id: str, emoji: str) -> dict[str, object]:
        self.calls.append((message_id, emoji))
        return self.result


def message(
    message_id: str,
    text: str,
    author: str = "Rook",
    *,
    author_id: str | None = None,
) -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author=author,
        author_id=author_id,
        text=text,
    )


def runner(*, runtime_mode: str = "live_fire", ledger: ReactionLedgerStub | None = None):
    instance = NhiZuesRunner.__new__(NhiZuesRunner)
    instance.config = SimpleNamespace(
        runtime_mode=runtime_mode,
        reaction_max_per_channel=2,
        reaction_threshold="normal",
        reaction_sample_percent=0.0,
        reaction_force_laugh_percent=0.0,
        reaction_emoji_override="",
        scanner_channel_settle_seconds=0.0,
        character_card="default.json",
    )
    instance.events = EventSink()
    instance.reaction_ledger = ledger or ReactionLedgerStub()
    instance.reply_ledger = ReplyLedgerStateStub()
    instance.discarded_approvals = DiscardedApprovalStub()
    return instance


class RunnerReactionTests(unittest.IsolatedAsyncioTestCase):
    def test_recent_reaction_candidates_include_visible_when_no_fresh_messages(self) -> None:
        visible = [message("1", "old"), message("2", "that was wild")]

        candidates = _recent_reaction_candidates(visible, [], character_names=("NHI Zues",))

        self.assertEqual(["2", "1"], [item.message_id for item in candidates])

    def test_recent_reaction_candidates_skip_known_own_author_id(self) -> None:
        visible = [
            message("1", "own display drift", "different nickname", author_id="own-1"),
            message("2", "that was wild", "Rook", author_id="user-1"),
        ]

        candidates = _recent_reaction_candidates(
            visible,
            [],
            character_names=("NHI Zues",),
            own_author_ids={"own-1"},
        )

        self.assertEqual(["2"], [item.message_id for item in candidates])

    def test_recent_reaction_candidates_skip_scraped_character_prefix(self) -> None:
        visible = [
            message("1", "own display drift", "NHI ZuesI'm new here say hi"),
            message("2", "that was wild", "Rook", author_id="user-1"),
        ]

        candidates = _recent_reaction_candidates(
            visible,
            [],
            character_names=("NHI Zues",),
        )

        self.assertEqual(["2"], [item.message_id for item in candidates])

    def test_recent_reaction_candidates_skip_scraped_character_status_suffixes(self) -> None:
        visible = [
            message("1", "own display drift", "NHI ZuesOnline"),
            message("2", "own display drift", "NHI Zues Invisible"),
            message("3", "not own", "ZuesFan", author_id="user-3"),
            message("4", "that was wild", "Rook", author_id="user-4"),
        ]

        candidates = _recent_reaction_candidates(
            visible,
            [],
            character_names=("NHI Zues", "zues"),
        )

        self.assertEqual(["4", "3"], [item.message_id for item in candidates])

    def test_recent_reaction_candidates_skip_known_own_text_from_ledger(self) -> None:
        visible = [
            message("1", "i already said the archive chain is the weak part", "Rook", author_id="user-1"),
            message("2", "that was wild", "Rook", author_id="user-2"),
        ]

        candidates = _recent_reaction_candidates(
            visible,
            [],
            character_names=("NHI Zues",),
            own_texts={"i already said the archive chain is the weak part"},
        )

        self.assertEqual(["2"], [item.message_id for item in candidates])

    async def test_no_eligible_reaction_emits_scan_event(self) -> None:
        app = runner()
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("1", "plain update with nothing notable")],
            fresh_count=0,
        )

        self.assertEqual(set(), reacted)
        self.assertEqual([], session.calls)
        self.assertEqual("reaction_scan", app.events.items[-1]["event_type"])
        self.assertIn("fresh=0", app.events.items[-1]["summary"])

    async def test_already_present_reaction_gets_distinct_event(self) -> None:
        app = runner()
        session = SessionStub({"applied": False, "already_present": True, "path": "own-existing"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("1", "that is such a cursed meme lmao")],
            fresh_count=1,
        )

        self.assertEqual(set(), reacted)
        self.assertEqual("reaction_already_present", app.events.items[0]["event_type"])
        self.assertEqual(1, len(app.reaction_ledger.records))

    async def test_unverified_reaction_does_not_write_ledger(self) -> None:
        app = runner()
        session = SessionStub(
            {
                "applied": False,
                "already_present": False,
                "verification_failed": True,
                "path": "quick-unverified",
            }
        )
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("1", "that is such a cursed meme lmao")],
            fresh_count=1,
        )

        self.assertEqual(set(), reacted)
        self.assertEqual([], app.reaction_ledger.records)
        self.assertEqual("reaction_failed", app.events.items[0]["event_type"])
        self.assertNotIn("reaction_added", [item["event_type"] for item in app.events.items])

    async def test_force_laugh_percentage_cap_blocks_repeated_scans(self) -> None:
        app = runner(ledger=ReactionLedgerStub({"1", "2"}))
        app.config.reaction_force_laugh_percent = 40.0
        app.config.reaction_max_per_channel = 10
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("3", "that is such a cursed meme lmao")],
            fresh_count=0,
            force_laugh_ids={"1", "2", "3", "4", "5"},
        )

        self.assertEqual(set(), reacted)
        self.assertEqual([], session.calls)
        self.assertIn("force_window=2/2/5", app.events.items[-1]["summary"])
        self.assertIn("force_window_capped=1", app.events.items[-1]["summary"])

    async def test_force_reaction_target_fills_until_window_cap(self) -> None:
        app = runner(ledger=ReactionLedgerStub({"1"}))
        app.config.reaction_force_laugh_percent = 40.0
        app.config.reaction_max_per_channel = 10
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [
                message("1", "already reacted old one"),
                message("2", "plain update but still worth light acknowledgement"),
                message("3", "plain update two"),
                message("4", "plain update three"),
                message("5", "plain update four"),
            ],
            fresh_count=0,
            force_laugh_ids={"1", "2", "3", "4", "5"},
        )

        self.assertEqual({"2"}, reacted)
        self.assertEqual([("2", THUMBS_UP_EMOJI)], session.calls)
        self.assertIn("force reaction target fill (40% target)", app.reaction_ledger.records[0]["reason"])

    async def test_force_laugh_percentage_cap_limits_total_reactions_in_window(self) -> None:
        app = runner()
        app.config.reaction_force_laugh_percent = 40.0
        app.config.reaction_max_per_channel = 10
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [
                message("1", "that is such a cursed meme lmao"),
                message("2", "that is such a cursed meme lmao"),
                message("3", "that is such a cursed meme lmao"),
                message("4", "that is such a cursed meme lmao"),
                message("5", "that is such a cursed meme lmao"),
            ],
            fresh_count=5,
            force_laugh_ids={"1", "2", "3", "4", "5"},
        )

        self.assertEqual({"1", "2"}, reacted)
        self.assertEqual([("1", LAUGH_EMOJI), ("2", LAUGH_EMOJI)], session.calls)

    async def test_successful_reaction_logs_event_and_ledger(self) -> None:
        app = runner()
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("1", "that is such a cursed meme lmao")],
            fresh_count=1,
        )

        self.assertEqual({"1"}, reacted)
        self.assertEqual([("1", LAUGH_EMOJI)], session.calls)
        self.assertEqual(1, len(app.reaction_ledger.records))
        self.assertEqual("reaction_added", app.events.items[-1]["event_type"])

    async def test_process_reactions_final_guard_blocks_own_author_id(self) -> None:
        app = runner()
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("1", "that is such a cursed meme lmao", "renamed account", author_id="own-1")],
            fresh_count=1,
            character_names=("NHI Zues",),
            own_author_ids={"own-1"},
        )

        self.assertEqual(set(), reacted)
        self.assertEqual([], session.calls)
        self.assertIn("own_skipped=1", app.events.items[-1]["summary"])

    async def test_remember_current_account_id_seeds_own_author_guard(self) -> None:
        app = NhiZuesRunner.__new__(NhiZuesRunner)

        class CurrentUserSession:
            async def current_user_id(self):
                return "own-1"

        await app._remember_current_account_id(CurrentUserSession())

        self.assertEqual({"own-1"}, app._own_author_ids)

    async def test_force_reaction_recent_messages_can_react_to_plain_text_without_laughing(self) -> None:
        app = runner()
        app.config.reaction_force_laugh_percent = 100.0
        session = SessionStub({"applied": True, "path": "quick"})
        target = SimpleNamespace(server_id="server-1", channel_id="channel-1", react_enabled=True)

        reacted = await app._process_reactions(
            session,
            target,
            [message("1", "plain update with no normal cue")],
            fresh_count=1,
            force_laugh_ids={"1"},
        )

        self.assertEqual({"1"}, reacted)
        self.assertEqual([("1", THUMBS_UP_EMOJI)], session.calls)
        self.assertIn("force reaction", app.events.items[-1]["summary"])

    def test_force_laugh_recent_ids_are_last_five_non_character_messages(self) -> None:
        visible = [
            message("1", "old one", "A"),
            message("2", "own", "NHI Zues"),
            message("3", "two", "B"),
            message("4", "three", "C"),
            message("5", "four", "D"),
            message("6", "five", "E"),
            message("7", "six", "F"),
        ]

        ids = _recent_non_own_message_ids(visible, character_names=("NHI Zues",), limit=5)

        self.assertEqual({"3", "4", "5", "6", "7"}, ids)

    def test_reaction_window_cap_uses_ceiling_for_small_active_windows(self) -> None:
        self.assertEqual(1, _reaction_window_cap(40.0, 2))
        self.assertEqual(0, _reaction_window_cap(0.0, 5))

    async def test_engage_disabled_channel_can_react_but_does_not_plan_reply(self) -> None:
        app = runner()
        app.config.runtime_mode = "semi_auto"
        app.memory = MemoryStub([message("1", "that made me laugh lmao", "Rook")])
        app.characters = SimpleNamespace(
            for_server=lambda server_id, card: SimpleNamespace(name="NHI Zues", aliases=())
        )
        app.topics = SimpleNamespace(
            update=lambda channel_id, messages: SimpleNamespace(top_topics=())
        )
        app.user_instructions = SimpleNamespace(for_users=lambda user_keys, server_id, channel_id: [])
        app.character_memory = SimpleNamespace(load=lambda card_id: SimpleNamespace())
        app.planner = PlannerShouldNotRun()
        session = ChannelSessionStub()
        target = SimpleNamespace(
            server_id="server-1",
            channel_id="channel-1",
            character_card=None,
            react_enabled=True,
            engage_enabled=False,
            auto_respond_enabled=True,
        )

        await app._process_channels(session, [target])

        self.assertEqual([("1", LAUGH_EMOJI)], session.calls)
        self.assertTrue(app.memory.saved)
        self.assertEqual("channel_checked", app.events.items[-1]["event_type"])
        self.assertIn("Engage is off", app.events.items[-1]["summary"])

    async def test_scanned_messages_are_saved_before_planner_runs(self) -> None:
        class PlannerRaises:
            async def plan(self, **kwargs):
                raise RuntimeError("planner failed after scan")

        app = runner()
        app.config.runtime_mode = "semi_auto"
        app.memory = MemoryStub([message("1", "that made me laugh lmao", "Rook")])
        app.characters = SimpleNamespace(
            for_server=lambda server_id, card: SimpleNamespace(name="NHI Zues", aliases=())
        )
        app.topics = SimpleNamespace(
            update=lambda channel_id, messages: SimpleNamespace(top_topics=())
        )
        app.user_instructions = SimpleNamespace(for_users=lambda user_keys, server_id, channel_id: [])
        app.character_memory = SimpleNamespace(load=lambda card_id: SimpleNamespace())
        app.planner = PlannerRaises()
        session = ChannelSessionStub()
        target = SimpleNamespace(
            server_id="server-1",
            channel_id="channel-1",
            character_card=None,
            react_enabled=False,
            engage_enabled=True,
            auto_respond_enabled=True,
        )

        with self.assertRaisesRegex(RuntimeError, "planner failed"):
            await app._process_channels(session, [target])

        self.assertTrue(app.memory.saved)

    async def test_discarded_source_suppresses_requeued_approval(self) -> None:
        class PlannerAlwaysReplies:
            async def plan(self, **kwargs):
                return DraftDecision(
                    True,
                    "direct cue",
                    draft="i would normally answer this",
                    engagement_type="direct",
                )

        app = runner(runtime_mode="live_fire")
        app.memory = MemoryStub([message("1", "hey NHI Zues what do you think", "Rook")])
        app.characters = SimpleNamespace(
            for_server=lambda server_id, card: SimpleNamespace(name="NHI Zues", aliases=())
        )
        app.topics = SimpleNamespace(
            update=lambda channel_id, messages: SimpleNamespace(top_topics=())
        )
        app.user_instructions = SimpleNamespace(for_users=lambda user_keys, server_id, channel_id: [])
        app.character_memory = SimpleNamespace(load=lambda card_id: SimpleNamespace())
        app.planner = PlannerAlwaysReplies()
        app.approvals = ApprovalsShouldNotQueue()
        app.discarded_approvals = DiscardedApprovalStub(
            [
                DiscardedApproval(
                    discard_id="discard-1",
                    created_at="2026-06-24T12:00:00+00:00",
                    server_id="server-1",
                    channel_id="channel-1",
                    source_message_ids=("1",),
                    reason="discarded by operator",
                )
            ]
        )
        session = ChannelSessionStub()
        target = SimpleNamespace(
            server_id="server-1",
            channel_id="channel-1",
            character_card=None,
            react_enabled=False,
            engage_enabled=True,
            auto_respond_enabled=True,
        )

        await app._process_channels(session, [target])

        self.assertEqual("discarded_approval_suppressed", app.events.items[-1]["event_type"])
        self.assertTrue(app.memory.saved)


class RunnerTargetRotationTests(unittest.TestCase):
    def test_limit_targets_rotates_through_global_loop_order(self) -> None:
        first = ChannelTarget(server_id="s", channel_id="1")
        second = ChannelTarget(server_id="s", channel_id="2")
        third = ChannelTarget(server_id="s", channel_id="3")
        app = NhiZuesRunner.__new__(NhiZuesRunner)
        app.config = SimpleNamespace(
            scanner_max_channels_per_cycle=1,
            channels=(first, second, third),
        )

        selected, completed_loop = app._select_targets(app._planned_targets())
        self.assertEqual([first], selected)
        self.assertFalse(completed_loop)
        selected, completed_loop = app._select_targets(app._planned_targets())
        self.assertEqual([second], selected)
        self.assertFalse(completed_loop)
        selected, completed_loop = app._select_targets(app._planned_targets())
        self.assertEqual([third], selected)
        self.assertTrue(completed_loop)

    def test_limit_targets_respects_rotated_subset(self) -> None:
        first = ChannelTarget(server_id="s", channel_id="1")
        second = ChannelTarget(server_id="s", channel_id="2")
        third = ChannelTarget(server_id="s", channel_id="3")
        app = NhiZuesRunner.__new__(NhiZuesRunner)
        app.config = SimpleNamespace(
            scanner_max_channels_per_cycle=1,
            channels=(first, second, third),
        )
        app._target_cursor = 1

        self.assertEqual([third], app._limit_targets([third]))

    def test_select_targets_finishes_loop_before_wrapping(self) -> None:
        first = ChannelTarget(server_id="s", channel_id="1")
        second = ChannelTarget(server_id="s", channel_id="2")
        third = ChannelTarget(server_id="s", channel_id="3")
        app = NhiZuesRunner.__new__(NhiZuesRunner)
        app.config = SimpleNamespace(
            scanner_max_channels_per_cycle=2,
            channels=(first, second, third),
        )
        app._target_cursor = 2

        selected, completed_loop = app._select_targets([third, first, second])

        self.assertEqual([third], selected)
        self.assertTrue(completed_loop)
        self.assertEqual(0, app._target_cursor)

    def test_planned_targets_start_from_current_cursor(self) -> None:
        first = ChannelTarget(server_id="s", channel_id="1")
        second = ChannelTarget(server_id="s", channel_id="2")
        third = ChannelTarget(server_id="s", channel_id="3")
        app = NhiZuesRunner.__new__(NhiZuesRunner)
        app.config = SimpleNamespace(channels=(first, second, third))
        app._target_cursor = 1

        self.assertEqual([second, third, first], app._planned_targets())


class MemoryStub:
    def __init__(self, messages):
        self.messages = messages
        self.saved = False

    def ingest(self, channel_id, visible_messages):
        return list(visible_messages)

    def context(self, channel_id, *, limit=20):
        return []

    def user_context_for(self, context, *, limit=8):
        return []

    def save(self):
        self.saved = True


class PlannerShouldNotRun:
    async def plan(self, **kwargs):
        raise AssertionError("planner should not run when Engage is disabled")


class ChannelSessionStub(SessionStub):
    def __init__(self) -> None:
        super().__init__({"applied": True, "path": "quick"})

    async def account_blocker_state(self) -> dict[str, object]:
        return {"blocked": False}

    async def navigate_channel(self, server_id: str, channel_id: str) -> str:
        return f"https://discord.com/channels/{server_id}/{channel_id}"

    async def read_visible_messages(self, server_id: str, channel_id: str):
        return [message("1", "that made me laugh lmao", "Rook")]


if __name__ == "__main__":
    unittest.main()
