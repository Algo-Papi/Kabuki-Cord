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
    verified: bool = True


class ReactionLedger:
    def __init__(self, ledger_file: Path) -> None:
        self.ledger_file = ledger_file
        self._records = self._load()

    def has_reacted(self, *, channel_id: str, message_id: str, emoji: str) -> bool:
        return any(
            record.channel_id == channel_id
            and record.message_id == message_id
            and record.emoji == emoji
            and record.verified
            for record in self._records
        )

    def has_reacted_to_message(self, *, channel_id: str, message_id: str) -> bool:
        return any(
            record.channel_id == channel_id
            and record.message_id == message_id
            and record.verified
            for record in self._records
        )

    def has_attempted_to_message(self, *, channel_id: str, message_id: str) -> bool:
        return any(
            record.channel_id == channel_id
            and record.message_id == message_id
            for record in self._records
        )

    def last_reaction_at(self, *, channel_id: str) -> datetime | None:
        matches = [
            _parse_iso_datetime(record.created_at)
            for record in self._records
            if record.channel_id == channel_id and record.verified
        ]
        valid = [value for value in matches if value is not None]
        return max(valid) if valid else None

    def last_attempt_at(self, *, channel_id: str) -> datetime | None:
        matches = [
            _parse_iso_datetime(record.created_at)
            for record in self._records
            if record.channel_id == channel_id
        ]
        valid = [value for value in matches if value is not None]
        return max(valid) if valid else None

    def recent_unverified_count(
        self,
        *,
        channel_id: str,
        within_seconds: float,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now(timezone.utc)
        window = max(0.0, float(within_seconds or 0.0))
        count = 0
        for record in self._records:
            if record.channel_id != channel_id or record.verified:
                continue
            created = _parse_iso_datetime(record.created_at)
            if created is None:
                continue
            if (current - created.astimezone(timezone.utc)).total_seconds() <= window:
                count += 1
        return count

    def list(self) -> list[ReactionRecord]:
        return list(self._records)

    def record(
        self,
        *,
        server_id: str,
        message: MessageRecord,
        emoji: str,
        reason: str,
        verified: bool = True,
    ) -> ReactionRecord:
        existing_index = next(
            (
                index
                for index, record in enumerate(self._records)
                if record.channel_id == message.channel_id
                and record.message_id == message.message_id
                and record.emoji == emoji
            ),
            None,
        )
        if existing_index is not None:
            existing = self._records[existing_index]
            if verified and not existing.verified:
                updated = ReactionRecord(
                    created_at=existing.created_at,
                    server_id=server_id,
                    channel_id=existing.channel_id,
                    message_id=existing.message_id,
                    emoji=existing.emoji,
                    reason=reason,
                    author=message.author,
                    verified=True,
                )
                self._records[existing_index] = updated
                self._save()
                return updated
            return existing
        record = ReactionRecord(
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=server_id,
            channel_id=message.channel_id,
            message_id=message.message_id,
            emoji=emoji,
            reason=reason,
            author=message.author,
            verified=verified,
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
                verified=bool(row.get("verified", False)),
            )
            for row in payload.get("items", [])
        ]

    def _save(self) -> None:
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(self.ledger_file, {"items": [asdict(record) for record in self._records]})


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
