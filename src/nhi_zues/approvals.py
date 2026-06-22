from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import MessageRecord


@dataclass(frozen=True)
class ApprovalItem:
    approval_id: str
    created_at: str
    server_id: str
    channel_id: str
    character_name: str
    engagement_type: str
    reason: str
    draft: str
    source_message_ids: tuple[str, ...] = field(default_factory=tuple)


class ApprovalQueue:
    def __init__(self, queue_file: Path) -> None:
        self.queue_file = queue_file
        self._items = self._load()

    def add(
        self,
        *,
        server_id: str,
        channel_id: str,
        character_name: str,
        engagement_type: str,
        reason: str,
        draft: str,
        source_messages: list[MessageRecord],
    ) -> ApprovalItem:
        source_ids = tuple(message.message_id for message in source_messages)
        approval_id = _approval_id(channel_id=channel_id, draft=draft, source_ids=source_ids)
        existing = next((item for item in self._items if item.approval_id == approval_id), None)
        if existing:
            return existing

        item = ApprovalItem(
            approval_id=approval_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=server_id,
            channel_id=channel_id,
            character_name=character_name,
            engagement_type=engagement_type,
            reason=reason,
            draft=draft,
            source_message_ids=source_ids,
        )
        self._items.append(item)
        self._save()
        return item

    def list(self) -> list[ApprovalItem]:
        return list(self._items)

    def _load(self) -> list[ApprovalItem]:
        if not self.queue_file.exists():
            return []
        payload = json.loads(self.queue_file.read_text(encoding="utf-8"))
        return [
            ApprovalItem(
                approval_id=row["approval_id"],
                created_at=row["created_at"],
                server_id=row["server_id"],
                channel_id=row["channel_id"],
                character_name=row["character_name"],
                engagement_type=row["engagement_type"],
                reason=row["reason"],
                draft=row["draft"],
                source_message_ids=tuple(row.get("source_message_ids", [])),
            )
            for row in payload.get("items", [])
        ]

    def _save(self) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [asdict(item) for item in self._items]}
        self.queue_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _approval_id(*, channel_id: str, draft: str, source_ids: tuple[str, ...]) -> str:
    raw = "\n".join((channel_id, draft, *source_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
