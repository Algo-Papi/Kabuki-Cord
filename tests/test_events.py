from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.events import EventLog


class EventLogTests(unittest.TestCase):
    def test_loads_legacy_rows_without_link_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events.json"
            event_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-06-24T10:00:00+00:00",
                                "event_type": "message_sent",
                                "server_id": "server",
                                "channel_id": "channel",
                                "summary": "sent",
                                "draft": "old row",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            [item] = EventLog(event_file).list()

            self.assertEqual("", item.message_id)
            self.assertEqual("", item.target_message_id)
            self.assertEqual("", item.target_author)
            self.assertEqual("", item.emoji)
            self.assertEqual("", item.reason_code)
            self.assertEqual({}, item.metrics)

    def test_persists_action_link_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events.json"
            EventLog(event_file).add(
                event_type="reaction_added",
                server_id="server",
                channel_id="channel",
                summary="Added reaction.",
                draft="target text",
                message_id="chat-messages-1-2",
                target_message_id="chat-messages-1-2",
                target_author="Rook",
                emoji="\U0001f602",
                reason_code="Draft Ready",
                metrics={"eligible": 1, "model_called": 1},
            )

            [item] = EventLog(event_file).list()

            self.assertEqual("chat-messages-1-2", item.message_id)
            self.assertEqual("chat-messages-1-2", item.target_message_id)
            self.assertEqual("Rook", item.target_author)
            self.assertEqual("\U0001f602", item.emoji)
            self.assertEqual("draft_ready", item.reason_code)
            self.assertEqual({"eligible": 1, "model_called": 1}, item.metrics)

    def test_metrics_are_allowlisted_nonnegative_integers(self) -> None:
        with TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events.json"
            EventLog(event_file).add(
                event_type="channel_checked",
                server_id="server",
                channel_id="channel",
                summary="checked",
                reason_code=" Source/Too Thin ",
                metrics={
                    "fresh_observed": 4,
                    "own_filtered": 1,
                    "sent": -1,
                    "eligible": True,
                    "model_called": "1",
                    "unknown": 99,
                },
            )

            [item] = EventLog(event_file).list()

            self.assertEqual("source_too_thin", item.reason_code)
            self.assertEqual({"fresh_observed": 4, "own_filtered": 1}, item.metrics)

    def test_app_log_does_not_duplicate_content_or_identifiers(self) -> None:
        with TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events.json"
            EventLog(event_file).add(
                event_type="message_sent",
                server_id="sensitive-server-9821",
                channel_id="sensitive-channel-7314",
                summary="Private summary for Rowan",
                draft="This is private draft text",
                user_key="sensitive-user-4412",
                message_id="sensitive-message-8823",
                target_message_id="sensitive-target-2291",
                target_author="Rowan Private",
                reason_code="sent",
                metrics={"sent": 1},
            )

            app_log = (event_file.parent / "app.log").read_text(encoding="utf-8")

            self.assertIn("message_sent", app_log)
            self.assertIn('reason="sent"', app_log)
            self.assertIn('metrics={"sent": 1}', app_log)
            for sensitive_value in (
                "sensitive-server-9821",
                "sensitive-channel-7314",
                "Private summary for Rowan",
                "This is private draft text",
                "sensitive-user-4412",
                "sensitive-message-8823",
                "sensitive-target-2291",
                "Rowan Private",
            ):
                self.assertNotIn(sensitive_value, app_log)


if __name__ == "__main__":
    unittest.main()
