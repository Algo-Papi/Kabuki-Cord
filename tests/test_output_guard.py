from __future__ import annotations

import unittest

from nhi_zues.output_guard import outgoing_block_reason


class OutputGuardTests(unittest.TestCase):
    def test_blocks_recent_bonkers_identity_escalation_pattern(self) -> None:
        reason = outgoing_block_reason(
            "i heard this selective abduction thing gets mixed with antisemitic propaganda"
        )

        self.assertIn("blocked", reason.lower())

    def test_blocks_edgy_named_reference(self) -> None:
        reason = outgoing_block_reason("some dude claimed sam hyde is connected")

        self.assertIn("blocked", reason.lower())

    def test_allows_normal_ufo_side_comment(self) -> None:
        self.assertEqual(
            "",
            outgoing_block_reason("i still dont trust the android claim without the exact model number"),
        )


if __name__ == "__main__":
    unittest.main()
