from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SentReply:
    reply_id: str
    created_at: str
    server_id: str
    channel_id: str
    mode: str
    draft_hash: str
    source_message_ids: tuple[str, ...]


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
    ) -> SentReply:
        source_ids = _clean_source_ids(source_message_ids)
        draft_hash = _draft_hash(draft)
        reply_id = _reply_id(channel_id=channel_id, draft_hash=draft_hash, source_ids=source_ids)
        existing = next((item for item in self._items if item.reply_id == reply_id), None)
        if existing:
            return existing

        item = SentReply(
            reply_id=reply_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=server_id,
            channel_id=channel_id,
            mode=mode,
            draft_hash=draft_hash,
            source_message_ids=source_ids,
        )
        self._items.append(item)
        self._items = self._items[-self.limit :]
        self._save()
        return item

    def find_overlap(
        self,
        *,
        channel_id: str,
        source_message_ids: tuple[str, ...] | list[str],
    ) -> list[SentReply]:
        source_ids = set(_clean_source_ids(source_message_ids))
        if not source_ids:
            return []
        return [
            item
            for item in self._items
            if item.channel_id == channel_id and source_ids.intersection(item.source_message_ids)
        ]

    def list(self) -> list[SentReply]:
        return list(self._items)

    def _load(self) -> list[SentReply]:
        if not self.ledger_file.exists():
            return []
        payload = json.loads(self.ledger_file.read_text(encoding="utf-8-sig"))
        return [
            SentReply(
                reply_id=str(row["reply_id"]),
                created_at=str(row["created_at"]),
                server_id=str(row["server_id"]),
                channel_id=str(row["channel_id"]),
                mode=str(row.get("mode") or "unknown"),
                draft_hash=str(row["draft_hash"]),
                source_message_ids=tuple(str(value) for value in row.get("source_message_ids", [])),
            )
            for row in payload.get("items", [])
        ]

    def _save(self) -> None:
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_file.write_text(
            json.dumps({"items": [asdict(item) for item in self._items]}, indent=2),
            encoding="utf-8",
        )


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
