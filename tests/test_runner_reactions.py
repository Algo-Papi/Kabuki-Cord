from __future__ import annotations

import unittest
from types import SimpleNamespace

from nhi_zues.config import ChannelTarget
from nhi_zues.models import MessageRecord
from nhi_zues.runner import (
    NhiZuesRunner,
    _recent_non_own_message_ids,
    _recent_reaction_candidates,
)
from nhi_zues.reactions import LAUGH_EMOJI


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

    async def test_force_laugh_recent_messages_can_react_to_plain_text(self) -> None:
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
        self.assertEqual([("1", LAUGH_EMOJI)], session.calls)
        self.assertIn("force laugh", app.events.items[-1]["summary"])

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


class RunnerTargetRotationTests(unittest.TestCase):
    def test_limit_targets_rotates_through_due_channels(self) -> None:
        first = ChannelTarget(server_id="s", channel_id="1")
        second = ChannelTarget(server_id="s", channel_id="2")
        third = ChannelTarget(server_id="s", channel_id="3")
        app = NhiZuesRunner.__new__(NhiZuesRunner)
        app.config = SimpleNamespace(
            scanner_max_channels_per_cycle=1,
            channels=(first, second, third),
        )

        self.assertEqual([first], app._limit_targets([first, second, third]))
        self.assertEqual([second], app._limit_targets([first, second, third]))
        self.assertEqual([third], app._limit_targets([first, second, third]))

    def test_limit_targets_respects_due_subset_after_rotation(self) -> None:
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
