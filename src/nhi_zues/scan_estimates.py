from __future__ import annotations

import math

from .config import AppConfig


def estimated_channel_scan_seconds(config: AppConfig) -> float:
    return max(15.0, min(90.0, float(config.scanner_channel_settle_seconds) + 18.0))


def estimated_loop_seconds(config: AppConfig, channel_count: int) -> float:
    total = max(0, int(channel_count or 0))
    if total <= 0:
        return 0.0
    per_channel = estimated_channel_scan_seconds(config)
    per_cycle = max(1, int(config.scanner_max_channels_per_cycle or 1))
    cycle_count = math.ceil(total / per_cycle)
    between_channel_delays = max(0, total - cycle_count)
    average_delay = (
        max(0.0, float(config.scanner_min_channel_delay_seconds))
        + max(0.0, float(config.scanner_max_channel_delay_seconds))
    ) / 2
    return (
        total * per_channel
        + between_channel_delays * average_delay
        + cycle_count * max(0.0, float(config.scanner_cycle_sleep_seconds))
    )
