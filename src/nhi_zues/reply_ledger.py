from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .discord_text import sanitize_outgoing_draft
from .own_identity import normalize_message_text
from .state_io import mutate_json_file, read_json_file, write_json_file


@dataclass(frozen=True)
class SentReply:
    reply_id: str
    created_at: str
    server_id: str
    channel_id: str
    mode: str
    draft_hash: str
    source_message_ids: tuple[str, ...]
    message_id: str = ""
    draft_text: str = ""


class ReplyLedger:
    def __init__(self, ledger_file: Path, *, limit: int = 1000) -> None:
        self.ledger_file = ledger_file
        self.limit = limit
        self._items = self._load()

    def record(
        self,
        *,
        server_id: str,
        channel_id: str,
        mode: str,
        draft: str,
        source_message_ids: tuple[str, ...] | list[str],
        message_id: str = "",
    ) -> SentReply:
        source_ids = _clean_source_ids(source_message_ids)
        draft_hash = _draft_hash(draft)
        reply_id = _reply_id(channel_id=channel_id, draft_hash=draft_hash, source_ids=source_ids)
        item = SentReply(
            reply_id=reply_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=server_id,
            channel_id=channel_id,
            mode=mode,
            draft_hash=draft_hash,
            source_message_ids=source_ids,
            message_id=str(message_id or "").strip(),
            draft_text=sanitize_outgoing_draft(draft),
        )

        def add_item(payload: dict) -> SentReply:
            items = _items_from_payload(payload)
            existing = next((row for row in items if row.reply_id == reply_id), None)
            if existing:
                return existing
            items.append(item)
            payload["items"] = [asdict(row) for row in items[-self.limit :]]
            return item

        _, result = mutate_json_file(
            self.ledger_file,
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
    ) -> list[SentReply]:
        self._items = self._load()
        source_ids = set(_clean_source_ids(source_message_ids))
        if not source_ids:
            return []
        return [
            item
            for item in self._items
            if item.channel_id == channel_id and source_ids.intersection(item.source_message_ids)
        ]

    def latest_for_channel(self, *, channel_id: str) -> SentReply | None:
        for item in reversed(self._items):
            if item.channel_id == channel_id:
                return item
        return None

    def recent_for_channel(
        self,
        *,
        channel_id: str,
        window_seconds: float,
        now: datetime | None = None,
    ) -> list[SentReply]:
        if window_seconds <= 0:
            return []
        now = now or datetime.now(timezone.utc)
        recent: list[SentReply] = []
        for item in self._items:
            if item.channel_id != channel_id:
                continue
            created_at = _parse_created_at(item.created_at)
            if created_at is None:
                continue
            if (now - created_at).total_seconds() <= window_seconds:
                recent.append(item)
        return recent

    def list(self) -> list[SentReply]:
        return list(self._items)

    def own_message_ids_for_channel(self, *, channel_id: str, limit: int = 100) -> set[str]:
        return {
            item.message_id
            for item in self._items[-limit:]
            if item.channel_id == channel_id and item.message_id
        }

    def own_texts_for_channel(self, *, channel_id: str, limit: int = 100) -> set[str]:
        return {
            normalize_message_text(item.draft_text)
            for item in self._items[-limit:]
            if item.channel_id == channel_id and normalize_message_text(item.draft_text)
        }

    def _load(self) -> list[SentReply]:
        payload = read_json_file(self.ledger_file, default={"items": []})
        return _items_from_payload(payload)

    def _save(self) -> None:
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(self.ledger_file, {"items": [asdict(item) for item in self._items]})


def duplicate_reply_message(overlaps: list[SentReply]) -> str:
    if not overlaps:
        return ""
    latest = overlaps[-1]
    return (
        "Duplicate reply blocked: this approval overlaps source message(s) already replied to "
        f"on {latest.created_at}. Use Regenerate on the existing thread or discard the stale draft."
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
    return hashlib.sha256(" ".join(draft.split()).encode("utf-8")).hexdigest()[:16]


def _reply_id(*, channel_id: str, draft_hash: str, source_ids: tuple[str, ...]) -> str:
    raw = "\n".join((channel_id, draft_hash, *source_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _parse_created_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _items_from_payload(payload: dict) -> list[SentReply]:
    return [
        SentReply(
            reply_id=str(row["reply_id"]),
            created_at=str(row["created_at"]),
            server_id=str(row["server_id"]),
            channel_id=str(row["channel_id"]),
            mode=str(row.get("mode") or "unknown"),
            draft_hash=str(row["draft_hash"]),
            source_message_ids=tuple(str(value) for value in row.get("source_message_ids", [])),
            message_id=str(row.get("message_id") or ""),
            draft_text=str(row.get("draft_text") or ""),
        )
        for row in payload.get("items", [])
    ]
