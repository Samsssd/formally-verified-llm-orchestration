"""Tests for budget tracking and enforcement."""

import pytest

from excelsior_harness.budget import BudgetExceeded, BudgetTracker


class TestBudgetTracker:
    def test_initial_state(self):
        bt = BudgetTracker(max_budget_usd=1.0)
        assert bt.remaining() == 1.0
        assert bt.total_cost == 0.0

    def test_record_cost(self):
        bt = BudgetTracker(max_budget_usd=1.0)
        cost = bt.record(model="gpt-4o", prompt_tokens=1000, completion_tokens=500)
        assert cost > 0
        assert bt.total_cost == cost
        assert bt.remaining() == 1.0 - cost

    def test_budget_exceeded_raises(self):
        bt = BudgetTracker(max_budget_usd=0.001)
        with pytest.raises(BudgetExceeded) as exc_info:
            bt.record(model="gpt-4o", prompt_tokens=100000, completion_tokens=50000)
        assert exc_info.value.total_cost > 0.001

    def test_unknown_model_uses_default(self):
        bt = BudgetTracker(max_budget_usd=1.0)
        cost = bt.record(
            model="unknown-model-xyz", prompt_tokens=1000, completion_tokens=500
        )
        assert cost > 0

    def test_summary(self):
        bt = BudgetTracker(max_budget_usd=5.0)
        bt.record(model="gpt-4o", prompt_tokens=1000, completion_tokens=500)
        bt.record(model="claude-sonnet-4-20250514", prompt_tokens=2000, completion_tokens=1000)
        summary = bt.summary()
        assert summary["max_budget_usd"] == 5.0
        assert summary["total_cost_usd"] > 0
        assert "gpt-4o" in summary["by_model"]
        assert "claude-sonnet-4-20250514" in summary["by_model"]
