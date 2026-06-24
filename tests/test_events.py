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
            )

            [item] = EventLog(event_file).list()

            self.assertEqual("chat-messages-1-2", item.message_id)
            self.assertEqual("chat-messages-1-2", item.target_message_id)
            self.assertEqual("Rook", item.target_author)
            self.assertEqual("\U0001f602", item.emoji)


if __name__ == "__main__":
    unittest.main()
