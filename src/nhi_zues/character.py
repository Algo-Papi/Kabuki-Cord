from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CharacterCard:
    name: str
    system_prompt: str
    style_rules: tuple[str, ...]
    engagement_rules: tuple[str, ...]
    response_moves: tuple[str, ...]
    voice_examples: tuple[str, ...]
    avoid_examples: tuple[str, ...]
    aliases: tuple[str, ...]
    trigger_keywords: tuple[str, ...]

    def prompt_text(self) -> str:
        rules = "\n".join(f"- {rule}" for rule in self.style_rules)
        engagement = "\n".join(f"- {rule}" for rule in self.engagement_rules)
        sections = [
            self.system_prompt,
            f"Style rules:\n{rules}",
            f"Engagement rules:\n{engagement}",
        ]
        if self.response_moves:
            moves = "\n".join(f"- {move}" for move in self.response_moves)
            sections.append(f"Available response moves:\n{moves}")
        if self.voice_examples:
            examples = "\n".join(f"- {example}" for example in self.voice_examples)
            sections.append(f"Good voice examples:\n{examples}")
        if self.avoid_examples:
            examples = "\n".join(f"- {example}" for example in self.avoid_examples)
            sections.append(f"Bad voice examples to avoid:\n{examples}")
        return "\n\n".join(sections)


class CharacterCardStore:
    def __init__(self, card_dir: Path, active_card: str = "default.json") -> None:
        self.card_dir = card_dir
        self.default_card = self._load_card(card_dir / active_card)

    def for_server(self, server_id: str, character_card: str | None = None) -> CharacterCard:
        if character_card:
            return self._load_card(self.card_dir / character_card)

        override_path = self.card_dir / "servers" / f"{server_id}.json"
        if not override_path.exists():
            return self.default_card

        base = _card_to_dict(self.default_card)
        override = json.loads(override_path.read_text(encoding="utf-8"))
        base.update({key: value for key, value in override.items() if value is not None})
        return _card_from_dict(base)

    @staticmethod
    def _load_card(path: Path) -> CharacterCard:
        if not path.exists():
            raise FileNotFoundError(f"Missing character card: {path}")
        return _card_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _card_from_dict(payload: dict) -> CharacterCard:
    return CharacterCard(
        name=str(payload["name"]),
        system_prompt=str(payload["system_prompt"]),
        style_rules=tuple(str(rule) for rule in payload.get("style_rules", [])),
        engagement_rules=tuple(str(rule) for rule in payload.get("engagement_rules", [])),
        response_moves=tuple(str(move) for move in payload.get("response_moves", [])),
        voice_examples=tuple(str(example) for example in payload.get("voice_examples", [])),
        avoid_examples=tuple(str(example) for example in payload.get("avoid_examples", [])),
        aliases=tuple(str(alias).lower() for alias in payload.get("aliases", [])),
        trigger_keywords=tuple(str(word).lower() for word in payload.get("trigger_keywords", [])),
    )


def _card_to_dict(card: CharacterCard) -> dict:
    return {
        "name": card.name,
        "system_prompt": card.system_prompt,
        "style_rules": list(card.style_rules),
        "engagement_rules": list(card.engagement_rules),
        "response_moves": list(card.response_moves),
        "voice_examples": list(card.voice_examples),
        "avoid_examples": list(card.avoid_examples),
        "aliases": list(card.aliases),
        "trigger_keywords": list(card.trigger_keywords),
    }
