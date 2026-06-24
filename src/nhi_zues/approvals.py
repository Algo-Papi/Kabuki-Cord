from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import MessageRecord
from .state_io import write_json_file


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
    def __init__(self, queue_file: Path, max_items: int = 5) -> None:
        self.queue_file = queue_file
        self.max_items = max_items
        self._items = self._load()
        if self._prune_oldest():
            self._save()

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
        self._prune_oldest()
        self._save()
        return item

    def list(self) -> list[ApprovalItem]:
        return list(self._items)

    def get(self, approval_id: str) -> ApprovalItem | None:
        return next((item for item in self._items if item.approval_id == approval_id), None)

    def find_source_overlap(
        self,
        *,
        channel_id: str,
        source_message_ids: tuple[str, ...] | list[str],
    ) -> ApprovalItem | None:
        source_ids = {str(value).strip() for value in source_message_ids if str(value or "").strip()}
        if not source_ids:
            return None
        return next(
            (
                item
                for item in self._items
                if item.channel_id == channel_id and source_ids.intersection(item.source_message_ids)
            ),
            None,
        )

    def update_draft(self, approval_id: str, draft: str) -> ApprovalItem:
        for index, item in enumerate(self._items):
            if item.approval_id != approval_id:
                continue
            updated = ApprovalItem(
                approval_id=item.approval_id,
                created_at=item.created_at,
                server_id=item.server_id,
                channel_id=item.channel_id,
                character_name=item.character_name,
                engagement_type=item.engagement_type,
                reason=item.reason,
                draft=draft,
                source_message_ids=item.source_message_ids,
            )
            self._items[index] = updated
            self._save()
            return updated
        raise KeyError(f"Unknown approval: {approval_id}")

    def remove(self, approval_id: str) -> bool:
        original_count = len(self._items)
        self._items = [item for item in self._items if item.approval_id != approval_id]
        changed = len(self._items) != original_count
        if changed:
            self._save()
        return changed

    def clear(self) -> int:
        count = len(self._items)
        if count:
            self._items = []
            self._save()
        return count

    def _load(self) -> list[ApprovalItem]:
        if not self.queue_file.exists():
            return []
        payload = json.loads(self.queue_file.read_text(encoding="utf-8-sig"))
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
        write_json_file(self.queue_file, payload)

    def _prune_oldest(self) -> bool:
        if self.max_items <= 0 or len(self._items) <= self.max_items:
            return False
        self._items = self._items[-self.max_items :]
        return True


def _approval_id(*, channel_id: str, draft: str, source_ids: tuple[str, ...]) -> str:
    raw = "\n".join((channel_id, draft, *source_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
