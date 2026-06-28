from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nhi_zues.gui as gui
from nhi_zues.approvals import ApprovalQueue
from nhi_zues.discarded_approvals import DiscardedApprovalStore
from nhi_zues.memory import ConversationMemory
from nhi_zues.models import DraftDecision, MessageRecord


class FakeCharacterStore:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def for_server(self, *_args, **_kwargs):
        return SimpleNamespace(name="NHI Zues", aliases=("nhi zues",))


class GuiManualApprovalTests(unittest.TestCase):
    def test_manual_history_response_ignores_prior_discard(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = SimpleNamespace(
                state_dir=root / ".state",
                character_dir=root / "character_cards",
                character_card="default.json",
                servers_file=root / "servers.json",
            )
            source = _message("source-1", text="selected history message")
            memory = ConversationMemory(config.state_dir / "memory.json")
            memory.ingest("channel-1", [source])
            memory.save()
            DiscardedApprovalStore(config.state_dir / "discarded_approvals.json").record(
                server_id="server-1",
                channel_id="channel-1",
                source_message_ids=(source.message_id,),
                draft="discarded older draft",
                reason="discarded by operator",
            )

            async def fake_generate_manual_decision(_config, **kwargs):
                self.assertEqual([source.message_id], [m.message_id for m in kwargs["source_messages"]])
                return DraftDecision(
                    should_reply=True,
                    reason="manual selected history message",
                    draft="new manual draft",
                    engagement_type="manual",
                    requires_approval=True,
                )

            with (
                patch.object(gui, "load_config", return_value=config),
                patch.object(gui, "_own_source_block_message", return_value=""),
                patch.object(gui, "_generate_manual_decision", new=fake_generate_manual_decision),
                patch.object(gui, "CharacterCardStore", FakeCharacterStore),
            ):
                gui.create_manual_approval(
                    {
                        "server_id": "server-1",
                        "channel_id": "channel-1",
                        "target_message_id": source.message_id,
                    }
                )

            queued = ApprovalQueue(config.state_dir / "approvals.json").list()
            self.assertEqual(1, len(queued))
            self.assertEqual("<@123> new manual draft", queued[0].draft)
            self.assertEqual((source.message_id,), queued[0].source_message_ids)
            self.assertTrue(
                DiscardedApprovalStore(config.state_dir / "discarded_approvals.json").find_overlap(
                    channel_id="channel-1",
                    source_message_ids=(source.message_id,),
                )
            )

    def test_manual_user_suggest_ignores_prior_discard(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = SimpleNamespace(
                state_dir=root / ".state",
                character_dir=root / "character_cards",
                character_card="default.json",
                servers_file=root / "servers.json",
            )
            older = _message("source-1", text="older point from the same user")
            latest = _message("source-2", text="latest point from the same user")
            memory = ConversationMemory(config.state_dir / "memory.json")
            memory.ingest("channel-1", [older, latest])
            memory.save()
            DiscardedApprovalStore(config.state_dir / "discarded_approvals.json").record(
                server_id="server-1",
                channel_id="channel-1",
                source_message_ids=(latest.message_id,),
                draft="dismissed suggestion",
                reason="discarded by operator",
            )

            async def fake_generate_manual_decision(_config, **kwargs):
                self.assertEqual(
                    [older.message_id, latest.message_id],
                    [m.message_id for m in kwargs["source_messages"]],
                )
                return DraftDecision(
                    should_reply=True,
                    reason="manual user suggestion",
                    draft="fresh forced draft",
                    engagement_type="manual",
                    requires_approval=True,
                )

            with (
                patch.object(gui, "load_config", return_value=config),
                patch.object(gui, "_own_source_block_message", return_value=""),
                patch.object(gui, "_generate_manual_decision", new=fake_generate_manual_decision),
                patch.object(gui, "CharacterCardStore", FakeCharacterStore),
            ):
                gui.create_manual_approval(
                    {
                        "server_id": "server-1",
                        "channel_id": "channel-1",
                        "target_user_key": "discord:123",
                        "force_manual": True,
                    }
                )

            queued = ApprovalQueue(config.state_dir / "approvals.json").list()
            self.assertEqual(1, len(queued))
            self.assertEqual("<@123> fresh forced draft", queued[0].draft)
            self.assertEqual((older.message_id, latest.message_id), queued[0].source_message_ids)
            self.assertIn("Manual override", queued[0].reason)


def _message(message_id: str, *, text: str = "source text") -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author="Rook",
        author_id="123",
        text=text,
        observed_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
    )


if __name__ == "__main__":
    unittest.main()
