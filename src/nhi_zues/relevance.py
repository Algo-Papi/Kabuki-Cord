from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .character import CharacterCard
from .discord_text import clean_discord_display_name, sanitize_outgoing_draft
from .models import MessageRecord


AssessmentOutcome = Literal["reply", "defer", "skip"]
EngagementType = Literal["direct", "proactive", "conversation", "none"]


@dataclass(frozen=True)
class ConversationWindow:
    targets: tuple[MessageRecord, ...]
    support: tuple[MessageRecord, ...] = ()


@dataclass(frozen=True)
class TextSignals:
    concrete_question: bool = False
    compact_opinion: bool = False
    disagreement: bool = False
    reason_or_evidence: bool = False
    specific: bool = False
    unresolved_anaphora: bool = False


@dataclass(frozen=True)
class RelevanceAssessment:
    outcome: AssessmentOutcome
    engagement_type: EngagementType
    total_score: int
    relevance_score: int
    substance_score: int
    continuity_score: int
    reason_code: str
    reason: str
    signals: tuple[str, ...] = ()
    target_message_ids: tuple[str, ...] = ()
    support_message_ids: tuple[str, ...] = ()


_LOW_SIGNAL_PHRASES = {
    "can i though",
    "cute",
    "hello",
    "hey",
    "hi",
    "hm",
    "hmm",
    "how are u",
    "how are you",
    "how is life",
    "how's life",
    "hows it going",
    "hows life",
    "nah",
    "nope",
    "nothing much",
    "nthn much",
    "ok",
    "okay",
    "pretty much",
    "same",
    "sup",
    "thanks",
    "thats facts",
    "that's facts",
    "what about you",
    "wsg",
    "wyd",
    "yea",
    "yeah",
    "yep",
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "do",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "him",
    "his",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "just",
    "me",
    "my",
    "not",
    "of",
    "on",
    "or",
    "our",
    "she",
    "so",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "those",
    "to",
    "us",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "would",
    "you",
    "your",
}

_EVALUATIONS = (
    "absurd",
    "amazing",
    "annoying",
    "awful",
    "backwards",
    "bad",
    "better",
    "boring",
    "dumb",
    "fine",
    "funny",
    "good",
    "great",
    "interesting",
    "pointless",
    "ridiculous",
    "right",
    "smart",
    "terrible",
    "underrated",
    "useful",
    "weird",
    "wild",
    "worse",
    "worst",
    "wrong",
    "overrated",
)
_EVALUATION_PATTERN = "(?:" + "|".join(re.escape(term) for term in _EVALUATIONS) + ")"

_QUESTION_START = re.compile(r"^(?:why|how|what|which|who|where|when)\b")
_ANAPHORIC_START = re.compile(
    r"^(?:(?:but|though|instead|because)\b|(?:that|this|it|those|these|he|she|they)\s+"
    r"(?:is|isn't|isnt|was|wasn't|wasnt|are|aren't|arent|were|weren't|werent|"
    r"still|also|just|really|sounds?|looks?|feels?|seems?|does|doesn't|doesnt)\b)"
)
_STANCE_PATTERN = re.compile(
    r"\b(?:i|we)\s+(?:really\s+|honestly\s+)?"
    r"(?:think|believe|feel|prefer|hate|love|doubt|agree|disagree)\b"
)
_PREDICATE_OPINION_PATTERN = re.compile(
    rf"\b(?:is|are|was|were|be|being|seems?|looks?|sounds?|feels?)\b"
    rf"(?:\s+[a-z0-9']+){{0,3}}\s+{_EVALUATION_PATTERN}\b"
)
_COMPARATIVE_PATTERN = re.compile(
    r"\b(?:better|worse|more|less|fewer)\b(?:\s+\w+){0,3}\s+"
    r"(?:than|before|after|with|without)\b|"
    r"\b(?:need(?:ed|s)?|has|have|had|gets?|got)\s+(?:way\s+|too\s+)?"
    r"(?:more|less|fewer)\b"
)
_DISAGREEMENT_PATTERN = re.compile(
    r"\b(?:but|though|instead|wrong|backwards|never|can't|cant|isn't|isnt|"
    r"doesn't|doesnt|not|without)\b|\bnot\s+the\s+same\b|\bdoes\s+not\s+follow\b"
)
_REASON_PATTERN = re.compile(
    r"\b(?:because|according\s+to|apparently|reportedly|confirmed|evidence|source|"
    r"which\s+means|turns\s+out)\b|\b\d+(?:\.\d+)?%\b"
)


