from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.gui import _estimated_channel_scan_seconds, _estimated_loop_seconds


def config(**overrides):
    values = {
        "scanner_channel_settle_seconds": 12.0,
        "scanner_max_channels_per_cycle": 2,
        "scanner_min_channel_delay_seconds": 10.0,
        "scanner_max_channel_delay_seconds": 20.0,
        "scanner_cycle_sleep_seconds": 45.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class RuntimeEstimateTests(unittest.TestCase):
    def test_channel_scan_estimate_clamps_between_floor_and_ceiling(self) -> None:
        self.assertEqual(18.0, _estimated_channel_scan_seconds(config(scanner_channel_settle_seconds=0.0)))
        self.assertEqual(15.0, _estimated_channel_scan_seconds(config(scanner_channel_settle_seconds=-10.0)))
        self.assertEqual(90.0, _estimated_channel_scan_seconds(config(scanner_channel_settle_seconds=120.0)))

    def test_loop_estimate_includes_scan_time_between_channel_delay_and_cycle_sleep(self) -> None:
        estimate = _estimated_loop_seconds(config(), 5)

        self.assertEqual(315.0, estimate)

    def test_loop_estimate_handles_empty_counts_and_nonpositive_cycle_size(self) -> None:
        self.assertEqual(0.0, _estimated_loop_seconds(config(), 0))
        self.assertEqual(
            150.0,
            _estimated_loop_seconds(config(scanner_max_channels_per_cycle=0, scanner_cycle_sleep_seconds=20.0), 3),
        )


if __name__ == "__main__":
    unittest.main()
