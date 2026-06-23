from __future__ import annotations

import hashlib
import random
import re


STOCK_PHRASES = (
    "vibe",
    "vibes",
    "energy",
    "so real",
    "ngl",
    "i need to know",
    "yeah i get you",
    "yeah exactly",
    "lowkey",
    "not gonna lie",
)


def voice_guard_prompt(*, avoid_question: bool, recent_character_lines: list[str]) -> str:
    lines = [
        "Voice repetition guard:",
        "- Do not use stock Discord filler: vibe, vibes, energy, so real, ngl, lowkey, i need to know, yeah i get you, yeah exactly.",
        "- Vary the move. Choose one: dry aside, grounded personal tangent, half-remembered claim, mild disagreement, evidence question, flawed inference, or short factual pushback.",
        "- Prefer concrete nouns and details over abstract filler like consciousness/energy unless the other person already used that frame.",
    ]
    if avoid_question:
        lines.append("- Do not end this reply with a question; make a statement, aside, or imperfect claim instead.")
    else:
        lines.append("- A question is allowed, but only if it is specific and not the same broad what-do-you-think closer.")
    if recent_character_lines:
        lines.append("- Avoid sounding like these recent lines from the same character:")
        for line in recent_character_lines[-4:]:
            lines.append(f"  - {line[:220]}")
    return "\n".join(lines)


def should_avoid_question(*, recent_character_lines: list[str], seed: str) -> bool:
    if not recent_character_lines:
        return False
    window = recent_character_lines[-8:]
    question_count = sum("?" in line for line in window)
    if question_count / len(window) >= 0.35:
        return True
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16)).random() < 0.55


def apply_voice_guard(text: str, *, avoid_question: bool, seed: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return cleaned
    cleaned = _replace_stock_phrases(cleaned, seed=seed)
    if avoid_question and cleaned.rstrip().endswith("?"):
        cleaned = _soften_final_question(cleaned)
    return " ".join(cleaned.split())


def _replace_stock_phrases(text: str, *, seed: str) -> str:
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    replacements = {
        r"\bngl\b[, ]*": ("", "honestly ", ""),
        r"\blowkey\b\s*": ("", "kinda "),
        r"\bnot gonna lie\b[, ]*": ("", "honestly "),
        r"\bso real\b": ("familiar", "rough", "that tracks"),
        r"\bi need to know\b": ("i keep wondering", "the part i keep circling", "i can't tell"),
        r"\byeah i get you\b": ("i see what you mean", "i get the point", "i'm with part of that"),
        r"\byeah exactly\b": ("right", "that part makes sense", "that's the part"),
        r"\bvibes\b": ("read", "pattern", "thing"),
        r"\bvibe\b": ("read", "pattern", "thing", "texture"),
        r"\benergy\b": ("tone", "pressure", "read"),
    }
    result = text
    for pattern, choices in replacements.items():
        result = re.sub(pattern, lambda _match: rng.choice(choices), result, flags=re.IGNORECASE)
    return result


def _soften_final_question(text: str) -> str:
    stripped = text.rstrip()
    question_start = max(stripped.rfind("?"), stripped.rfind(". "), stripped.rfind("! "))
    if question_start <= 0 or stripped[question_start] != "?":
        return stripped.rstrip("?") + "."
    return stripped.rstrip("?") + "."