def assess_reply_candidate(
    *,
    new_messages: list[MessageRecord],
    context: list[MessageRecord],
    character: CharacterCard,
    conversation_reply_enabled: bool,
) -> RelevanceAssessment:
    windows = candidate_windows(
        new_messages=new_messages,
        context=context,
        character=character,
    )
    if not windows:
        return _assessment(
            outcome="skip",
            engagement_type="none",
            reason_code="no_candidate",
        )

    assessments = [
        score_window(
            window,
            character=character,
            conversation_reply_enabled=conversation_reply_enabled,
        )
        for window in windows
    ]
    outcome_rank = {"skip": 0, "defer": 1, "reply": 2}
    return max(
        enumerate(assessments),
        key=lambda item: (
            outcome_rank[item[1].outcome],
            item[1].total_score,
            item[0],
        ),
    )[1]


def candidate_windows(
    *,
    new_messages: list[MessageRecord],
    context: list[MessageRecord],
    character: CharacterCard,
) -> tuple[ConversationWindow, ...]:
    fresh = [message for message in new_messages if _has_text(message)]
    if not fresh:
        return ()

    groups: list[list[MessageRecord]] = []
    for message in fresh:
        author_key = _author_key(message)
        if groups and _author_key(groups[-1][-1]) == author_key:
            groups[-1].append(message)
        else:
            groups.append([message])

    context_index = {
        message.message_id: index
        for index, message in enumerate(context)
        if str(message.message_id or "")
    }
    windows: list[ConversationWindow] = []
    for group in groups:
        targets = tuple(group[-4:])
        first_index = context_index.get(targets[0].message_id)
        support: list[MessageRecord] = []
        if first_index is not None:
            preceding = [
                message
                for message in context[max(0, first_index - 2) : first_index]
                if _has_text(message) and not looks_like_app_feed(message)
            ]
            support = _relevant_support(preceding, targets)
        windows.append(ConversationWindow(targets=targets, support=tuple(support[-2:])))
    return tuple(windows)


