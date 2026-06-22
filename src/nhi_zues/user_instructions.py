from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class UserInstruction:
    user_key: str
    note: str
    created_at: str


class UserInstructionStore:
    def __init__(self, instruction_file: Path) -> None:
        self.instruction_file = instruction_file
        self._items = self._load()

    def add(self, user_key: str, note: str) -> UserInstruction:
        item = UserInstruction(
            user_key=user_key,
            note=" ".join(note.strip().split()),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._items.append(item)
        self._save()
        return item

    def for_users(self, user_keys: list[str]) -> dict[str, list[UserInstruction]]:
        wanted = set(user_keys)
        results: dict[str, list[UserInstruction]] = {key: [] for key in user_keys}
        for item in self._items:
            if item.user_key in wanted:
                results.setdefault(item.user_key, []).append(item)
        return results

    def _load(self) -> list[UserInstruction]:
        if not self.instruction_file.exists():
            return []
        payload = json.loads(self.instruction_file.read_text(encoding="utf-8"))
        return [UserInstruction(**row) for row in payload.get("items", [])]

    def _save(self) -> None:
        self.instruction_file.parent.mkdir(parents=True, exist_ok=True)
        self.instruction_file.write_text(
            json.dumps({"items": [item.__dict__ for item in self._items]}, indent=2),
            encoding="utf-8",
        )
