from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import MessageRecord


DEFAULT_TOPIC_KEYWORDS = {
    "uap": {"uap", "ufo", "alien", "nhi", "disclosure", "craft", "orb"},
    "institutions": {"government", "pentagon", "nasa", "cia", "vatican", "congress"},
    "tech": {"ai", "model", "algorithm", "computer", "cyber", "tech", "data"},
    "money": {"money", "market", "billionaire", "stock", "crypto", "bank"},
    "religion": {"god", "soul", "pope", "religion", "spiritual", "christian"},
}


@dataclass(frozen=True)
class TopicSnapshot:
    channel_id: str
    top_topics: tuple[tuple[str, float], ...]
    recent_terms: tuple[tuple[str, int], ...]


class TopicTracker:
    def __init__(self, *, decay: float = 0.82) -> None:
        self.decay = decay
        self._scores: dict[str, Counter[str]] = defaultdict(Counter)

    def update(self, channel_id: str, messages: list[MessageRecord]) -> TopicSnapshot:
        scores = self._scores[channel_id]
        for topic in list(scores):
            scores[topic] *= self.decay
            if scores[topic] < 0.05:
                del scores[topic]

        recent_terms: Counter[str] = Counter()
        for message in messages:
            terms = _terms(message.text)
            recent_terms.update(terms)
            term_set = set(terms)
            for topic, keywords in DEFAULT_TOPIC_KEYWORDS.items():
                overlap = term_set & keywords
                if overlap:
                    scores[topic] += len(overlap)

        return TopicSnapshot(
            channel_id=channel_id,
            top_topics=tuple((topic, round(score, 2)) for topic, score in scores.most_common(5)),
            recent_terms=tuple(recent_terms.most_common(10)),
        )


def _terms(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9']+", text.lower()) if len(term) > 2]
