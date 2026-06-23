from __future__ import annotations

import unittest
from types import SimpleNamespace

from nhi_zues.models import MessageRecord
from nhi_zues.runner import NhiZuesRunner, _recent_reaction_candidates
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


def message(message_id: str, text: str, author: str = "Rook") -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author=author,
        author_id=None,
        text=text,
    )


def runner(*, runtime_mode: str = "live_fire", ledger: ReactionLedgerStub | None = None):
    instance = NhiZuesRunner.__new__(NhiZuesRunner)
    instance.config = SimpleNamespace(
        runtime_mode=runtime_mode,
        reaction_max_per_channel=2,
        reaction_threshold="normal",
        reaction_sample_percent=0.0,
        reaction_emoji_override="",
    )
    instance.events = EventSink()
    instance.reaction_ledger = ledger or ReactionLedgerStub()
    return instance


class RunnerReactionTests(unittest.IsolatedAsyncioTestCase):
    def test_recent_reaction_candidates_include_visible_when_no_fresh_messages(self) -> None:
        visible = [message("1", "old"), message("2", "that was wild")]

        candidates = _recent_reaction_candidates(visible, [], character_names=("NHI Zues",))

        self.assertEqual(["2", "1"], [item.message_id for item in candidates])

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
        self.assertEqual([], app.reaction_ledger.records)

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


if __name__ == "__main__":
    unittest.main()
