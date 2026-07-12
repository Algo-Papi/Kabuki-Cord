from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .state_io import mutate_json_file, read_json_file, write_json_file


@dataclass(frozen=True)
class CharacterMemory:
    card_id: str
    story_claims: tuple[str, ...] = field(default_factory=tuple)
    behavior_notes: tuple[str, ...] = field(default_factory=tuple)
    updated_at: str = ""

    def prompt_text(self) -> str:
        sections: list[str] = []
        if self.story_claims:
            sections.append("Continuity claims:\n" + "\n".join(f"- {claim}" for claim in self.story_claims[-20:]))
        if self.behavior_notes:
            sections.append("Behavior adjustments:\n" + "\n".join(f"- {note}" for note in self.behavior_notes[-20:]))
        return "\n\n".join(sections)


class CharacterMemoryStore:
    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = memory_dir

    def load(self, card_id: str) -> CharacterMemory:
        path = self._path(card_id)
        payload = read_json_file(
            path,
            default={"story_claims": [], "behavior_notes": [], "updated_at": ""},
        )
        return CharacterMemory(
            card_id=card_id,
            story_claims=tuple(payload.get("story_claims", [])),
            behavior_notes=tuple(payload.get("behavior_notes", [])),
            updated_at=payload.get("updated_at", ""),
        )

    def add_story_claim(self, card_id: str, claim: str) -> CharacterMemory:
        cleaned = _clean_note(claim)
        if not cleaned:
            return self.load(card_id)

        def add_claim(payload: dict) -> CharacterMemory:
            updated = CharacterMemory(
                card_id=card_id,
                story_claims=_append_unique(tuple(payload.get("story_claims", [])), cleaned, limit=80),
                behavior_notes=tuple(payload.get("behavior_notes", [])),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            payload.update(asdict(updated))
            return updated

        _, updated = mutate_json_file(
            self._path(card_id),
            default={"story_claims": [], "behavior_notes": [], "updated_at": ""},
            mutator=add_claim,
        )
        return updated

    def add_behavior_note(self, card_id: str, note: str) -> CharacterMemory:
        cleaned = _clean_note(note)
        if not cleaned:
            return self.load(card_id)

        def add_note(payload: dict) -> CharacterMemory:
            updated = CharacterMemory(
                card_id=card_id,
                story_claims=tuple(payload.get("story_claims", [])),
                behavior_notes=_append_unique(tuple(payload.get("behavior_notes", [])), cleaned, limit=80),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            payload.update(asdict(updated))
            return updated

        _, updated = mutate_json_file(
            self._path(card_id),
            default={"story_claims": [], "behavior_notes": [], "updated_at": ""},
            mutator=add_note,
        )
        return updated

    def _save(self, memory: CharacterMemory) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        write_json_file(self._path(memory.card_id), asdict(memory))

    def _path(self, card_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", card_id).strip("_") or "default"
        return self.memory_dir / f"{safe}.json"


def _append_unique(existing: tuple[str, ...], note: str, *, limit: int) -> tuple[str, ...]:
    lowered = {item.lower() for item in existing}
    items = list(existing)
    if note.lower() not in lowered:
        items.append(note)
    return tuple(items[-limit:])


def _clean_note(note: str) -> str:
    return " ".join(note.strip().split())