def score_window(
    window: ConversationWindow,
    *,
    character: CharacterCard,
    conversation_reply_enabled: bool,
) -> RelevanceAssessment:
    target_ids = tuple(message.message_id for message in window.targets)
    support_ids = tuple(message.message_id for message in window.support)
    if all(_is_character_message(message, character) for message in window.targets):
        return _assessment(
            outcome="skip",
            engagement_type="none",
            reason_code="self_only",
            target_ids=target_ids,
            support_ids=support_ids,
        )
    if any(looks_like_app_feed(message) for message in window.targets):
        return _assessment(
            outcome="skip",
            engagement_type="none",
            reason_code="system_feed",
            target_ids=target_ids,
            support_ids=support_ids,
        )

    text = _window_text(window.targets)
    direct = contains_card_alias(text, character)
    triggered = contains_card_trigger(text, character)
    if direct:
        engagement_type: EngagementType = "direct"
        relevance_score = 4
        relevance_signal = "card_alias"
    elif triggered:
        engagement_type = "proactive"
        relevance_score = 3
        relevance_signal = "card_trigger"
    elif conversation_reply_enabled:
        engagement_type = "conversation"
        relevance_score = 2
        relevance_signal = "conversation_enabled"
    else:
        engagement_type = "none"
        relevance_score = 0
        relevance_signal = ""

    if looks_like_meta_suspicion(text):
        return _assessment(
            outcome="skip",
            engagement_type=engagement_type,
            reason_code="meta_suspicion",
            relevance=relevance_score,
            target_ids=target_ids,
            support_ids=support_ids,
            signals=(relevance_signal,) if relevance_signal else (),
        )
    if is_low_signal_chatter(text):
        reason_code = "awaiting_more_detail" if direct or triggered else "low_signal_ack"
        return _assessment(
            outcome="defer" if direct or triggered else "skip",
            engagement_type=engagement_type,
            reason_code=reason_code,
            relevance=relevance_score,
            target_ids=target_ids,
            support_ids=support_ids,
            signals=(relevance_signal,) if relevance_signal else (),
        )
    if engagement_type == "none":
        return _assessment(
            outcome="skip",
            engagement_type="none",
            reason_code="no_card_cue",
            target_ids=target_ids,
            support_ids=support_ids,
        )

    signals = detect_text_signals(
        text,
        has_support=bool(window.support),
        direct=direct,
        aliases=character.aliases,
    )
    signal_names: list[str] = [relevance_signal]
    primary = 0
    if signals.concrete_question:
        primary += 3
        signal_names.append("specific_question")
    if signals.compact_opinion:
        primary += 3
        signal_names.append("compact_opinion")
    if signals.disagreement:
        primary += 2
        signal_names.append("disagreement")
    if signals.reason_or_evidence:
        primary += 2
        signal_names.append("reason_or_evidence")
    substance_score = min(5, primary + int(signals.specific))
    if signals.specific:
        signal_names.append("specific_content")

    continuity_score = _continuity_score(window)
    if continuity_score:
        signal_names.append("thread_continuity")
    total_score = relevance_score + substance_score + continuity_score
    if signals.unresolved_anaphora:
        total_score = max(0, total_score - 2)
        signal_names.append("unresolved_anaphora")

    if engagement_type == "direct":
        reply = substance_score >= 2 and total_score >= 6 and not signals.unresolved_anaphora
        defer = relevance_score >= 4
    elif engagement_type == "proactive":
        reply = (
            relevance_score >= 3
            and substance_score >= 3
            and total_score >= 7
            and not signals.unresolved_anaphora
        )
        defer = (
            4 <= total_score <= 6
            or signals.unresolved_anaphora
            or (relevance_score >= 3 and substance_score == 0)
        )
    else:
        reply = substance_score >= 3 and total_score >= 6 and not signals.unresolved_anaphora
        defer = 4 <= total_score <= 5 or signals.unresolved_anaphora

    if reply:
        reason_code = _reply_reason_code(
            engagement_type=engagement_type,
            signals=signals,
            continuity_score=continuity_score,
        )
        outcome: AssessmentOutcome = "reply"
    elif defer:
        reason_code = "awaiting_context" if signals.unresolved_anaphora else "near_threshold"
        if (direct or triggered) and substance_score == 0:
            reason_code = "awaiting_more_detail"
        outcome = "defer"
    else:
        reason_code = "insufficient_substance"
        outcome = "skip"

    return _assessment(
        outcome=outcome,
        engagement_type=engagement_type,
        reason_code=reason_code,
        total=total_score,
        relevance=relevance_score,
        substance=substance_score,
        continuity=continuity_score,
        target_ids=target_ids,
        support_ids=support_ids,
        signals=tuple(signal_names),
    )


def detect_text_signals(
    text: str,
    *,
    has_support: bool = False,
    direct: bool = False,
    aliases: tuple[str, ...] = (),
) -> TextSignals:
    cleaned = clean_text(text)
    words = _words(cleaned)
    meaningful = _meaningful_terms(cleaned, excluded=aliases)
    concrete_question = (
        ("?" in cleaned and (len(meaningful) >= 2 or (direct and len(meaningful) >= 1)))
        or (len(words) >= 4 and bool(_QUESTION_START.search(cleaned)))
    )
    compact_opinion = bool(
        _STANCE_PATTERN.search(cleaned)
        or _PREDICATE_OPINION_PATTERN.search(cleaned)
        or _COMPARATIVE_PATTERN.search(cleaned)
    )
    disagreement = len(words) >= 4 and bool(_DISAGREEMENT_PATTERN.search(cleaned))
    reason_or_evidence = bool(_REASON_PATTERN.search(cleaned))
    non_url_text = re.sub(r"https?://\S+|\bwww\.\S+", "", cleaned)
    if re.search(r"https?://|\bwww\.", cleaned) and len(_meaningful_terms(non_url_text)) >= 2:
        reason_or_evidence = True
    unresolved_anaphora = bool(_ANAPHORIC_START.search(cleaned)) and not has_support
    return TextSignals(
        concrete_question=concrete_question,
        compact_opinion=compact_opinion,
        disagreement=disagreement,
        reason_or_evidence=reason_or_evidence,
        specific=len(meaningful) >= 2,
        unresolved_anaphora=unresolved_anaphora,
    )


