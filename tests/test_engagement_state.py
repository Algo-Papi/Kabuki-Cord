from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.gui import engagement_state


class EngagementStateTests(unittest.TestCase):
    def test_aggregates_latest_run_and_returns_content_free_freshness(self) -> None:
        with TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events.json"
            started_at = datetime(2026, 7, 12, 15, 0, tzinfo=timezone.utc)
            event_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-07-12T14:00:00+00:00",
                                "event_type": "channel_checked",
                                "server_id": "server-secret-old",
                                "channel_id": "channel-secret-live",
                                "reason_code": "old_result",
                                "metrics": {"fresh_observed": 99, "sent": 99},
                                "draft": "old private draft",
                            },
                            {
                                "created_at": started_at.isoformat(),
                                "event_type": "runtime_started",
                                "server_id": "",
                                "channel_id": "",
                            },
                            {
                                "created_at": "2026-07-12T15:01:00+00:00",
                                "event_type": "channel_checked",
                                "server_id": "server-secret-current",
                                "channel_id": "channel-secret-live",
                                "reason_code": "source_too_thin",
                                "metrics": {
                                    "fresh_observed": 4,
                                    "own_filtered": 1,
                                    "eligible": 2,
                                    "model_called": 1,
                                    "model_requests": 2,
                                    "rejected": 1,
                                },
                                "summary": "Private conversation summary",
                                "draft": "Private generated response",
                                "message_id": "message-secret-1",
                                "user_key": "user-secret-1",
                            },
                            {
                                "created_at": "2026-07-12T15:02:00+00:00",
                                "event_type": "approval_queued",
                                "server_id": "server-secret-current",
                                "channel_id": "channel-secret-live",
                                "reason_code": "approval_queued",
                                "metrics": {"draft_queued": 1},
                            },
                            {
                                "created_at": "2026-07-12T15:02:30+00:00",
                                "event_type": "approval_sent",
                                "server_id": "server-secret-current",
                                "channel_id": "channel-secret-live",
                                "summary": "Manual approval without scanner metrics",
                            },
                            {
                                "created_at": "2026-07-12T15:03:00+00:00",
                                "event_type": "channel_unavailable",
                                "server_id": "server-secret-current",
                                "channel_id": "channel-secret-away",
                                "summary": "Private redirect URL",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            servers = {
                "servers": [
                    {
                        "server_id": "server-secret-current",
                        "label": "Community One",
                        "channels": [
                            {
                                "channel_id": "channel-secret-live",
                                "label": "lobby",
                                "scan_enabled": True,
                            },
                            {
                                "channel_id": "channel-secret-away",
                                "label": "news",
                                "scan_enabled": True,
                            },
                            {
                                "channel_id": "channel-secret-never",
                                "label": "slow-room",
                                "scan_enabled": True,
                            },
                            {
                                "channel_id": "channel-secret-disabled",
                                "label": "disabled-room",
                                "scan_enabled": False,
                            },
                        ],
                    }
                ]
            }
            runtime = {
                "last_started_at": started_at.timestamp(),
                "scan": {"loop": {"estimated_loop_seconds": 120}},
            }

            state = engagement_state(event_file, servers, runtime)

            self.assertEqual("latest_run", state["scope"])
            self.assertEqual(started_at.isoformat(), state["scope_started_at"])
            self.assertEqual(
                {
                    "fresh_observed": 4,
                    "own_filtered": 1,
                    "eligible": 2,
                    "model_called": 1,
                    "model_requests": 2,
                    "draft_queued": 1,
                    "rejected": 1,
                },
                state["totals"],
            )
            self.assertEqual(
                [
                    {"code": "approval_queued", "count": 1},
                    {"code": "source_too_thin", "count": 1},
                ],
                state["reasons"],
            )
            self.assertEqual(120.0, state["expected_revisit_seconds"])
            self.assertEqual(
                [
                    ("slow-room", "never"),
                    ("lobby", "checked"),
                    ("news", "unavailable"),
                ],
                [(item["channel_label"], item["status"]) for item in state["channels"]],
            )
            self.assertEqual(4, state["channels"][1]["last_fresh_observed"])

            encoded = json.dumps(state)
            for sensitive_value in (
                "server-secret-current",
                "channel-secret-live",
                "channel-secret-away",
                "message-secret-1",
                "user-secret-1",
                "Private conversation summary",
                "Private generated response",
                "Private redirect URL",
            ):
                self.assertNotIn(sensitive_value, encoded)

    def test_uses_latest_runtime_event_when_controller_timestamp_is_unavailable(self) -> None:
        with TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events.json"
            event_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-07-12T14:00:00+00:00",
                                "event_type": "channel_checked",
                                "metrics": {"fresh_observed": 7},
                            },
                            {
                                "created_at": "2026-07-12T15:00:00+00:00",
                                "event_type": "runtime_signin_handoff_started",
                            },
                            {
                                "created_at": "2026-07-12T15:01:00+00:00",
                                "event_type": "channel_checked",
                                "metrics": {"fresh_observed": 2},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            state = engagement_state(event_file, {"servers": []}, {})

            self.assertEqual("2026-07-12T15:00:00+00:00", state["scope_started_at"])
            self.assertEqual({"fresh_observed": 2}, state["totals"])


if __name__ == "__main__":
    unittest.main()
