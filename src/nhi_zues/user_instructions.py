from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .state_io import mutate_json_file, read_json_file, write_json_file


@dataclass(frozen=True)
class UserInstruction:
    user_key: str
    note: str
    created_at: str
    server_id: str | None = None
    channel_id: str | None = None


class UserInstructionStore:
    def __init__(self, instruction_file: Path) -> None:
        self.instruction_file = instruction_file
        self._items = self._load()

    def add(
        self,
        user_key: str,
        note: str,
        *,
        server_id: str | None = None,
        channel_id: str | None = None,
    ) -> UserInstruction:
        item = UserInstruction(
            user_key=user_key,
            note=" ".join(note.strip().split()),
            created_at=datetime.now(timezone.utc).isoformat(),
            server_id=server_id or None,
            channel_id=channel_id or None,
        )
        def append_item(payload: dict) -> None:
            rows = list(payload.get("items", []))
            rows.append(item.__dict__)
            payload["items"] = rows

        mutate_json_file(
            self.instruction_file,
            default={"items": []},
            mutator=append_item,
        )
        self._items = self._load()
        return item

    def for_users(
        self,
        user_keys: list[str],
        *,
        server_id: str | None = None,
        channel_id: str | None = None,
    ) -> dict[str, list[UserInstruction]]:
        self._items = self._load()
        wanted = set(user_keys)
        results: dict[str, list[UserInstruction]] = {key: [] for key in user_keys}
        for item in self._items:
            if item.user_key in wanted and _scope_applies(item, server_id=server_id, channel_id=channel_id):
                results.setdefault(item.user_key, []).append(item)
        return results

    def _load(self) -> list[UserInstruction]:
        payload = read_json_file(self.instruction_file, default={"items": []})
        return [UserInstruction(**row) for row in payload.get("items", [])]

    def _save(self) -> None:
        self.instruction_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(self.instruction_file, {"items": [item.__dict__ for item in self._items]})


def _scope_applies(item: UserInstruction, *, server_id: str | None, channel_id: str | None) -> bool:
    if item.server_id and item.server_id != server_id:
        return False
    if item.channel_id and item.channel_id != channel_id:
        return False
    return True
