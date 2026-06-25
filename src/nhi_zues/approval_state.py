from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .approvals import ApprovalQueue
from .message_view import message_preview, sorted_message_rows


def approval_items_state(config) -> list[dict]:
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    server_labels, channel_labels = approval_config_indexes(config.servers_file)
    memory_payload = read_json(config.state_dir / "memory.json", default={"channels": {}})
    channel_rows = {
        str(channel_id): sorted_message_rows(rows)
        for channel_id, rows in memory_payload.get("channels", {}).items()
    }
    result: list[dict] = []
    for item in queue.list():
        payload = asdict(item)
        channel_meta = channel_labels.get(item.channel_id, {})
        source_ids = [str(value) for value in item.source_message_ids if str(value or "").strip()]
        rows_by_id = {
            str(row.get("message_id") or ""): row
            for row in channel_rows.get(item.channel_id, [])
            if str(row.get("message_id") or "")
        }
        source_messages = [
            message_preview(rows_by_id[source_id])
            for source_id in source_ids
            if source_id in rows_by_id
        ]
        payload.update(
            {
                "server_label": server_labels.get(item.server_id) or item.server_id,
                "channel_label": channel_meta.get("label") or item.channel_id,
                "channel_type": channel_meta.get("channel_type") or "text",
                "channel_category": channel_meta.get("category") or "",
                "source_messages": source_messages,
                "source_missing_ids": [
                    source_id for source_id in source_ids if source_id not in rows_by_id
                ],
            }
        )
        result.append(payload)
    return result


def approval_config_indexes(servers_file: Path) -> tuple[dict[str, str], dict[str, dict]]:
    payload = read_json(servers_file, default={"servers": []})
    server_labels: dict[str, str] = {}
    channel_labels: dict[str, dict] = {}
    for server in payload.get("servers", []):
        server_id = str(server.get("server_id") or "").strip()
        if not server_id:
            continue
        server_labels[server_id] = str(server.get("label") or server_id)
        for channel in server.get("channels", []):
            channel_id = str(channel.get("channel_id") or "").strip()
            if not channel_id:
                continue
            channel_labels[channel_id] = {
                "server_id": server_id,
                "server_label": server_labels[server_id],
                "label": str(channel.get("label") or channel_id),
                "channel_type": str(channel.get("channel_type") or "text"),
                "category": str(channel.get("category") or ""),
            }
    return server_labels, channel_labels


def read_json(path: Path, *, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))
