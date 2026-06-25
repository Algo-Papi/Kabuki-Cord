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


class UnavailableSession:
    async def account_blocker_state(self) -> dict[str, object]:
        return {"blocked": False}

    async def navigate_channel(self, server_id: str, channel_id: str) -> str:
        return f"https://discord.com/channels/{server_id}/redirected"


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


if __name__ == "__main__":
    unittest.main()
