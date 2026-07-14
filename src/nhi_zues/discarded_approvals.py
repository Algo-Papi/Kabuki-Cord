from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .discord_text import sanitize_outgoing_draft
from .state_io import mutate_json_file, read_json_file, write_json_file


@dataclass(frozen=True)
class DiscardedApproval:
    discard_id: str
    created_at: str
    server_id: str
    channel_id: str
    source_message_ids: tuple[str, ...]
    reason: str
    draft_hash: str = ""


class DiscardedApprovalStore:
    def __init__(self, store_file: Path, *, limit: int = 2000) -> None:
        self.store_file = store_file
        self.limit = limit
        self._items = self._load()

    def record(
        self,
        *,
        server_id: str,
        channel_id: str,
        source_message_ids: tuple[str, ...] | list[str],
        draft: str = "",
        reason: str = "discarded approval",
    ) -> DiscardedApproval | None:
        source_ids = _clean_source_ids(source_message_ids)
        if not source_ids:
            return None
        discard_id = _discard_id(channel_id=channel_id, source_ids=source_ids)
        item = DiscardedApproval(
            discard_id=discard_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=str(server_id or ""),
            channel_id=str(channel_id or ""),
            source_message_ids=source_ids,
            reason=str(reason or "discarded approval"),
            draft_hash=_draft_hash(draft),
        )

        def add_item(payload: dict) -> DiscardedApproval:
            items = _items_from_payload(payload)
            existing = next((row for row in items if row.discard_id == discard_id), None)
            if existing:
                return existing
            items.append(item)
            payload["items"] = [asdict(row) for row in items[-self.limit :]]
            return item

        _, result = mutate_json_file(
            self.store_file,
            default={"items": []},
            mutator=add_item,
        )
        self._items = self._load()
        return result

    def find_overlap(
        self,
        *,
        channel_id: str,
        source_message_ids: tuple[str, ...] | list[str],
    ) -> list[DiscardedApproval]:
        self._items = self._load()
        source_ids = set(_clean_source_ids(source_message_ids))
        if not source_ids:
            return []
        return [
            item
            for item in self._items
            if item.channel_id == channel_id and source_ids.intersection(item.source_message_ids)
        ]

    def list(self) -> list[DiscardedApproval]:
        return list(self._items)

    def _load(self) -> list[DiscardedApproval]:
        payload = read_json_file(self.store_file, default={"items": []})
        return _items_from_payload(payload)

    def _save(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(self.store_file, {"items": [asdict(item) for item in self._items]})


def discarded_approval_message(overlaps: list[DiscardedApproval]) -> str:
    if not overlaps:
        return ""
    latest = overlaps[-1]
    return (
        "Discarded approval suppressed: this source message was already discarded "
        f"on {latest.created_at}. Use a newer message or clear local discard state "
        "only if you intentionally want to revisit it."
    )


def _clean_source_ids(source_message_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in source_message_ids:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return tuple(cleaned)


def _draft_hash(draft: str) -> str:
    text = sanitize_outgoing_draft(str(draft or ""))
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


def _discard_id(*, channel_id: str, source_ids: tuple[str, ...]) -> str:
    raw = "\n".join((str(channel_id or ""), *source_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _items_from_payload(payload: dict) -> list[DiscardedApproval]:
    return [
        DiscardedApproval(
            discard_id=str(row["discard_id"]),
            created_at=str(row["created_at"]),
            server_id=str(row.get("server_id") or ""),
            channel_id=str(row["channel_id"]),
            source_message_ids=tuple(str(value) for value in row.get("source_message_ids", [])),
            reason=str(row.get("reason") or "discarded approval"),
            draft_hash=str(row.get("draft_hash") or ""),
        )
        for row in payload.get("items", [])
    ]
