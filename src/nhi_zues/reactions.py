from __future__ import annotations

import re

LAUGH_EMOJI = "\U0001f602"
THUMBS_UP_EMOJI = "\U0001f44d"
APPRECIATION_EMOJI = "\U0001f64f"
EYES_EMOJI = "\U0001f440"


def suggest_emoji_reaction(text: str) -> tuple[str, str]:
    lowered = f" {str(text or '').lower()} "
    joke_markers = (
        " lol ",
        " lmao ",
        " haha",
        f" {LAUGH_EMOJI}",
        " \U0001f923",
        " joke",
        " kidding",
        " satire",
        " parody",
        " meme",
        " shitpost",
        " bit ",
        " /s ",
    )
    if any(marker in lowered for marker in joke_markers) or re.search(r"\b(lol+|lmao+|haha+)\b", lowered):
        return LAUGH_EMOJI, "message reads as a joke, bit, meme, or satire"

    agreement_markers = (
        " exactly",
        " agreed",
        " agree ",
        " true ",
        " facts",
        " good point",
        " makes sense",
        " fair point",
        " correct",
        " this is it",
    )
    if any(marker in lowered for marker in agreement_markers):
        return THUMBS_UP_EMOJI, "message reads like a clear agreement or solid point"

    appreciation_markers = (" thanks", " thank you", " appreciate", " helpful", " good info")
    if any(marker in lowered for marker in appreciation_markers):
        return APPRECIATION_EMOJI, "message reads as helpful or appreciative"

    surprise_markers = (" wild", " crazy", " insane", " wtf", " weird", " bizarre", " unreal")
    if any(marker in lowered for marker in surprise_markers):
        return EYES_EMOJI, "message has a surprising or unusually weird claim"

    return THUMBS_UP_EMOJI, "safe light acknowledgement; no strong joke or surprise cue found"


def should_auto_laugh_react(text: str) -> tuple[bool, str]:
    emoji, reason = suggest_emoji_reaction(text)
    if emoji != LAUGH_EMOJI:
        return False, reason

    lowered = f" {str(text or '').lower()} "
    strong_markers = (" lmao", " lol", " haha", f" {LAUGH_EMOJI}", " \U0001f923", " shitpost", " meme", " /s ")
    if any(marker in lowered for marker in strong_markers) or re.search(r"\b(lol+|lmao+|haha+)\b", lowered):
        return True, reason
    return False, "joke-like, but not strong enough for automatic reaction"


def should_auto_react(text: str) -> tuple[bool, str, str]:
    cleaned = " ".join(str(text or "").split())
    if not _has_enough_reaction_signal(cleaned):
        return False, "", "message is too short or low-signal for an automatic reaction"

    emoji, reason = suggest_emoji_reaction(cleaned)
    lowered = f" {cleaned.lower()} "
    if emoji == LAUGH_EMOJI:
        strong_markers = (" lmao", " lol", " haha", f" {LAUGH_EMOJI}", " \U0001f923", " shitpost", " meme", " /s ")
        if any(marker in lowered for marker in strong_markers) or re.search(r"\b(lol+|lmao+|haha+)\b", lowered):
            return True, emoji, reason
        return False, "", "joke-like, but not strong enough for automatic reaction"
    if emoji in {THUMBS_UP_EMOJI, APPRECIATION_EMOJI, EYES_EMOJI}:
        return True, emoji, reason
    return False, "", "no configured automatic reaction cue found"


def _has_enough_reaction_signal(text: str) -> bool:
    if len(text) < 8:
        return False
    words = re.findall(r"[a-zA-Z0-9']+", text)
    if len(words) < 2 and not any(item in text for item in (LAUGH_EMOJI, "\U0001f923")):
        return False
    lowered = text.lower().strip()
    if lowered.startswith(("http://", "https://", "www.")):
        return False
    return True
