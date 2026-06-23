from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import MessageRecord
from .state_io import write_json_file


@dataclass(frozen=True)
class ReactionRecord:
    created_at: str
    server_id: str
    channel_id: str
    message_id: str
    emoji: str
    reason: str
    author: str


class ReactionLedger:
    def __init__(self, ledger_file: Path) -> None:
        self.ledger_file = ledger_file
        self._records = self._load()

    def has_reacted(self, *, channel_id: str, message_id: str, emoji: str) -> bool:
        return any(
            record.channel_id == channel_id
            and record.message_id == message_id
            and record.emoji == emoji
            for record in self._records
        )

    def record(self, *, server_id: str, message: MessageRecord, emoji: str, reason: str) -> ReactionRecord:
        existing = next(
            (
                record
                for record in self._records
                if record.channel_id == message.channel_id
                and record.message_id == message.message_id
                and record.emoji == emoji
            ),
            None,
        )
        if existing:
            return existing
        record = ReactionRecord(
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=server_id,
            channel_id=message.channel_id,
            message_id=message.message_id,
            emoji=emoji,
            reason=reason,
            author=message.author,
        )
        self._records.append(record)
        self._records = self._records[-1000:]
        self._save()
        return record

    def _load(self) -> list[ReactionRecord]:
        if not self.ledger_file.exists():
            return []
        payload = json.loads(self.ledger_file.read_text(encoding="utf-8-sig"))
        return [
            ReactionRecord(
                created_at=str(row["created_at"]),
                server_id=str(row["server_id"]),
                channel_id=str(row["channel_id"]),
                message_id=str(row["message_id"]),
                emoji=str(row["emoji"]),
                reason=str(row.get("reason") or ""),
                author=str(row.get("author") or ""),
            )
            for row in payload.get("items", [])
        ]

    def _save(self) -> None:
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(self.ledger_file, {"items": [asdict(record) for record in self._records]})
