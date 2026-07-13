from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from nhi_zues.config import ChannelTarget, _load_channels
from nhi_zues.models import MessageRecord
from nhi_zues.runner import ChannelScanState, NhiZuesRunner
from nhi_zues.safety_review import SafetyReviewQueue, detect_safety_review_findings


class SafetyReviewTests(unittest.TestCase):
    def test_detects_direct_self_harm_abuse(self) -> None:
        message = record("m1", "User", "kys")

        findings = detect_safety_review_findings([message])

        self.assertEqual(1, len(findings))
        self.assertEqual("Harassment / self-harm abuse", findings[0].category)
        self.assertEqual("high", findings[0].severity)

    def test_detects_protected_class_violence(self) -> None:
        message = record("m2", "User", "all immigrants should be killed")

        findings = detect_safety_review_findings([message])

        self.assertEqual(1, len(findings))
        self.assertEqual("Hateful conduct", findings[0].category)

    def test_slur_cue_does_not_match_inside_an_ordinary_word(self) -> None:
        messages = [
            record("normal-1", "User", "That sounds suspicious to me."),
            record("normal-2", "User", "The food was spicy."),
        ]

        self.assertEqual([], detect_safety_review_findings(messages))

    def test_slur_cue_still_matches_punctuation_obfuscation(self) -> None:
        findings = detect_safety_review_findings([record("obfuscated", "User", "s.p.i.c")])

        self.assertEqual(1, len(findings))
        self.assertEqual("protected-class slur cue", findings[0].matched_cues[0])

    def test_queue_dedupes_and_keeps_dismissed_items_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = SafetyReviewQueue(Path(tmp) / "safety_review.json")
            finding = detect_safety_review_findings([record("m3", "User", "go die")])[0]

            first = queue.add_findings(
                server_id="server",
                server_label="Server",
                channel_id="channel",
                channel_label="general",
                findings=[finding],
            )
            second = queue.add_findings(
                server_id="server",
                server_label="Server",
                channel_id="channel",
                channel_label="general",
                findings=[finding],
            )
            dismissed = queue.dismiss([first[0].review_id])
            third = queue.add_findings(
                server_id="server",
                server_label="Server",
                channel_id="channel",
                channel_label="general",
                findings=[finding],
            )

            self.assertEqual(1, len(first))
            self.assertEqual([], second)
            self.assertEqual(1, dismissed)
            self.assertEqual([], third)
            self.assertEqual([], queue.list())

    def test_detector_caps_findings_per_cue(self) -> None:
        messages = [record(f"cue-{index}", "User", f"go die {index}") for index in range(8)]

        findings = detect_safety_review_findings(messages, per_cue_limit=5)

        self.assertEqual(5, len(findings))

    def test_queue_caps_open_items_at_ten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = SafetyReviewQueue(Path(tmp) / "safety_review.json")
            messages = [record(f"item-{index}", "User", f"go die {index}") for index in range(12)]
            findings = detect_safety_review_findings(messages, per_cue_limit=20)

            added = queue.add_findings(
                server_id="server",
                server_label="Server",
                channel_id="channel",
                channel_label="general",
                findings=findings,
            )

            self.assertEqual(10, len(added))
            self.assertEqual(10, len(queue.list()))
            self.assertEqual(10, queue.state()["max_open_count"])

    def test_server_safety_review_flag_loads_into_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "servers.json"
            path.write_text(
                """
                {
                  "servers": [
                    {
                      "server_id": "s1",
                      "label": "Server",
                      "safety_review_enabled": true,
                      "channels": [
                        {"channel_id": "c1", "scan_enabled": true}
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            targets = _load_channels(path, "")

            self.assertEqual(1, len(targets))
            self.assertTrue(targets[0].safety_review_enabled)

    def test_safety_review_exclusive_limits_active_targets(self) -> None:
        runner = NhiZuesRunner.__new__(NhiZuesRunner)
        sweep = ChannelTarget(server_id="sweep-server", channel_id="c1", safety_review_enabled=True)
        normal = ChannelTarget(server_id="normal-server", channel_id="c2", safety_review_enabled=False)
        runner.config = SimpleNamespace(
            channels=(normal, sweep),
            safety_review_exclusive=True,
            scanner_max_channels_per_cycle=10,
        )
        runner._target_cursor = 0
        runner._completed_loop_count = 0

        self.assertEqual([sweep], runner._planned_targets())
        self.assertEqual(
            1,
            runner._loop_state(
                planned_targets=(sweep,),
                selected_targets=(sweep,),
                will_complete_loop=True,
            )["total_channels"],
        )

    def test_safety_review_exclusive_can_be_disabled(self) -> None:
        runner = NhiZuesRunner.__new__(NhiZuesRunner)
        sweep = ChannelTarget(server_id="sweep-server", channel_id="c1", safety_review_enabled=True)
        normal = ChannelTarget(server_id="normal-server", channel_id="c2", safety_review_enabled=False)
        runner.config = SimpleNamespace(
            channels=(normal, sweep),
            safety_review_exclusive=False,
            scanner_max_channels_per_cycle=10,
        )
        runner._target_cursor = 0
        runner._completed_loop_count = 0

        self.assertEqual([normal, sweep], runner._planned_targets())


class EmptySafetyReviewHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_fallback_does_not_double_count_new_messages_as_backfill(self) -> None:
        runner = NhiZuesRunner.__new__(NhiZuesRunner)
        runner.config = SimpleNamespace(
            safety_review_history_limit=20,
            safety_review_scroll_rounds=2,
            safety_review_exclusive=True,
        )
        runner.events = EventSink()
        runner.memory = FreshMemory()
        runner.safety_reviews = ReviewSink()
        visible = record("visible-1", "User", "ordinary visible message")
        target = SimpleNamespace(
            server_id="server",
            server_label="Server",
            channel_id="channel",
            channel_label="general",
        )
        state = ChannelScanState(
            visible_messages=[visible],
            fresh_messages=[visible],
            character=SimpleNamespace(name="NHI Zues", aliases=()),
            character_names=("NHI Zues",),
            own_message_ids=set(),
            own_texts=set(),
            own_author_ids=set(),
        )

        with self.assertLogs("nhi_zues.runner", level="WARNING"):
            visible_count, fresh_count = await runner._process_safety_review_channel(
                FailedHistorySession(),
                target,
                state,
            )

        self.assertEqual(1, visible_count)
        self.assertEqual(1, fresh_count)
        self.assertEqual(1, runner.events.items[-1]["metrics"]["newly_visible"])
        self.assertEqual(0, runner.events.items[-1]["metrics"]["backfill_discovered"])

    async def test_empty_history_read_records_dom_diagnostics(self) -> None:
        runner = NhiZuesRunner.__new__(NhiZuesRunner)
        runner.config = SimpleNamespace(safety_review_history_limit=10, safety_review_scroll_rounds=1)
        runner.events = EventSink()
        target = SimpleNamespace(server_id="server", channel_id="channel")
        state = ChannelScanState(
            visible_messages=[],
            fresh_messages=[],
            character=SimpleNamespace(name="NHI Zues", aliases=()),
            character_names=("NHI Zues",),
            own_message_ids=set(),
            own_texts=set(),
            own_author_ids=set(),
        )

        review_source, fresh_messages, source_label = await runner._read_safety_review_source(
            EmptyHistorySession(),
            target,
            state,
        )

        self.assertEqual([], review_source)
        self.assertEqual([], fresh_messages)
        self.assertEqual("history-empty", source_label)
        self.assertEqual("safety_review_scan", runner.events.items[0]["event_type"])
        self.assertIn("raw=0", runner.events.items[0]["summary"])
        self.assertIn("Discord may not have loaded", runner.events.items[0]["summary"])

    async def test_shallow_unverified_history_is_retried_and_merged(self) -> None:
        runner = NhiZuesRunner.__new__(NhiZuesRunner)
        runner.config = SimpleNamespace(
            safety_review_history_limit=20,
            safety_review_scroll_rounds=8,
            safety_review_history_retries=1,
        )
        runner.events = EventSink()
        runner.memory = FreshMemory()
        runner._own_author_ids = set()
        target = SimpleNamespace(server_id="server", channel_id="channel")
        state = ChannelScanState(
            visible_messages=[],
            fresh_messages=[],
            character=SimpleNamespace(name="NHI Zues", aliases=()),
            character_names=("NHI Zues",),
            own_message_ids=set(),
            own_texts=set(),
            own_author_ids=set(),
        )
        session = RetryingHistorySession()

        review_source, fresh_messages, source_label = await runner._read_safety_review_source(
            session,
            target,
            state,
        )

        self.assertEqual(2, session.calls)
        self.assertEqual(20, len(review_source))
        self.assertEqual(20, len(fresh_messages))
        self.assertEqual("history", source_label)
        self.assertEqual(2, state.safety_history_diagnostics["pass_count"])
        self.assertEqual(18, state.safety_history_diagnostics["retry_added"])


def record(message_id: str, author: str, text: str) -> MessageRecord:
    return MessageRecord(
        server_id="server",
        channel_id="channel",
        message_id=message_id,
        author=author,
        author_id="user-id",
        text=text,
        observed_at=datetime.now(timezone.utc),
    )


class EventSink:
    def __init__(self) -> None:
        self.items = []

    def add(self, **kwargs) -> None:
        self.items.append(kwargs)


class EmptyHistorySession:
    async def read_channel_history(self, server_id: str, channel_id: str, *, limit: int, scroll_rounds: int):
        return []

    async def message_dom_diagnostics(self) -> dict[str, object]:
        return {
            "url": "https://discord.com/channels/server/channel",
            "raw_chat_nodes": 0,
            "valid_message_id_nodes": 0,
            "text_rows": 0,
            "empty_text_rows": 0,
            "body_preview": "No Messages",
        }


class FreshMemory:
    def ingest(self, channel_id: str, messages: list[MessageRecord]) -> list[MessageRecord]:
        _ = channel_id
        return list(messages)

    def save(self) -> None:
        return None


class ReviewSink:
    def add_findings(self, **kwargs) -> list:
        _ = kwargs
        return []


class FailedHistorySession:
    async def read_channel_history(self, server_id: str, channel_id: str, *, limit: int, scroll_rounds: int):
        _ = (server_id, channel_id, limit, scroll_rounds)
        raise RuntimeError("history unavailable")


class RetryingHistorySession:
    def __init__(self) -> None:
        self.calls = 0
        self._diagnostics: dict[str, object] = {}

    async def read_channel_history(self, server_id: str, channel_id: str, *, limit: int, scroll_rounds: int):
        _ = (server_id, channel_id, limit, scroll_rounds)
        self.calls += 1
        count = 2 if self.calls == 1 else 20
        self._diagnostics = {
            "stop_reason": "stable_timeout" if self.calls == 1 else "limit_reached",
            "rounds_used": 8,
            "message_count": count,
            "limit": 20,
            "cancelled": False,
        }
        return [record(str(index + 1), "User", f"message {index + 1}") for index in range(count)]

    def history_read_diagnostics(self) -> dict[str, object]:
        return dict(self._diagnostics)