def is_conversation_worthy_text(text: str, character: CharacterCard) -> bool:
    cleaned = clean_text(text)
    if not cleaned or is_low_signal_chatter(cleaned) or looks_like_meta_suspicion(cleaned):
        return False
    signals = detect_text_signals(cleaned, direct=contains_card_alias(cleaned, character))
    substance = min(
        5,
        (3 if signals.concrete_question else 0)
        + (3 if signals.compact_opinion else 0)
        + (2 if signals.disagreement else 0)
        + (2 if signals.reason_or_evidence else 0)
        + int(signals.specific),
    )
    relevance = 3 if contains_card_trigger(cleaned, character) else 2
    threshold = 7 if contains_card_trigger(cleaned, character) else 6
    return substance >= 3 and relevance + substance >= threshold and not signals.unresolved_anaphora


def is_low_signal_chatter(text: str) -> bool:
    cleaned = re.sub(r"[^a-z0-9'? ]+", " ", clean_text(text))
    normalized = " ".join(cleaned.split()).strip(" ?!")
    if not normalized:
        return True
    if normalized in _LOW_SIGNAL_PHRASES:
        return True
    if re.fullmatch(r"(yo+|hey+|hi+|hello+|sup|wsg)( chat| guys| yall| bro| dude)?", normalized):
        return True
    if len(normalized.split()) <= 3 and re.search(r"\b(how|what|wyd|sup|wsg)\b", normalized):
        return True
    return False


def looks_like_app_feed(message: MessageRecord) -> bool:
    author = str(getattr(message, "author", "") or "").lower()
    text = clean_text(str(getattr(message, "text", "") or ""))
    if "app" in author and re.search(r"\b(were playing|started playing|level up|verified app)\b", text):
        return True
    return bool(re.search(r"\b(verified app|new achievement|started a game|were playing)\b", text))


def looks_like_meta_suspicion(text: str) -> bool:
    cleaned = clean_text(text)
    if re.search(r"\b(chatgpt|llm|bot|automated|automation|fake account|posting behavior)\b", cleaned):
        return True
    words = _words(cleaned)
    return "ai" in words and bool(
        re.search(r"\b(mimic|grammar|human|person|posting|behavior|detect|sounds|sus|suspicious)\b", cleaned)
    )


def contains_card_alias(text: str, character: CharacterCard) -> bool:
    return any(term_in_text(alias, text) for alias in character.aliases)


def contains_card_trigger(text: str, character: CharacterCard) -> bool:
    return any(term_in_text(keyword, text) for keyword in character.trigger_keywords)


def term_in_text(term: str, text: str) -> bool:
    cleaned_term = " ".join(str(term or "").lower().split())
    if not cleaned_term:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(cleaned_term)}(?![a-z0-9])", str(text or "").lower()))


def clean_text(text: str) -> str:
    return " ".join(sanitize_outgoing_draft(str(text or "")).lower().split())


def _relevant_support(
    preceding: list[MessageRecord],
    targets: tuple[MessageRecord, ...],
) -> list[MessageRecord]:
    if not preceding:
        return []
    target_text = _window_text(targets)
    target_author = _author_key(targets[0])
    anaphoric = bool(_ANAPHORIC_START.search(target_text))
    target_terms = set(_meaningful_terms(target_text))
    selected: list[MessageRecord] = []
    for message in reversed(preceding):
        same_author = _author_key(message) == target_author
        overlap = bool(target_terms.intersection(_meaningful_terms(message.text)))
        if same_author or anaphoric or overlap:
            selected.append(message)
            if not same_author:
                break
        elif selected:
            break
    return list(reversed(selected))


