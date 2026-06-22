from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class EventItem:
    created_at: str
    event_type: str
    server_id: str
    channel_id: str
    summary: str
    draft: str = ""
    user_key: str = ""


class EventLog:
    def __init__(self, event_file: Path, *, limit: int = 500) -> None:
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
    ) -> EventItem:
        item = EventItem(
            created_at=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            server_id=server_id,
            channel_id=channel_id,
            summary=" ".join(summary.strip().split()),
            draft=draft.strip(),
            user_key=user_key,
        )
        self._items.append(item)
        self._items = self._items[-self.limit :]
        self._save()
        return item

    def list(self) -> list[EventItem]:
        return list(self._items)

    def _load(self) -> list[EventItem]:
        if not self.event_file.exists():
            return []
        payload = json.loads(self.event_file.read_text(encoding="utf-8-sig"))
        return [EventItem(**row) for row in payload.get("items", [])]

    def _save(self) -> None:
        self.event_file.parent.mkdir(parents=True, exist_ok=True)
        self.event_file.write_text(
            json.dumps({"items": [asdict(item) for item in self._items]}, indent=2),
            encoding="utf-8",
        )
