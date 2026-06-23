from __future__ import annotations

import hashlib
import random
import re


STOCK_PHRASES = (
    "vibe",
    "vibes",
    "energy",
    "so real",
    "lol",
    "lmao",
    "ngl",
    "i need to know",
    "yeah i get you",
    "i get what you mean",
    "yeah exactly",
    "ok but",
    "lowkey",
    "not gonna lie",
    "hits different",
    "insanely specific",
    "what kind of",
    "if this is where",
    "the whole point",
)

ABSTRACT_TELLS = (
    "consciousness",
    "energy",
    "framing",
    "pattern",
    "reality",
    "mechanics",
    "the whole point",
    "turns into",
    "where it stops",
    "feels like",
    "interesting",
)


DEFAULT_RESPONSE_MOVES = (
    "plain pushback: challenge one word or assumption directly, then stop. No question.",
    "grounded aside: connect the topic to one ordinary detail from work, music, home, or town life. No big theory.",
    "half-remembered claim: mention something you heard/read imperfectly, with uncertainty instead of confidence.",
    "dry reaction: one blunt passing comment, casual and short. No metaphor stack.",
    "specific evidence ask: ask one concrete source/detail question. No broad what-do-you-think closer.",
    "messy comparison: compare the claim to one concrete thing, but keep it rough and brief.",
    "skeptic nudge: disagree with the clean debunk version without sounding like a lecturer.",
)


def select_response_move(
    *,
    seed: str,
    avoid_question: bool,
    card_moves: tuple[str, ...] = (),
) -> str:
    moves = tuple(move.strip() for move in (card_moves or DEFAULT_RESPONSE_MOVES) if move.strip())
    if avoid_question:
        non_question_moves = tuple(
            move for move in moves if "question" not in move.lower() and "ask" not in move.lower()
        )
        if non_question_moves:
            moves = non_question_moves
    if not moves:
        moves = DEFAULT_RESPONSE_MOVES
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return moves[int(digest[:16], 16) % len(moves)]


def voice_guard_prompt(
    *,
    avoid_question: bool,
    recent_character_lines: list[str],
    response_move: str = "",
) -> str:
    lines = [
        "Voice repetition guard:",
        "- Do not use stock Discord filler: vibe, vibes, energy, so real, lol, lmao, ngl, lowkey, i need to know, yeah i get you, i get what you mean, yeah exactly.",
        "- Do not start with a soft agreement unless the user's exact message needs it. Skip the throat clearing.",
        "- Prefer concrete nouns and details over abstract filler like consciousness, reality, energy, framing, or pattern unless the other person already used that frame.",
        "- Keep the reply uneven and local. A normal passing comment is better than a polished theory.",
    ]
    if response_move:
        lines.append(f"- Required move for this draft: {response_move}")
    if avoid_question:
        lines.append("- Do not end this reply with a question; make a statement, aside, or imperfect claim instead.")
    else:
        lines.append("- A question is allowed, but only if it asks for one specific detail or source.")
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
    cleaned = _trim_stock_openers(cleaned)
    cleaned = _replace_stock_phrases(cleaned, seed=seed)
    cleaned = _clean_repeated_personal_filler(cleaned)
    if avoid_question and cleaned.rstrip().endswith("?"):
        cleaned = _soften_final_question(cleaned)
    return " ".join(cleaned.split())


def draft_quality_issues(text: str) -> list[str]:
    lowered = text.lower().strip()
    words = re.findall(r"\b[\w']+\b", lowered)
    issues: list[str] = []
    if len(words) > 45:
        issues.append("too long; keep it under 45 words unless explicitly asked")
    if lowered.startswith(("ok ", "okay ", "yeah ", "yep ", "lol ", "lmao ", "i mean ")):
        issues.append("starts with stock filler")
    stock_hits = [phrase for phrase in STOCK_PHRASES if phrase in lowered]
    if stock_hits:
        issues.append("uses stock phrase(s): " + ", ".join(stock_hits[:4]))
    abstract_hits = [term for term in ABSTRACT_TELLS if term in lowered]
    if len(abstract_hits) >= 2:
        issues.append("too abstract: " + ", ".join(abstract_hits[:4]))
    if lowered.count(" like ") > 1:
        issues.append("too many like-comparisons")
    if "?" in lowered and len(words) > 32:
        issues.append("question is too long; ask one concrete thing or make a statement")
    return issues


def _trim_stock_openers(text: str) -> str:
    result = text.strip()
    result = re.sub(
        r"^(?:ok but|okay but|yeah exactly|yeah|yep|lol|lmao|ngl|honestly|i mean|i get what you mean)[, ]+",
        "",
        result,
        flags=re.IGNORECASE,
    )
    return result[:1].lower() + result[1:] if result else result


def _clean_repeated_personal_filler(text: str) -> str:
    result = re.sub(
        r"\b(bothers|bugs|annoys|gets to) me for me\b",
        r"\1 me",
        text,
        flags=re.IGNORECASE,
    )
    result = re.sub(r"\bfor me[, ]+for me\b", "for me", result, flags=re.IGNORECASE)
    return result


def _replace_stock_phrases(text: str, *, seed: str) -> str:
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    replacements = {
        r"\blmao\b[, ]*": ("", "that is ugly, ", "gross, "),
        r"\blol\b[, ]*": ("", "", "that is ugly, "),
        r"\bngl\b[, ]*": ("", "honestly ", ""),
        r"\blowkey\b\s*": ("", "kinda "),
        r"\bnot gonna lie\b[, ]*": ("", "honestly "),
        r"\bhits different\b": ("gets under my skin", "sticks in my head", "bothers me"),
        r"\binsanely specific\b": ("too specific", "oddly specific", "grossly specific"),
        r"\bso real\b": ("familiar", "rough", "ugly"),
        r"\bi need to know\b": ("i keep wondering", "i can't tell", "the weird part is"),
        r"\bi get what you mean\b": ("i'm with part of that", "part of that checks out"),
        r"\byeah i get you\b": ("i'm with part of that", "part of that checks out"),
        r"\byeah exactly\b": ("right", "that part makes sense"),
        r"\bok but\b": ("", "still, "),
        r"\bthe whole point\b": ("the part that matters", "the part people skip"),
        r"\bframing\b": ("idea", "claim", "angle"),
        r"\bfeels like\b": ("sounds like", "reads like", "seems like"),
        r"\bwhat kind of\b": ("which", "what"),
        r"\bif this is where\b": ("if that's where", "when"),
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
