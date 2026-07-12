from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import MessageRecord
from .state_io import mutate_json_file, read_json_file, write_json_file


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

        def add_item(payload: dict) -> ApprovalItem:
            items = _items_from_payload(payload)
            existing = next((row for row in items if row.approval_id == approval_id), None)
            if existing:
                return existing
            items.append(item)
            if self.max_items > 0:
                items = items[-self.max_items :]
            payload["items"] = [asdict(row) for row in items]
            return item

        _, result = mutate_json_file(
            self.queue_file,
            default={"items": []},
            mutator=add_item,
        )
        self._items = [
            result if row.approval_id == result.approval_id and row == result else row
            for row in self._load()
        ]
        return result

    def list(self) -> list[ApprovalItem]:
        self._reload()
        return list(self._items)

    def get(self, approval_id: str) -> ApprovalItem | None:
        self._reload()
        return next((item for item in self._items if item.approval_id == approval_id), None)

    def find_source_overlap(
        self,
        *,
        channel_id: str,
        source_message_ids: tuple[str, ...] | list[str],
    ) -> ApprovalItem | None:
        self._reload()
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
        def update_item(payload: dict) -> ApprovalItem:
            items = _items_from_payload(payload)
            for index, item in enumerate(items):
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
                items[index] = updated
                payload["items"] = [asdict(row) for row in items]
                return updated
            raise KeyError(f"Unknown approval: {approval_id}")

        _, result = mutate_json_file(
            self.queue_file,
            default={"items": []},
            mutator=update_item,
        )
        self._items = self._load()
        return result

    def remove(self, approval_id: str) -> bool:
        def remove_item(payload: dict) -> bool:
            rows = list(payload.get("items", []))
            payload["items"] = [row for row in rows if str(row.get("approval_id")) != approval_id]
            return len(payload["items"]) != len(rows)

        _, changed = mutate_json_file(
            self.queue_file,
            default={"items": []},
            mutator=remove_item,
        )
        self._items = self._load()
        return changed

    def clear(self) -> int:
        def clear_items(payload: dict) -> int:
            count = len(payload.get("items", []))
            payload["items"] = []
            return count

        _, count = mutate_json_file(
            self.queue_file,
            default={"items": []},
            mutator=clear_items,
        )
        self._items = []
        return count

    def _load(self) -> list[ApprovalItem]:
        payload = read_json_file(self.queue_file, default={"items": []})
        return _items_from_payload(payload)

    def _save(self) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [asdict(item) for item in self._items]}
        write_json_file(self.queue_file, payload)

    def _reload(self) -> None:
        previous = {item.approval_id: item for item in self._items}
        loaded = self._load()
        self._items = [
            previous[item.approval_id]
            if previous.get(item.approval_id) == item
            else item
            for item in loaded
        ]
        if self._prune_oldest():
            self._save()

    def _prune_oldest(self) -> bool:
        if self.max_items <= 0 or len(self._items) <= self.max_items:
            return False
        self._items = self._items[-self.max_items :]
        return True


def _approval_id(*, channel_id: str, draft: str, source_ids: tuple[str, ...]) -> str:
    raw = "\n".join((channel_id, draft, *source_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _items_from_payload(payload: dict) -> list[ApprovalItem]:
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
