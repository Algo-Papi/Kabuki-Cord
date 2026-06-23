from __future__ import annotations

import re

LAUGH_EMOJI = "😂"


def suggest_emoji_reaction(text: str) -> tuple[str, str]:
    lowered = f" {str(text or '').lower()} "
    joke_markers = (
        " lol ",
        " lmao ",
        " haha",
        " 😂",
        " 🤣",
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
        return "👍", "message reads like a clear agreement or solid point"

    appreciation_markers = (" thanks", " thank you", " appreciate", " helpful", " good info")
    if any(marker in lowered for marker in appreciation_markers):
        return "🙏", "message reads as helpful or appreciative"

    surprise_markers = (" wild", " crazy", " insane", " wtf", " weird", " bizarre", " unreal")
    if any(marker in lowered for marker in surprise_markers):
        return "👀", "message has a surprising or unusually weird claim"

    return "👍", "safe light acknowledgement; no strong joke or surprise cue found"


def should_auto_laugh_react(text: str) -> tuple[bool, str]:
    emoji, reason = suggest_emoji_reaction(text)
    if emoji != LAUGH_EMOJI:
        return False, reason

    lowered = f" {str(text or '').lower()} "
    strong_markers = (" lmao", " lol", " haha", " 😂", " 🤣", " shitpost", " meme", " /s ")
    if any(marker in lowered for marker in strong_markers) or re.search(r"\b(lol+|lmao+|haha+)\b", lowered):
        return True, reason
    return False, "joke-like, but not strong enough for automatic reaction"
