from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from nhi_zues.config import ChannelTarget, _load_channels
from nhi_zues.models import MessageRecord
from nhi_zues.runner import NhiZuesRunner
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
