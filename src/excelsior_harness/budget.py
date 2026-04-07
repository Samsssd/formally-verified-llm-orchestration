"""Budget enforcement and cost tracking.

Custom implementation drawing from production patterns in minimal frameworks
like agenkit and shekel for cost-aware orchestration. Provides per-model
cost estimation with a hard USD ceiling that terminates the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Cost per 1 000 tokens: (prompt, completion)
COST_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.010, 0.030),
    # Anthropic
    "claude-opus-4-20250514": (0.015, 0.075),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-20250506": (0.0008, 0.004),
    # Fallback
    "_default": (0.005, 0.015),
}


class BudgetExceeded(Exception):
    """Raised when the cumulative cost exceeds the configured ceiling."""

    def __init__(self, total_cost: float, max_budget: float) -> None:
        self.total_cost = total_cost
        self.max_budget = max_budget
        super().__init__(
            f"Budget exceeded: ${total_cost:.4f} spent of ${max_budget:.4f} allowed"
        )


@dataclass
class BudgetTracker:
    """Track cumulative LLM costs and enforce a hard USD ceiling."""

    max_budget_usd: float
    total_cost: float = 0.0
    _by_model: dict[str, float] = field(default_factory=dict)

    def record(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Record a single LLM call. Returns cost. Raises BudgetExceeded if over."""
        prompt_rate, completion_rate = COST_TABLE.get(
            model, COST_TABLE["_default"]
        )
        cost = (prompt_tokens / 1000) * prompt_rate + (
            completion_tokens / 1000
        ) * completion_rate

        self.total_cost += cost
        self._by_model[model] = self._by_model.get(model, 0.0) + cost

        if self.total_cost > self.max_budget_usd:
            raise BudgetExceeded(self.total_cost, self.max_budget_usd)
        return cost

    def remaining(self) -> float:
        """USD remaining before the ceiling is hit."""
        return max(0.0, self.max_budget_usd - self.total_cost)

    def summary(self) -> dict:
        """Return a structured cost summary."""
        return {
            "max_budget_usd": self.max_budget_usd,
            "total_cost_usd": self.total_cost,
            "remaining_usd": self.remaining(),
            "by_model": dict(self._by_model),
        }
