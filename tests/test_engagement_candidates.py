from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.memory import ConversationMemory
from nhi_zues.models import MessageRecord


NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def message(message_id: str, *, channel_id: str = "channel-1", text: str = "hello") -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id=channel_id,
        message_id=message_id,
        author="Rook",
        author_id="user-1",
        text=text,
        observed_at=NOW,
    )


class EngagementCandidateTests(unittest.TestCase):
    def test_deferred_batch_reopens_only_after_generation_advances(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(Path(tmp) / "memory.json")
            first = message("message-1")
            memory.ingest("channel-1", [first])
            observed = memory.observe_reply_candidates("channel-1", [first], now=NOW)
            memory.save()

            self.assertIsNotNone(observed)
            ready = memory.ready_reply_candidates("channel-1", now=NOW)
            self.assertEqual(("message-1",), ready.message_ids)
            self.assertTrue(
                memory.defer_reply_candidates(ready, reason="too thin", now=NOW)
            )
            self.assertIsNone(memory.ready_reply_candidates("channel-1", now=NOW))
            self.assertEqual(
                {"pending": 0, "deferred": 1, "eligible": 0},
                memory.reply_candidate_counts("channel-1", now=NOW),
            )

            memory.observe_reply_candidates("channel-1", [first], now=NOW + timedelta(seconds=1))
            self.assertIsNone(memory.ready_reply_candidates("channel-1", now=NOW))

            second = message("message-2")
            memory.ingest("channel-1", [second])
            memory.observe_reply_candidates("channel-1", [second], now=NOW + timedelta(seconds=2))
            advanced = memory.ready_reply_candidates("channel-1", now=NOW + timedelta(seconds=2))
            self.assertEqual(("message-1", "message-2"), advanced.message_ids)
            self.assertGreater(advanced.generation, ready.generation)

    def test_eligible_state_is_distinct_and_content_free(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            memory = ConversationMemory(path)
            source = message("message-1", text="private source text")
            memory.ingest("channel-1", [source])
            batch = memory.observe_reply_candidates("channel-1", [source], now=NOW)
            memory.save()

            self.assertTrue(
                memory.mark_reply_candidates_eligible(
                    batch,
                    reason="clear reply opportunity",
                    now=NOW,
                )
            )
            self.assertIsNone(memory.ready_reply_candidates("channel-1", now=NOW))
            eligible = memory.eligible_reply_candidates("channel-1", now=NOW)
            self.assertEqual("eligible", eligible.status)
            self.assertEqual("clear reply opportunity", eligible.reason)
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 1},
                memory.reply_candidate_counts(now=NOW),
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            item = payload["reply_candidates"]["channel-1"]["items"][0]
            self.assertEqual(
                {"message_id", "queued_at", "expires_at", "generation"},
                set(item),
            )
            self.assertNotIn("private source text", json.dumps(payload["reply_candidates"]))
            self.assertNotIn("Rook", json.dumps(payload["reply_candidates"]))

    def test_stale_defer_cannot_hide_newer_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            first_writer = ConversationMemory(path)
            second_writer = ConversationMemory(path)
            first = message("message-1")
            second = message("message-2")

            first_writer.observe_reply_candidates("channel-1", [first], now=NOW)
            stale_batch = first_writer.ready_reply_candidates("channel-1", now=NOW)
            second_writer.observe_reply_candidates(
                "channel-1",
                [second],
                now=NOW + timedelta(seconds=1),
            )

            self.assertFalse(
                first_writer.defer_reply_candidates(
                    stale_batch,
                    reason="stale evaluation",
                    now=NOW + timedelta(seconds=2),
                )
            )
            current = first_writer.ready_reply_candidates(
                "channel-1",
                now=NOW + timedelta(seconds=2),
            )
            self.assertEqual(("message-1", "message-2"), current.message_ids)

    def test_stale_resolution_preserves_newer_generation(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            first_writer = ConversationMemory(path)
            second_writer = ConversationMemory(path)
            first_writer.observe_reply_candidates("channel-1", [message("message-1")], now=NOW)
            stale_batch = first_writer.ready_reply_candidates("channel-1", now=NOW)
            second_writer.observe_reply_candidates(
                "channel-1",
                [message("message-2")],
                now=NOW + timedelta(seconds=1),
            )

            self.assertEqual(
                1,
                first_writer.resolve_reply_candidates(
                    "channel-1",
                    stale_batch,
                    now=NOW + timedelta(seconds=2),
                ),
            )
            remaining = first_writer.ready_reply_candidates(
                "channel-1",
                now=NOW + timedelta(seconds=2),
            )
            self.assertEqual(("message-2",), remaining.message_ids)

    def test_resolving_selected_ids_reopens_remaining_items(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(Path(tmp) / "memory.json")
            memory.observe_reply_candidates(
                "channel-1",
                [message("message-1"), message("message-2")],
                now=NOW,
            )
            batch = memory.ready_reply_candidates("channel-1", now=NOW)
            memory.mark_reply_candidates_eligible(batch, reason="worthy", now=NOW)

            self.assertEqual(
                1,
                memory.resolve_reply_candidates("channel-1", ["message-1"], now=NOW),
            )
            remaining = memory.pending_reply_candidates("channel-1", now=NOW)
            self.assertEqual(("message-2",), remaining.message_ids)
            self.assertEqual(("message-2",), memory.ready_reply_candidates("channel-1", now=NOW).message_ids)

    def test_candidate_and_batch_bounds_keep_newest_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(
                Path(tmp) / "memory.json",
                max_candidates_per_channel=12,
                candidate_batch_size=8,
            )
            messages = [message(f"message-{index:02d}") for index in range(15)]
            memory.observe_reply_candidates("channel-1", messages, now=NOW)

            ready = memory.ready_reply_candidates("channel-1", now=NOW)
            self.assertEqual(
                tuple(f"message-{index:02d}" for index in range(7, 15)),
                ready.message_ids,
            )
            self.assertEqual(
                {"pending": 12, "deferred": 0, "eligible": 0},
                memory.reply_candidate_counts("channel-1", now=NOW),
            )

    def test_ttl_prunes_items_independently(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(
                Path(tmp) / "memory.json",
                candidate_ttl_seconds=60,
            )
            memory.observe_reply_candidates("channel-1", [message("message-1")], now=NOW)
            memory.observe_reply_candidates(
                "channel-1",
                [message("message-2")],
                now=NOW + timedelta(seconds=30),
            )

            self.assertEqual(1, memory.prune_reply_candidates(now=NOW + timedelta(seconds=61)))
            remaining = memory.ready_reply_candidates(
                "channel-1",
                now=NOW + timedelta(seconds=61),
            )
            self.assertEqual(("message-2",), remaining.message_ids)

    def test_zero_ttl_disables_and_clears_persisted_candidates(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            enabled = ConversationMemory(path)
            enabled.observe_reply_candidates("channel-1", [message("message-1")], now=NOW)

            disabled = ConversationMemory(path, candidate_ttl_seconds=0)
            self.assertIsNone(
                disabled.observe_reply_candidates("channel-1", [message("message-2")], now=NOW)
            )
            self.assertEqual(
                {"pending": 0, "deferred": 0, "eligible": 0},
                disabled.reply_candidate_counts(now=NOW),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual({}, payload["reply_candidates"])

    def test_messages_by_ids_preserves_requested_order(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(Path(tmp) / "memory.json")
            messages = [message("message-1"), message("message-2")]
            memory.ingest("channel-1", messages)

            selected = memory.messages_by_ids(
                "channel-1",
                ["message-2", "missing", "message-1", "message-2"],
            )
            self.assertEqual(["message-2", "message-1"], [item.message_id for item in selected])

    def test_normal_memory_save_does_not_clobber_newer_candidate_state(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            stale = ConversationMemory(path)
            stale.load()
            writer = ConversationMemory(path)
            writer.observe_reply_candidates("channel-1", [message("message-1")], now=NOW)

            stale.ingest("channel-2", [message("other", channel_id="channel-2")])
            stale.save()

            reloaded = ConversationMemory(path)
            reloaded.load()
            ready = reloaded.ready_reply_candidates("channel-1", now=NOW)
            self.assertEqual(("message-1",), ready.message_ids)


if __name__ == "__main__":
    unittest.main()
