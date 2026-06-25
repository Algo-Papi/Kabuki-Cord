from __future__ import annotations

from collections.abc import Callable


IconPathResolver = Callable[[str, str], str]


def merge_discovered_servers(
    payload: dict,
    discovered: list[dict],
    *,
    icon_path_for_server: IconPathResolver | None = None,
) -> tuple[dict, dict]:
    server_list = payload.get("servers")
    if not isinstance(server_list, list):
        server_list = []

    by_id: dict[str, dict] = {}
    for item in server_list:
        if isinstance(item, dict) and item.get("server_id"):
            by_id[str(item["server_id"])] = dict(item)

    stats = {
        "discovered": len(discovered),
        "added": 0,
        "added_server_ids": [],
        "removed": 0,
        "removed_server_ids": [],
        "updated": 0,
        "channels_discovered": 0,
        "channels_added": 0,
        "channels_updated": 0,
    }
    next_server_list: list[dict] = []
    discovered_ids: set[str] = set()
    for server in discovered:
        server_id = str(server.get("server_id") or "").strip()
        if not server_id:
            continue
        discovered_ids.add(server_id)
        label = str(server.get("label") or "")
        existing = by_id.get(server_id)
        if existing is None:
            existing = {
                "server_id": server_id,
                "label": label,
                "character_card": None,
                "safety_review_enabled": False,
                "channels": [],
            }
            stats["added"] += 1
            stats["added_server_ids"].append(server_id)
        if label and str(existing.get("label") or "").strip() != label:
            existing["label"] = label
            stats["updated"] += 1
        icon_url = str(server.get("icon_url") or "")
        if icon_path_for_server and icon_url:
            icon_path = icon_path_for_server(server_id, icon_url)
            if icon_path:
                existing["icon_path"] = icon_path
        channel_stats = merge_channels(existing, server.get("channels", []))
        stats["channels_discovered"] += channel_stats["discovered"]
        stats["channels_added"] += channel_stats["added"]
        stats["channels_updated"] += channel_stats["updated"]
        next_server_list.append(existing)

    stats["removed_server_ids"] = [
        server_id for server_id in by_id.keys() if server_id not in discovered_ids
    ]
    stats["removed"] = len(stats["removed_server_ids"])
    return {**payload, "servers": next_server_list}, stats


def merge_channels(server: dict, discovered_channels: list[dict]) -> dict[str, int]:
    existing_channels = server.get("channels")
    if not isinstance(existing_channels, list):
        existing_channels = []

    by_id: dict[str, dict] = {}
    for item in existing_channels:
        if isinstance(item, dict) and item.get("channel_id"):
            by_id[str(item["channel_id"])] = dict(item)

    updated = 0
    added = 0
    next_channels: list[dict] = []
    for channel in discovered_channels:
        channel_id = str(channel.get("channel_id") or "")
        if not channel_id:
            continue
        existing = by_id.get(channel_id)
        if existing is None:
            existing = {
                "channel_id": channel_id,
                "label": str(channel.get("label") or ""),
                "channel_type": str(channel.get("channel_type") or "text"),
                "category": str(channel.get("category") or ""),
                "parent_channel_id": str(channel.get("parent_channel_id") or ""),
                "scan_enabled": False,
                "engage_enabled": False,
                "react_enabled": False,
                "auto_respond_enabled": False,
            }
            added += 1
        else:
            for key in ("label", "channel_type", "category", "parent_channel_id"):
                value = str(channel.get(key) or "")
                if value and str(existing.get(key) or "") != value:
                    existing[key] = value
                    updated += 1
        next_channels.append(existing)

    discovered_ids = {str(channel.get("channel_id") or "") for channel in discovered_channels}
    next_channels.extend(
        channel
        for channel in existing_channels
        if (
            isinstance(channel, dict)
            and str(channel.get("channel_id") or "") not in discovered_ids
            and str(channel.get("label") or "").strip()
        )
    )
    server["channels"] = next_channels
    return {"discovered": len(discovered_channels), "added": added, "updated": updated}
