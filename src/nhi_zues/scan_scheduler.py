from __future__ import annotations


def active_targets(config):
    targets = list(config.channels)
    if not targets:
        return []
    if bool(getattr(config, "safety_review_exclusive", True)):
        sweep_targets = [target for target in targets if getattr(target, "safety_review_enabled", False)]
        if sweep_targets:
            return sweep_targets
    return targets


def normalized_cursor(config, cursor: int) -> int:
    total = len(active_targets(config))
    if not total:
        return 0
    return int(cursor or 0) % total


def planned_targets(config, cursor: int):
    targets = active_targets(config)
    if not targets:
        return []
    start = normalized_cursor(config, cursor)
    return targets[start:] + targets[:start]


def target_index(config, target) -> int:
    for index, item in enumerate(active_targets(config)):
        if item.server_id == target.server_id and item.channel_id == target.channel_id:
            return index
    return -1


def limit_targets(config, targets, cursor: int) -> tuple[list, int]:
    limit = max(1, config.scanner_max_channels_per_cycle)
    all_targets = active_targets(config)
    if not targets or not all_targets:
        return [], normalized_cursor(config, cursor)
    current_loop_remaining = len(all_targets) - normalized_cursor(config, cursor)
    selected = list(targets)[: min(limit, current_loop_remaining)]
    next_cursor = normalized_cursor(config, cursor)
    if selected:
        last_index = target_index(config, selected[-1])
        if last_index >= 0:
            next_cursor = (last_index + 1) % len(all_targets)
    return selected, next_cursor


def select_targets(config, cursor: int, targets) -> tuple[list, int, bool]:
    start_cursor = normalized_cursor(config, cursor)
    selected, next_cursor = limit_targets(config, targets, cursor)
    return selected, next_cursor, bool(selected) and next_cursor <= start_cursor


def loop_state(
    config,
    cursor: int,
    completed_loop_count: int,
    *,
    planned_targets,
    selected_targets,
    will_complete_loop: bool,
    target=None,
    completed_in_loop: int | None = None,
) -> dict[str, int | bool]:
    total = len(active_targets(config))
    cursor = normalized_cursor(config, cursor)
    completed_loops = max(0, int(completed_loop_count or 0))
    position = 0
    if target is not None:
        index = target_index(config, target)
        if index >= 0:
            position = index + 1
    if completed_in_loop is None:
        completed_in_loop = cursor
    return {
        "completed_loops": completed_loops,
        "current_loop": completed_loops + 1,
        "total_channels": total,
        "cursor": cursor,
        "position": position,
        "completed_in_loop": max(0, min(int(completed_in_loop or 0), total)),
        "selected_count": len(list(selected_targets or ())),
        "planned_count": len(list(planned_targets or ())),
        "will_complete_loop": bool(will_complete_loop),
    }
