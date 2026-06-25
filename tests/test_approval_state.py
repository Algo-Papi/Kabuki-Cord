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
from nhi_zues.gui import _own_source_block_message, approval_items_state
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

    def test_approval_state_reports_missing_source_ids_without_losing_found_previews(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".state"
            servers_file = root / "servers.json"
            servers_file.write_text(json.dumps({"servers": []}), encoding="utf-8")
            found = MessageRecord(
                server_id="server-1",
                channel_id="channel-1",
                message_id="chat-messages-1-100",
                author="Rook",
                author_id="123",
                text="found source text",
                observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            )
            missing = MessageRecord(
                server_id="server-1",
                channel_id="channel-1",
                message_id="chat-messages-1-101",
                author="Muse",
                author_id="456",
                text="missing source text",
                observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            )
            memory = ConversationMemory(state_dir / "memory.json")
            memory.ingest("channel-1", [found])
            memory.save()
            ApprovalQueue(state_dir / "approvals.json").add(
                server_id="server-1",
                channel_id="channel-1",
                character_name="NHI Zues",
                engagement_type="reply",
                reason="manual response",
                draft="yeah that part is weird",
                source_messages=[found, missing],
            )

            [approval] = approval_items_state(
                SimpleNamespace(state_dir=state_dir, servers_file=servers_file)
            )

            self.assertEqual(["chat-messages-1-101"], approval["source_missing_ids"])
            self.assertEqual(
                ["chat-messages-1-100"],
                [source["message_id"] for source in approval["source_messages"]],
            )
            self.assertEqual("found source text", approval["source_messages"][0]["text"])

    def test_approval_queue_keeps_only_five_newest_items(self) -> None:
        with TemporaryDirectory() as tmp:
            queue = ApprovalQueue(Path(tmp) / "approvals.json")

            for index in range(7):
                queue.add(
                    server_id="server-1",
                    channel_id="channel-1",
                    character_name="NHI Zues",
                    engagement_type="reply",
                    reason=f"reason {index}",
                    draft=f"draft {index}",
                    source_messages=[],
                )

            drafts = [item.draft for item in queue.list()]
            self.assertEqual(["draft 2", "draft 3", "draft 4", "draft 5", "draft 6"], drafts)

    def test_approval_queue_prunes_existing_backlog_on_load(self) -> None:
        with TemporaryDirectory() as tmp:
            queue_file = Path(tmp) / "approvals.json"
            queue = ApprovalQueue(queue_file, max_items=0)
            for index in range(6):
                queue.add(
                    server_id="server-1",
                    channel_id="channel-1",
                    character_name="NHI Zues",
                    engagement_type="reply",
                    reason=f"reason {index}",
                    draft=f"draft {index}",
                    source_messages=[],
                )

            reloaded = ApprovalQueue(queue_file)

            self.assertEqual(
                ["draft 1", "draft 2", "draft 3", "draft 4", "draft 5"],
                [item.draft for item in reloaded.list()],
            )

    def test_find_source_overlap_ignores_blanks_and_stays_in_channel(self) -> None:
        with TemporaryDirectory() as tmp:
            queue = ApprovalQueue(Path(tmp) / "approvals.json")
            source = MessageRecord(
                server_id="server-1",
                channel_id="channel-1",
                message_id="source-1",
                author="Rook",
                author_id="123",
                text="source text",
                observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            )
            item = queue.add(
                server_id="server-1",
                channel_id="channel-1",
                character_name="NHI Zues",
                engagement_type="reply",
                reason="reason",
                draft="draft",
                source_messages=[source],
            )

            self.assertIs(queue.find_source_overlap(channel_id="channel-1", source_message_ids=["", "source-1"]), item)
            self.assertIsNone(queue.find_source_overlap(channel_id="channel-2", source_message_ids=["source-1"]))
            self.assertIsNone(queue.find_source_overlap(channel_id="channel-1", source_message_ids=["", " "]))

    def test_own_source_block_message_blocks_character_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".state"
            card_dir = root / "character_cards"
            card_dir.mkdir()
            (card_dir / "default.json").write_text(
                json.dumps(
                    {
                        "name": "NHI Zues",
                        "system_prompt": "",
                        "style_rules": [],
                        "engagement_rules": [],
                        "aliases": ["nhi zues", "zues"],
                        "trigger_keywords": [],
                    }
                ),
                encoding="utf-8",
            )
            servers_file = root / "servers.json"
            servers_file.write_text(json.dumps({"servers": []}), encoding="utf-8")
            source = MessageRecord(
                server_id="server-1",
                channel_id="channel-1",
                message_id="chat-messages-1-200",
                author="NHI ZuesOnline",
                author_id="self",
                text="i already said the archive chain is the weak part",
                observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            )

            message = _own_source_block_message(
                SimpleNamespace(
                    state_dir=state_dir,
                    character_dir=card_dir,
                    character_card="default.json",
                    servers_file=servers_file,
                ),
                server_id="server-1",
                channel_id="channel-1",
                source_messages=[source],
            )

            self.assertIn("Reply blocked", message)


if __name__ == "__main__":
    unittest.main()
