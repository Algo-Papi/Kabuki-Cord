from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .state_io import write_json_file


MODEL_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
}


@dataclass(frozen=True)
class BudgetCheck:
    allowed: bool
    reason: str
    estimated_cost_usd: float


@dataclass(frozen=True)
class UsageRecord:
    created_at: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    kind: str


class BudgetManager:
    def __init__(
        self,
        usage_file: Path,
        *,
        model: str,
        max_daily_usd: float,
        max_session_usd: float,
        max_calls_per_run: int,
    ) -> None:
        self.usage_file = usage_file
        self.model = model
        self.max_daily_usd = max_daily_usd
        self.max_session_usd = max_session_usd
        self.max_calls_per_run = max_calls_per_run
        self.session_spend = 0.0
        self.session_calls = 0
        self._records = self._load()

    def check(self, *, estimated_input_tokens: int, max_output_tokens: int) -> BudgetCheck:
        estimated_cost = self.estimate_cost(
            input_tokens=estimated_input_tokens,
            output_tokens=max_output_tokens,
        )
        if self.session_calls >= self.max_calls_per_run:
            return BudgetCheck(False, "max LLM calls for this run reached", estimated_cost)
        if self.session_spend + estimated_cost > self.max_session_usd:
            return BudgetCheck(False, "session budget would be exceeded", estimated_cost)
        if self.daily_spend() + estimated_cost > self.max_daily_usd:
            return BudgetCheck(False, "daily budget would be exceeded", estimated_cost)
        return BudgetCheck(True, "within budget", estimated_cost)

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        input_rate, output_rate = MODEL_PRICES_PER_MILLION.get(
            self.model,
            MODEL_PRICES_PER_MILLION["gpt-5.4-mini"],
        )
        return ((input_tokens / 1_000_000) * input_rate) + (
            (output_tokens / 1_000_000) * output_rate
        )

    def record(self, *, input_tokens: int, output_tokens: int, kind: str = "actual") -> UsageRecord:
        cost = self.estimate_cost(input_tokens=input_tokens, output_tokens=output_tokens)
        record = UsageRecord(
            created_at=datetime.now(timezone.utc).isoformat(),
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            kind=kind,
        )
        self.session_calls += 1
        self.session_spend += cost
        self._records.append(record)
        self._save()
        return record

    def daily_spend(self) -> float:
        today = datetime.now(timezone.utc).date()
        total = 0.0
        for record in self._records:
            if datetime.fromisoformat(record.created_at).date() == today:
                total += record.cost_usd
        return total

    def summary(self) -> dict[str, float | int | str]:
        total = sum(record.cost_usd for record in self._records)
        input_tokens = sum(record.input_tokens for record in self._records)
        output_tokens = sum(record.output_tokens for record in self._records)
        return {
            "model": self.model,
            "records": len(self._records),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "daily_spend_usd": self.daily_spend(),
            "total_spend_usd": total,
        }

    @staticmethod
    def approx_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def _load(self) -> list[UsageRecord]:
        if not self.usage_file.exists():
            return []
        payload = json.loads(self.usage_file.read_text(encoding="utf-8"))
        return [UsageRecord(**row) for row in payload.get("records", [])]

    def _save(self) -> None:
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_file(self.usage_file, {"records": [record.__dict__ for record in self._records]})
