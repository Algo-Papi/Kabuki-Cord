from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nhi_zues.discarded_approvals import DiscardedApprovalStore, discarded_approval_message


class DiscardedApprovalTests(unittest.TestCase):
    def test_records_and_reloads_source_message_overlap(self) -> None:
        with TemporaryDirectory() as tmp:
            store_file = Path(tmp) / "discarded_approvals.json"
            store = DiscardedApprovalStore(store_file)

            item = store.record(
                server_id="server-1",
                channel_id="channel-1",
                source_message_ids=("source-1", "source-2"),
                draft="nah skip this one",
                reason="operator discarded",
            )

            self.assertIsNotNone(item)
            reloaded = DiscardedApprovalStore(store_file)
            overlaps = reloaded.find_overlap(
                channel_id="channel-1",
                source_message_ids=("source-2",),
            )

            self.assertEqual(1, len(overlaps))
            self.assertIn("already discarded", discarded_approval_message(overlaps))

    def test_ignores_records_without_source_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            store = DiscardedApprovalStore(Path(tmp) / "discarded_approvals.json")

            item = store.record(
                server_id="server-1",
                channel_id="channel-1",
                source_message_ids=("",),
            )

            self.assertIsNone(item)
            self.assertEqual([], store.list())


if __name__ == "__main__":
    unittest.main()
