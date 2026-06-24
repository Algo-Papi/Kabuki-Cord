from __future__ import annotations

import re
import random

LAUGH_EMOJI = "\U0001f602"
THUMBS_UP_EMOJI = "\U0001f44d"
APPRECIATION_EMOJI = "\U0001f64f"
EYES_EMOJI = "\U0001f440"
THINKING_EMOJI = "\U0001f914"
REACTION_THRESHOLDS = {"strict", "normal", "loose"}


def suggest_emoji_reaction(text: str) -> tuple[str, str]:
    cleaned = " ".join(str(text or "").split())
    lowered = f" {cleaned.lower()} "
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
    if _looks_like_joke(lowered, joke_markers):
        return LAUGH_EMOJI, "message reads as a joke, bit, meme, or satire"

    appreciation_markers = (
        " thanks",
        " thank you",
        " appreciate",
        " helpful",
        " good info",
        " pray for",
        " prayers",
    )
    if any(marker in lowered for marker in appreciation_markers):
        return APPRECIATION_EMOJI, "message reads as helpful, appreciative, or support-seeking"

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

    question_markers = (
        "?",
        " who ",
        " what ",
        " why ",
        " how ",
        " where ",
        " when ",
        " anyone ",
        " thoughts",
        " curious",
        " wonder",
    )
    if any(marker in lowered for marker in question_markers):
        return THINKING_EMOJI, "message asks a question or invites speculation"

    surprise_markers = (
        " wild",
        " crazy",
        " insane",
        " wtf",
        " weird",
        " bizarre",
        " unreal",
        " ufo",
        " alien",
        " nhi",
        " disclosure",
        " simulation",
        " consciousness",
        " scripture",
        " dna",
        " prophecy",
        " coverup",
        " propulsion",
        " electromagnetism",
    )
    if any(marker in lowered for marker in surprise_markers):
        return EYES_EMOJI, "message has a surprising or unusually weird claim"

    serious_markers = (
        " dead",
        " died",
        " death",
        " murder",
        " suicide",
        " cancer",
        " hospital",
        " banned",
        " abuse",
        " racist",
        " ai",
        " spam",
        " stop ",
        " cool it",
    )
    if any(marker in lowered for marker in serious_markers):
        return EYES_EMOJI, "message is serious or socially loaded, so a low-commitment reaction fits better"

    return THUMBS_UP_EMOJI, "safe light acknowledgement; no strong joke or surprise cue found"


def should_auto_laugh_react(text: str) -> tuple[bool, str]:
    emoji, reason = suggest_emoji_reaction(text)
    if emoji != LAUGH_EMOJI:
        return False, reason

    lowered = f" {str(text or '').lower()} "
    strong_markers = (
        " lmao",
        " lol",
        " haha",
        " hehe",
        f" {LAUGH_EMOJI}",
        " \U0001f923",
        " shitpost",
        " meme",
        " /s ",
    )
    if any(marker in lowered for marker in strong_markers) or re.search(r"\b(lol+|lmao+|haha+)\b", lowered):
        return True, reason
    return False, "joke-like, but not strong enough for automatic reaction"


