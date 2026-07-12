from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import MessageRecord


_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "been",
    "before",
    "but",
    "could",
    "does",
    "for",
    "from",
    "have",
    "into",
    "just",
    "like",
    "more",
    "not",
    "only",
    "really",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}


@dataclass(frozen=True)
class TopicSnapshot:
    channel_id: str
    top_topics: tuple[tuple[str, float], ...]
    recent_terms: tuple[tuple[str, int], ...]


class TopicTracker:
    def __init__(self, *, decay: float = 0.82) -> None:
        self.decay = decay
        self._scores: dict[str, dict[str, float]] = defaultdict(dict)

    def update(
        self,
        channel_id: str,
        messages: list[MessageRecord],
        *,
        tracked_terms: tuple[str, ...] = (),
    ) -> TopicSnapshot:
        scores = self._scores[channel_id]
        for topic in list(scores):
            scores[topic] *= self.decay
            if scores[topic] < 0.05:
                del scores[topic]

        recent_terms: Counter[str] = Counter()
        for message in messages:
            terms = _terms(message.text)
            recent_terms.update(terms)
            for term in set(terms):
                scores[term] = scores.get(term, 0.0) + 1.0

            for tracked_term in tracked_terms:
                cleaned = " ".join(str(tracked_term or "").lower().split())
                if cleaned and _term_in_text(cleaned, message.text):
                    scores[cleaned] = scores.get(cleaned, 0.0) + 2.0

        return TopicSnapshot(
            channel_id=channel_id,
            top_topics=tuple(
                (topic, round(score, 2))
                for topic, score in sorted(
                    scores.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:5]
            ),
            recent_terms=tuple(recent_terms.most_common(10)),
        )


def _terms(text: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9']+", text.lower())
        if len(term) > 2 and term not in _STOPWORDS
    ]


def _term_in_text(term: str, text: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", str(text or "").lower()))