def _continuity_score(window: ConversationWindow) -> int:
    if not window.support:
        return 0
    target_author = _author_key(window.targets[0])
    if any(_author_key(message) == target_author for message in window.support):
        return 2
    target_text = _window_text(window.targets)
    if _ANAPHORIC_START.search(target_text):
        return 2
    target_terms = set(_meaningful_terms(target_text))
    if any(target_terms.intersection(_meaningful_terms(message.text)) for message in window.support):
        return 1
    return 0


def _reply_reason_code(
    *,
    engagement_type: EngagementType,
    signals: TextSignals,
    continuity_score: int,
) -> str:
    if engagement_type == "direct":
        return "direct_cue_with_substance"
    if engagement_type == "proactive":
        return "card_trigger_with_substance"
    if continuity_score:
        return "thread_continuation"
    if signals.concrete_question:
        return "specific_question"
    if signals.compact_opinion:
        return "compact_opinion"
    return "grounded_claim"


def _assessment(
    *,
    outcome: AssessmentOutcome,
    engagement_type: EngagementType,
    reason_code: str,
    total: int = 0,
    relevance: int = 0,
    substance: int = 0,
    continuity: int = 0,
    target_ids: tuple[str, ...] = (),
    support_ids: tuple[str, ...] = (),
    signals: tuple[str, ...] = (),
) -> RelevanceAssessment:
    reasons = {
        "awaiting_context": "conversation source needs adjacent context before a grounded reply",
        "awaiting_more_detail": "direct or tracked cue is too thin to answer yet",
        "card_trigger_with_substance": "tracked card cue with a grounded reply target",
        "compact_opinion": "compact opinion with a concrete reply target",
        "direct_cue_with_substance": "direct name cue with a grounded reply target",
        "grounded_claim": "grounded claim with enough substance to answer",
        "insufficient_substance": "conversation source too thin or ambiguous for a grounded draft",
        "low_signal_ack": "low-signal acknowledgement or chatter",
        "meta_suspicion": "AI/bot-suspicion thread skipped unless manually selected",
        "near_threshold": "candidate is close but needs more context or detail",
        "no_candidate": "no non-self source message to answer",
        "no_card_cue": "no conversation permission, card trigger, or direct name cue",
        "self_only": "only configured character messages were available",
        "specific_question": "specific question with a grounded reply target",
        "system_feed": "app or system feed text is not a user reply target",
        "thread_continuation": "compact continuation resolved by adjacent conversation context",
    }
    return RelevanceAssessment(
        outcome=outcome,
        engagement_type=engagement_type,
        total_score=total,
        relevance_score=relevance,
        substance_score=substance,
        continuity_score=continuity,
        reason_code=reason_code,
        reason=reasons.get(reason_code, reason_code.replace("_", " ")),
        signals=signals,
        target_message_ids=target_ids,
        support_message_ids=support_ids,
    )


def _window_text(messages: tuple[MessageRecord, ...]) -> str:
    return "\n".join(str(message.text or "") for message in messages)


def _has_text(message: MessageRecord) -> bool:
    return bool(str(getattr(message, "text", "") or "").strip())


def _words(text: str) -> list[str]:
    return re.findall(r"\b[a-z0-9']+\b", clean_text(text))


def _meaningful_terms(text: str, *, excluded: tuple[str, ...] = ()) -> list[str]:
    excluded_terms = {word for term in excluded for word in _words(term)}
    return [
        word
        for word in _words(text)
        if len(word) > 1 and word not in _STOPWORDS and word not in excluded_terms
    ]


def _author_key(message: MessageRecord) -> str:
    author_id = str(getattr(message, "author_id", "") or "").strip()
    if author_id:
        return f"id:{author_id}"
    return "name:" + _normalize_author(str(getattr(message, "author", "") or ""))


def _normalize_author(value: str) -> str:
    return " ".join(clean_discord_display_name(value).lower().split())


def _is_character_message(message: MessageRecord, character: CharacterCard) -> bool:
    author = _normalize_author(message.author)
    names = {_normalize_author(character.name), *(_normalize_author(alias) for alias in character.aliases)}
    return bool(author) and author in names
