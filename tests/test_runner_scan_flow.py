from __future__ import annotations

import unittest
from types import SimpleNamespace

from nhi_zues.config import ChannelTarget
from nhi_zues.models import DraftDecision, MessageRecord
from nhi_zues.runner import ChannelScanState, NhiZuesRunner


class EventSink:
    def __init__(self) -> None:
        self.items = []

    def add(self, **kwargs) -> None:
        self.items.append(kwargs)


class NoOverlapStore:
    def find_overlap(self, *, channel_id: str, source_message_ids):
        return []


class ReplyLedgerStateStub:
    def own_message_ids_for_channel(self, *, channel_id: str) -> set[str]:
        return set()

    def own_texts_for_channel(self, *, channel_id: str) -> set[str]:
        return set()


class CharacterStoreStub:
    def for_server(self, server_id: str, card: str | None):
        return SimpleNamespace(name="NHI Zues", aliases=())


class MemoryRecorder:
    def __init__(self) -> None:
        self.seen = set()
        self.ingested = []
        self.saved = False

    def ingest(self, channel_id: str, messages: list[MessageRecord]) -> list[MessageRecord]:
        self.ingested.append((channel_id, [message.message_id for message in messages]))
        fresh = []
        for item in messages:
            if item.message_id in self.seen:
                continue
            self.seen.add(item.message_id)
            fresh.append(item)
        return fresh

    def save(self) -> None:
        self.saved = True


class UnavailableSession:
    async def account_blocker_state(self) -> dict[str, object]:
        return {"blocked": False}

    async def navigate_channel(self, server_id: str, channel_id: str) -> str:
        return f"https://discord.com/channels/{server_id}/redirected"


class ScanHistorySession:
    def __init__(self) -> None:
        self.visible = [message("visible-1")]
        self.history = [message("older-1"), message("visible-1")]
        self.history_calls = []
        self.latest_restores = 0

    async def read_visible_messages(self, server_id: str, channel_id: str) -> list[MessageRecord]:
        return self.visible

    async def read_channel_history(
        self,
        server_id: str,
        channel_id: str,
        *,
        limit: int,
        scroll_rounds: int,
    ) -> list[MessageRecord]:
        self.history_calls.append((server_id, channel_id, limit, scroll_rounds))
        return self.history

    async def ensure_latest_messages_visible(self) -> None:
        self.latest_restores += 1


def message(message_id: str = "message-1") -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author="Rook",
        author_id="user-1",
        text="hello",
    )


def bare_runner(*, runtime_mode: str = "dry") -> NhiZuesRunner:
    target = ChannelTarget(server_id="server-1", channel_id="channel-1")
    app = NhiZuesRunner.__new__(NhiZuesRunner)
    app.config = SimpleNamespace(
        channels=(target,),
        scanner_max_channels_per_cycle=1,
        runtime_mode=runtime_mode,
        typing_indicator_enabled=False,
        typing_min_seconds=0.0,
        typing_max_seconds=0.0,
        typing_chars_per_second=10.0,
    )
    app.events = EventSink()
    app.discarded_approvals = NoOverlapStore()
    app.reply_ledger = NoOverlapStore()
    app._target_cursor = 0
    app._completed_loop_count = 0
    return app


class RunnerScanFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_channel_records_event_and_completion_callback(self) -> None:
        target = ChannelTarget(server_id="server-1", channel_id="channel-1")
        app = bare_runner()
        started = []
        completed = []

        with self.assertLogs("nhi_zues.runner", level="WARNING") as logs:
            await app._process_channels(
                UnavailableSession(),
                [target],
                planned_targets=[target],
                loop_state={"will_complete_loop": True},
                on_target_start=lambda *args: started.append(args),
                on_target_complete=lambda *args: completed.append(args),
            )

        self.assertIn("redirected", logs.output[0])
        self.assertEqual("channel_unavailable", app.events.items[0]["event_type"])
        self.assertEqual(1, len(started))
        self.assertEqual(1, len(completed))
        self.assertEqual((target, 0, 0), completed[0][:3])

    async def test_dry_run_reply_decision_is_recorded_without_delivery(self) -> None:
        app = bare_runner(runtime_mode="dry")
        target = SimpleNamespace(
            server_id="server-1",
            channel_id="channel-1",
            auto_respond_enabled=True,
        )
        source = message()
        state = ChannelScanState(
            visible_messages=[source],
            fresh_messages=[source],
            character=SimpleNamespace(name="NHI Zues", aliases=()),
            character_names=("NHI Zues",),
            own_message_ids=set(),
            own_texts=set(),
            own_author_ids=set(),
        )

        await app._handle_reply_decision(
            session=SimpleNamespace(),
            target=target,
            state=state,
            decision=DraftDecision(
                should_reply=True,
                reason="test draft",
                draft="i would answer that",
                engagement_type="conversation",
            ),
            reply_fresh=[source],
        )

        self.assertEqual("dry_run", app.events.items[-1]["event_type"])
        self.assertEqual("i would answer that", app.events.items[-1]["draft"])

    async def test_scan_visit_backfills_history_without_treating_old_rows_as_reply_fresh(self) -> None:
        app = bare_runner()
        app.config.scanner_history_backfill_limit = 80
        app.config.scanner_history_scroll_rounds = 8
        app.memory = MemoryRecorder()
        app.characters = CharacterStoreStub()
        app.reply_ledger = ReplyLedgerStateStub()
        session = ScanHistorySession()
        target = ChannelTarget(server_id="server-1", channel_id="channel-1")

        state = await app._capture_channel_state(session, target)

        self.assertEqual([("server-1", "channel-1", 80, 8)], session.history_calls)
        self.assertEqual(
            [
                ("channel-1", ["visible-1"]),
                ("channel-1", ["older-1", "visible-1"]),
            ],
            app.memory.ingested,
        )
        self.assertTrue(app.memory.saved)
        self.assertEqual(["visible-1"], [item.message_id for item in state.fresh_messages])
        self.assertEqual(2, state.history_message_count)
        self.assertEqual(1, state.history_fresh_count)
        self.assertEqual(1, session.latest_restores)

    async def test_scan_history_backfill_is_skipped_for_safety_review_targets(self) -> None:
        app = bare_runner()
        app.config.scanner_history_backfill_limit = 80
        app.config.scanner_history_scroll_rounds = 8
        app.memory = MemoryRecorder()
        app.characters = CharacterStoreStub()
        app.reply_ledger = ReplyLedgerStateStub()
        session = ScanHistorySession()
        target = ChannelTarget(
            server_id="server-1",
            channel_id="channel-1",
            safety_review_enabled=True,
        )

        state = await app._capture_channel_state(session, target)

        self.assertEqual([], session.history_calls)
        self.assertEqual([("channel-1", ["visible-1"])], app.memory.ingested)
        self.assertEqual(0, state.history_message_count)
        self.assertEqual(0, state.history_fresh_count)


if __name__ == "__main__":
    unittest.main()