def should_auto_react(
    text: str,
    *,
    threshold: str = "normal",
    sample_percent: float = 0.0,
    force_laugh_percent: float = 0.0,
    emoji_override: str = "",
    sample_roll: float | None = None,
    force_laugh_roll: float | None = None,
) -> tuple[bool, str, str]:
    cleaned = " ".join(str(text or "").split())
    force_laugh_percent = max(0.0, min(float(force_laugh_percent or 0.0), 100.0))
    if force_laugh_percent > 0 and _has_minimum_forced_reaction_signal(cleaned):
        roll = force_laugh_roll if force_laugh_roll is not None else random.random()
        if roll <= force_laugh_percent / 100.0:
            if not _has_enough_reaction_signal(cleaned):
                return False, "", "message is too short or low-signal for an automatic reaction"
            emoji_override = _clean_emoji_override(emoji_override)
            emoji, reason = _forced_reaction_choice(cleaned)
            if emoji_override:
                return (
                    True,
                    emoji_override,
                    f"emoji override applied; force reaction sample accepted ({force_laugh_percent:g}%); {reason}",
                )
            return True, emoji, f"force reaction sample accepted ({force_laugh_percent:g}%); {reason}"

    if not _has_enough_reaction_signal(cleaned):
        return False, "", "message is too short or low-signal for an automatic reaction"

    threshold = _normalize_threshold(threshold)
    emoji_override = _clean_emoji_override(emoji_override)
    emoji, reason = suggest_emoji_reaction(cleaned)
    lowered = f" {cleaned.lower()} "

    should_react = False
    blocked_reason = "no configured automatic reaction cue found"
    if emoji == LAUGH_EMOJI:
        strong_markers = (
            " lmao",
            " lol",
            " haha",
            " hehe",
            f" {LAUGH_EMOJI}",
            " \U0001f923",
            " shitpost",
            " meme",
            " /s ",
        )
        if any(marker in lowered for marker in strong_markers) or re.search(r"\b(lol+|lmao+|haha+)\b", lowered):
            should_react = True
        elif threshold == "loose":
            should_react = True
        else:
            blocked_reason = "joke-like, but not strong enough for automatic reaction"
    elif emoji == EYES_EMOJI:
        should_react = threshold in {"normal", "loose"}
    elif emoji == THINKING_EMOJI:
        should_react = threshold in {"normal", "loose"}
    elif emoji in {THUMBS_UP_EMOJI, APPRECIATION_EMOJI} and "safe light acknowledgement" not in reason:
        should_react = True
    elif threshold == "loose":
        should_react = True
        emoji = _light_acknowledgement_emoji(cleaned)
        reason = "loose threshold accepted a low-commitment acknowledgement"

    if should_react:
        if emoji_override:
            return True, emoji_override, f"emoji override applied; {reason}"
        return True, emoji, reason

    sample_percent = max(0.0, min(float(sample_percent or 0.0), 100.0))
    if sample_percent > 0:
        roll = sample_roll if sample_roll is not None else random.random()
        if roll <= sample_percent / 100.0:
            emoji = emoji_override or _forced_reaction_choice(cleaned)[0]
            return True, emoji, f"sampled by reaction percentage setting ({sample_percent:g}%)"

    return False, "", blocked_reason


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


def _has_minimum_forced_reaction_signal(text: str) -> bool:
    cleaned = str(text or "").strip()
    if len(cleaned) < 4:
        return False
    lowered = cleaned.lower()
    if lowered.startswith(("http://", "https://", "www.")):
        return False
    return bool(re.search(r"[a-zA-Z0-9]", cleaned))


def _forced_reaction_choice(text: str) -> tuple[str, str]:
    emoji, reason = suggest_emoji_reaction(text)
    if emoji == LAUGH_EMOJI and not should_auto_laugh_react(text)[0]:
        return EYES_EMOJI, "joke cue was weak; using eyes instead of laugh"
    if "safe light acknowledgement" in reason:
        return _light_acknowledgement_emoji(text), "forced recent reaction selected a neutral acknowledgement"
    return emoji, reason


def _light_acknowledgement_emoji(text: str) -> str:
    lowered = f" {str(text or '').lower()} "
    if any(item in lowered for item in ("?", " curious", " wonder", " anyone ", " who ", " what ", " why ", " how ")):
        return THINKING_EMOJI
    if any(item in lowered for item in (" weird", " wild", " crazy", " ai", " spam", " serious", " stop ", " cool it")):
        return EYES_EMOJI
    return THUMBS_UP_EMOJI


def _looks_like_joke(lowered: str, markers: tuple[str, ...]) -> bool:
    return any(marker in lowered for marker in markers) or bool(
        re.search(r"\b(lol+|lmao+|haha+|hehe+)\b", lowered)
    )


def _normalize_threshold(value: str) -> str:
    cleaned = str(value or "normal").strip().lower().replace("-", "_").replace(" ", "_")
    return cleaned if cleaned in REACTION_THRESHOLDS else "normal"


def _clean_emoji_override(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    return cleaned[:8]
