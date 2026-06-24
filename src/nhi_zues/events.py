from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .state_io import try_write_json_file


@dataclass(frozen=True)
class EventItem:
    created_at: str
    event_type: str
    server_id: str
    channel_id: str
    summary: str
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
            draft=draft.strip(),
            user_key=user_key,
            message_id=str(message_id or "").strip(),
            target_message_id=str(target_message_id or "").strip(),
            target_author=str(target_author or "").strip(),
            emoji=str(emoji or "").strip(),
        )
        self._items.append(item)
        self._items = self._items[-self.limit :]
        self._save()
        self._append_app_log(item)
        return item

    def list(self) -> list[EventItem]:
        return list(self._items)

    def _load(self) -> list[EventItem]:
        if not self.event_file.exists():
            return []
        payload = json.loads(self.event_file.read_text(encoding="utf-8-sig"))
        return [
            EventItem(
                created_at=str(row.get("created_at") or ""),
                event_type=str(row.get("event_type") or ""),
                server_id=str(row.get("server_id") or ""),
                channel_id=str(row.get("channel_id") or ""),
                summary=str(row.get("summary") or ""),
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
            f"server={_log_value(item.server_id)}",
            f"channel={_log_value(item.channel_id)}",
        ]
        if item.user_key:
            line_parts.append(f"user={_log_value(item.user_key)}")
        if item.message_id:
            line_parts.append(f"message={_log_value(item.message_id)}")
        if item.target_message_id:
            line_parts.append(f"target_message={_log_value(item.target_message_id)}")
        if item.target_author:
            line_parts.append(f"target_author={_log_value(item.target_author)}")
        if item.emoji:
            line_parts.append(f"emoji={_log_value(item.emoji)}")
        if item.summary:
            line_parts.append(f"summary={_log_value(item.summary)}")
        if item.draft:
            line_parts.append(f"draft={_log_value(item.draft)}")
        try:
            with (self.event_file.parent / "app.log").open("a", encoding="utf-8") as handle:
                handle.write(" | ".join(line_parts) + "\n")
        except OSError:
            return


def _log_value(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)
