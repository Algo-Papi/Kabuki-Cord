from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


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
        if not path.exists():
            return CharacterMemory(card_id=card_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CharacterMemory(
            card_id=card_id,
            story_claims=tuple(payload.get("story_claims", [])),
            behavior_notes=tuple(payload.get("behavior_notes", [])),
            updated_at=payload.get("updated_at", ""),
        )

    def add_story_claim(self, card_id: str, claim: str) -> CharacterMemory:
        memory = self.load(card_id)
        cleaned = _clean_note(claim)
        if not cleaned:
            return memory
        claims = _append_unique(memory.story_claims, cleaned, limit=80)
        updated = CharacterMemory(
            card_id=card_id,
            story_claims=claims,
            behavior_notes=memory.behavior_notes,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save(updated)
        return updated

    def add_behavior_note(self, card_id: str, note: str) -> CharacterMemory:
        memory = self.load(card_id)
        cleaned = _clean_note(note)
        if not cleaned:
            return memory
        notes = _append_unique(memory.behavior_notes, cleaned, limit=80)
        updated = CharacterMemory(
            card_id=card_id,
            story_claims=memory.story_claims,
            behavior_notes=notes,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save(updated)
        return updated

    def _save(self, memory: CharacterMemory) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._path(memory.card_id).write_text(json.dumps(asdict(memory), indent=2), encoding="utf-8")

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
