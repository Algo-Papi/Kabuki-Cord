from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.approvals import ApprovalQueue
from nhi_zues.gui import approval_items_state
from nhi_zues.memory import ConversationMemory
from nhi_zues.models import MessageRecord


class ApprovalStateTests(unittest.TestCase):
    def test_approval_state_includes_route_labels_and_source_message(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".state"
            servers_file = root / "servers.json"
            servers_file.write_text(
                json.dumps(
                    {
                        "servers": [
                            {
                                "server_id": "server-1",
                                "label": "Test Server",
                                "channels": [
                                    {
                                        "channel_id": "channel-1",
                                        "label": "general",
                                        "channel_type": "text",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            message = MessageRecord(
                server_id="server-1",
                channel_id="channel-1",
                message_id="chat-messages-1-200",
                author="Rook",
                author_id="123",
                text="this is the message being answered",
                observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            )
            memory = ConversationMemory(state_dir / "memory.json")
            memory.ingest("channel-1", [message])
            memory.save()
            ApprovalQueue(state_dir / "approvals.json").add(
                server_id="server-1",
                channel_id="channel-1",
                character_name="NHI Zues",
                engagement_type="reply",
                reason="manual response",
                draft="yeah that part is weird",
                source_messages=[message],
            )

            [approval] = approval_items_state(
                SimpleNamespace(state_dir=state_dir, servers_file=servers_file)
            )

            self.assertEqual("Test Server", approval["server_label"])
            self.assertEqual("general", approval["channel_label"])
            self.assertEqual("text", approval["channel_type"])
            self.assertEqual([], approval["source_missing_ids"])
            self.assertEqual("Rook", approval["source_messages"][0]["author"])
            self.assertEqual("this is the message being answered", approval["source_messages"][0]["text"])


if __name__ == "__main__":
    unittest.main()
