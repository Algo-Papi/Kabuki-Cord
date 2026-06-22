from __future__ import annotations

import hashlib
import random
import re


WORD_RE = re.compile(r"(\b[\w']{4,}\b)")


def apply_human_writing_noise(
    text: str,
    *,
    mistake_rate: float,
    quirk: str,
    misspellings: str,
    seed: str = "",
) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return cleaned

    cleaned = _apply_consistent_misspellings(cleaned, _parse_misspellings(misspellings))
    cleaned = _apply_quirk(cleaned, quirk)
    cleaned = _reduce_dash_punctuation(cleaned)

    rate = max(0.0, min(float(mistake_rate or 0), 0.35))
    if rate <= 0:
        return cleaned

    digest = hashlib.sha256(f"{seed}\n{cleaned}".encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        if not _can_mistype(word) or rng.random() >= rate:
            return word
        return _mistype_word(word, rng)

    return WORD_RE.sub(replace, cleaned)


def writing_style_prompt(*, mistake_rate: float, quirk: str, misspellings: str) -> str:
    percent = round(max(0.0, min(float(mistake_rate or 0), 0.35)) * 100)
    quirk_text = {
        "none": "no consistent punctuation or casing quirk",
        "lowercase": "never capitalize normal prose",
        "no_commas": "avoid commas even where they would normally fit",
        "lowercase_no_commas": "never capitalize normal prose and avoid commas",
        "loose_punctuation": "use loose punctuation and occasional run-on phrasing",
    }.get(quirk, quirk or "none")
    typo_pairs = _parse_misspellings(misspellings)
    typo_text = ", ".join(f"{key}->{value}" for key, value in typo_pairs.items()) or "none"
    return (
        "Human writing imperfections:\n"
        f"- Add small typos or missing punctuation at roughly {percent}% intensity.\n"
        f"- Consistent quirk: {quirk_text}.\n"
        f"- Consistent misspellings: {typo_text}.\n"
        "- Avoid em dashes and frequent hyphen constructions; use plain sentence breaks instead.\n"
        "- Keep mistakes subtle; do not make the reply unreadable."
    )


def _parse_misspellings(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for item in re.split(r"[\n,]+", raw or ""):
        item = item.strip()
        if not item:
            continue
        if "=>" in item:
            left, right = item.split("=>", 1)
        elif ":" in item:
            left, right = item.split(":", 1)
        else:
            continue
        left = left.strip().lower()
        right = right.strip()
        if left and right:
            pairs[left] = right
    return pairs


def _apply_consistent_misspellings(text: str, pairs: dict[str, str]) -> str:
    if not pairs:
        return text

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        replacement = pairs.get(word.lower())
        return replacement if replacement else word

    return re.sub(r"\b[\w']+\b", replace, text)


def _apply_quirk(text: str, quirk: str) -> str:
    if quirk in {"lowercase", "lowercase_no_commas"}:
        text = text.lower()
    if quirk in {"no_commas", "lowercase_no_commas"}:
        text = text.replace(",", "")
    if quirk == "loose_punctuation":
        text = text.replace(";", " and").replace(" - ", " ")
        if text.endswith("."):
            text = text[:-1]
    return text


def _reduce_dash_punctuation(text: str) -> str:
    text = text.replace("—", " ").replace("–", " ")
    text = re.sub(r"\s+-\s+", " ", text)
    return " ".join(text.split())


def _can_mistype(word: str) -> bool:
    lower = word.lower()
    return not (
        lower.startswith(("http", "www"))
        or word.startswith(("@", "#"))
        or any(char.isdigit() for char in word)
        or "_" in word
    )


def _mistype_word(word: str, rng: random.Random) -> str:
    if len(word) < 5:
        return word
    chars = list(word)
    action = rng.choice(("swap", "drop", "double"))
    if action == "swap" and len(chars) > 5:
        index = rng.randrange(1, len(chars) - 2)
        chars[index], chars[index + 1] = chars[index + 1], chars[index]
    elif action == "drop":
        index = rng.randrange(1, len(chars) - 1)
        chars.pop(index)
    else:
        index = rng.randrange(1, len(chars) - 1)
        chars.insert(index, chars[index])
    return "".join(chars)
