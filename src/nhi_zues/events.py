from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .state_io import mutate_json_file, read_json_file, try_write_json_file


ENGAGEMENT_METRIC_KEYS = (
    "fresh_observed",
    "own_filtered",
    "pending",
    "deferred",
    "eligible",
    "model_called",
    "model_requests",
    "draft_queued",
    "sent",
    "rejected",
    "scanned_messages",
    "newly_visible",
    "backfill_discovered",
    "history_passes",
    "history_rounds",
    "history_retry_added",
    "queued_reviews",
)


@dataclass(frozen=True)
class EventItem:
    created_at: str
    event_type: str
    server_id: str
    channel_id: str
    summary: str
    reason_code: str = ""
    metrics: dict[str, int] = field(default_factory=dict)
    draft: str = ""
    user_key: str = ""
    message_id: str = ""
    target_message_id: str = ""
    target_author: str = ""
    emoji: str = ""


class EventLog:
    def __init__(self, event_file: Path, *, limit: int = 5000) -> None:
        self.event_file = event_file
        self.limit = limit
        self._items = self._load()

    def add(
        self,
        *,
        event_type: str,
        server_id: str,
        channel_id: str,
        summary: str,
        reason_code: str = "",
        metrics: dict | None = None,
        draft: str = "",
        user_key: str = "",
        message_id: str = "",
        target_message_id: str = "",
        target_author: str = "",
        emoji: str = "",
    ) -> EventItem:
        item = EventItem(
            created_at=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            server_id=server_id,
            channel_id=channel_id,
            summary=" ".join(summary.strip().split()),
            reason_code=normalize_reason_code(reason_code),
            metrics=normalize_event_metrics(metrics),
            draft=draft.strip(),
            user_key=user_key,
            message_id=str(message_id or "").strip(),
            target_message_id=str(target_message_id or "").strip(),
            target_author=str(target_author or "").strip(),
            emoji=str(emoji or "").strip(),
        )
        def append_item(payload: dict) -> None:
            rows = list(payload.get("items", []))
            rows.append(asdict(item))
            payload["items"] = rows[-self.limit :]

        mutate_json_file(
            self.event_file,
            default={"items": []},
            mutator=append_item,
        )
        self._items = self._load()
        self._append_app_log(item)
        return item

    def list(self) -> list[EventItem]:
        return list(self._items)

    def _load(self) -> list[EventItem]:
        payload = read_json_file(self.event_file, default={"items": []})
        return [
            EventItem(
                created_at=str(row.get("created_at") or ""),
                event_type=str(row.get("event_type") or ""),
                server_id=str(row.get("server_id") or ""),
                channel_id=str(row.get("channel_id") or ""),
                summary=str(row.get("summary") or ""),
                reason_code=normalize_reason_code(row.get("reason_code")),
                metrics=normalize_event_metrics(row.get("metrics")),
                draft=str(row.get("draft") or ""),
                user_key=str(row.get("user_key") or ""),
                message_id=str(row.get("message_id") or ""),
                target_message_id=str(row.get("target_message_id") or ""),
                target_author=str(row.get("target_author") or ""),
                emoji=str(row.get("emoji") or ""),
            )
            for row in payload.get("items", [])
        ]

    def _save(self) -> None:
        self.event_file.parent.mkdir(parents=True, exist_ok=True)
        try_write_json_file(self.event_file, {"items": [asdict(item) for item in self._items]})

    def _append_app_log(self, item: EventItem) -> None:
        self.event_file.parent.mkdir(parents=True, exist_ok=True)
        line_parts = [
            item.created_at,
            item.event_type,
        ]
        if item.reason_code:
            line_parts.append(f"reason={_log_value(item.reason_code)}")
        if item.metrics:
            line_parts.append(
                f"metrics={json.dumps(item.metrics, ensure_ascii=True, sort_keys=True)}"
            )
        try:
            with (self.event_file.parent / "app.log").open("a", encoding="utf-8") as handle:
                handle.write(" | ".join(line_parts) + "\n")
        except OSError:
            return


def _log_value(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def normalize_reason_code(value) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return cleaned[:64]


def normalize_event_metrics(value) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key in ENGAGEMENT_METRIC_KEYS:
        metric = value.get(key)
        if isinstance(metric, bool) or not isinstance(metric, int) or metric < 0:
            continue
        normalized[key] = metric
    return normalized
