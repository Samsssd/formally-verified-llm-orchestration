"""Property-based tests using Hypothesis.

These tests verify the same invariants that the Lean 4 specification proves
formally, but using randomized input generation. This creates a detection
method that sits between unit tests (example-based) and formal proofs
(exhaustive), and is directly comparable to both.

Properties tested:
  P1. Token accounting:  total = prompt + completion    (Lean: loop_tokens)
  P2. Step monotonicity:  step increases by 1           (Lean: step_inc_or_done)
  P3. State immutability: mutations return new objects   (Lean: N/A, structural)
  P4. Budget enforcement: cost > max raises exception    (Lean: loop_budget_safe)
  P5. Checkpoint accumulation: len grows by 1            (Lean: loop_ckpts)
  P6. Termination flag:   terminate sets done=True       (Lean: step_preserves_wf)
  P7. Token accumulation: tokens monotonically grow      (Lean: step_preserves_tokens)
  P8. Cost accumulation:  cost is non-negative & grows   (Lean: wf invariant 2)
  P9. Context truncation: system message preserved       (N/A in Lean)
  P10. Budget cost non-negative: recorded cost >= 0      (Lean: wf invariant 2)
  P11. Budget cost proportional: higher tokens -> higher cost (domain invariant)
"""

from __future__ import annotations

from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from excelsior_harness.state import AgentState
from excelsior_harness.budget import BudgetTracker, BudgetExceeded
from excelsior_harness.context import ContextManager
from excelsior_harness._types import TerminationReason


# ─────────────────────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────────────────────

token_count = st.integers(min_value=0, max_value=50_000)
small_cost = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
budget_amount = st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False)
step_count = st.integers(min_value=1, max_value=20)
message_role = st.sampled_from(["user", "assistant", "system"])
message_content = st.text(min_size=1, max_size=200, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
))


# ─────────────────────────────────────────────────────────────────────────────
# P1. Token Accounting Invariant  (Lean: loop_tokens, step_preserves_tokens)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    prompt_tokens=token_count,
    completion_tokens=token_count,
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_token_accounting_single(prompt_tokens: int, completion_tokens: int):
    """After one record_usage, total = prompt + completion."""
    state = AgentState()
    new = state.record_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=0.0,
    )
    assert new.total_tokens == new.prompt_tokens + new.completion_tokens


@given(
    calls=st.lists(
        st.tuples(token_count, token_count),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_token_accounting_multi(calls: list[tuple[int, int]]):
    """Token invariant holds after arbitrary sequence of record_usage calls."""
    state = AgentState()
    for pt, ct in calls:
        state = state.record_usage(prompt_tokens=pt, completion_tokens=ct, cost=0.0)
    assert state.total_tokens == state.prompt_tokens + state.completion_tokens


# ─────────────────────────────────────────────────────────────────────────────
# P2. Step Monotonicity  (Lean: step_inc_or_done)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    prompt_tokens=token_count,
    completion_tokens=token_count,
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_step_increment(prompt_tokens: int, completion_tokens: int):
    """Each record_usage increments step_count by exactly 1."""
    state = AgentState()
    old_step = state.step_count
    new = state.record_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=0.0,
    )
    assert new.step_count == old_step + 1


@given(n=st.integers(min_value=1, max_value=15))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_step_equals_call_count(n: int):
    """After n calls, step_count == n."""
    state = AgentState()
    for _ in range(n):
        state = state.record_usage(prompt_tokens=10, completion_tokens=10, cost=0.0)
    assert state.step_count == n


# ─────────────────────────────────────────────────────────────────────────────
# P3. State Immutability  (Lean: structural — pure functional by construction)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    prompt_tokens=token_count,
    completion_tokens=token_count,
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_record_usage_immutable(prompt_tokens: int, completion_tokens: int):
    """record_usage returns a NEW state; original is unchanged."""
    state = AgentState(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    original_pt = state.prompt_tokens
    original_ct = state.completion_tokens
    original_tt = state.total_tokens
    original_id = id(state)

    new = state.record_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=0.0,
    )
    assert id(new) != original_id, "record_usage must return a new object"
    assert state.prompt_tokens == original_pt, "original prompt_tokens mutated"
    assert state.completion_tokens == original_ct, "original completion_tokens mutated"
    assert state.total_tokens == original_tt, "original total_tokens mutated"


@given(
    role=message_role,
    content=message_content,
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_add_message_immutable(role: str, content: str):
    """add_message returns a NEW state; original messages unchanged."""
    state = AgentState()
    original_msgs = list(state.messages)
    original_id = id(state)

    new = state.add_message(role, content)
    assert id(new) != original_id, "add_message must return a new object"
    assert state.messages == original_msgs, "original messages mutated"
    assert len(new.messages) == len(original_msgs) + 1


# ─────────────────────────────────────────────────────────────────────────────
# P4. Budget Enforcement  (Lean: loop_budget_safe)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    max_budget=budget_amount,
    n_calls=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_budget_enforcement(max_budget: float, n_calls: int):
    """Budget tracker always raises when cost > max_budget."""
    tracker = BudgetTracker(max_budget_usd=max_budget)
    exceeded = False

    for _ in range(n_calls):
        try:
            tracker.record("gpt-4o", prompt_tokens=5000, completion_tokens=5000)
        except BudgetExceeded:
            exceeded = True
            break

    # Post-condition: if we didn't exceed, total_cost <= max_budget
    if not exceeded:
        assert tracker.total_cost <= max_budget


@given(
    max_budget=st.just(0.001),  # very small budget
    prompt_tokens=st.integers(min_value=100000, max_value=1000000),
)
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_budget_always_catches_large_cost(max_budget: float, prompt_tokens: int):
    """Large token usage always triggers budget exceeded on tiny budget."""
    tracker = BudgetTracker(max_budget_usd=max_budget)
    try:
        tracker.record("gpt-4o", prompt_tokens=prompt_tokens, completion_tokens=prompt_tokens)
        # If we get here, cost must be within budget
        assert tracker.total_cost <= max_budget
    except BudgetExceeded:
        assert tracker.total_cost > max_budget


# ─────────────────────────────────────────────────────────────────────────────
# P5. Checkpoint Accumulation  (Lean: loop_ckpts, continue_adds_ckpt)
# ─────────────────────────────────────────────────────────────────────────────

@given(n=st.integers(min_value=1, max_value=15))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_checkpoint_accumulates(n: int):
    """After n checkpoint() calls, len(checkpoints) == n."""
    state = AgentState()
    for i in range(n):
        state = state.record_usage(prompt_tokens=10, completion_tokens=10, cost=0.0)
        state = state.checkpoint()
    assert len(state.checkpoints) == n


@given(
    prompt_tokens=token_count,
    completion_tokens=token_count,
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_checkpoint_content(prompt_tokens: int, completion_tokens: int):
    """Checkpoint snapshot matches current state counters."""
    state = AgentState()
    state = state.record_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=0.0,
    )
    state = state.checkpoint()

    snap = state.checkpoints[-1]
    assert snap["step_count"] == state.step_count
    assert snap["total_tokens"] == state.total_tokens


# ─────────────────────────────────────────────────────────────────────────────
# P6. Termination Flag  (Lean: step_preserves_wf, specifically done=true paths)
# ─────────────────────────────────────────────────────────────────────────────

@given(reason=st.sampled_from(list(TerminationReason)))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_terminate_sets_flag(reason: TerminationReason):
    """terminate() always sets terminated=True."""
    state = AgentState()
    new = state.terminate(reason)
    assert new.terminated is True
    assert new.termination_reason == reason


@given(reason=st.sampled_from(list(TerminationReason)))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_terminate_immutable(reason: TerminationReason):
    """terminate() doesn't modify original state."""
    state = AgentState()
    assert state.terminated is False
    new = state.terminate(reason)
    assert state.terminated is False  # original unchanged
    assert new.terminated is True


# ─────────────────────────────────────────────────────────────────────────────
# P7. Token Monotonic Growth  (Lean: wf invariant — tokens always increase)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    calls=st.lists(
        st.tuples(token_count, token_count),
        min_size=2,
        max_size=10,
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_token_monotonic(calls: list[tuple[int, int]]):
    """Token counts never decrease across calls."""
    state = AgentState()
    prev_total = 0
    prev_prompt = 0
    prev_completion = 0

    for pt, ct in calls:
        state = state.record_usage(prompt_tokens=pt, completion_tokens=ct, cost=0.0)
        assert state.total_tokens >= prev_total
        assert state.prompt_tokens >= prev_prompt
        assert state.completion_tokens >= prev_completion
        prev_total = state.total_tokens
        prev_prompt = state.prompt_tokens
        prev_completion = state.completion_tokens


# ─────────────────────────────────────────────────────────────────────────────
# P8. Cost Accumulation  (Lean: wf invariant 2, cost ≤ maxBudget)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    costs=st.lists(
        small_cost,
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_cost_non_negative(costs: list[float]):
    """Cost is always non-negative and monotonically increasing."""
    state = AgentState()
    prev_cost = 0.0

    for c in costs:
        state = state.record_usage(prompt_tokens=10, completion_tokens=10, cost=c)
        assert state.cost_usd >= prev_cost
        assert state.cost_usd >= 0.0
        prev_cost = state.cost_usd


# ─────────────────────────────────────────────────────────────────────────────
# P9. Context Truncation Safety  (Lean: N/A — not modeled in spec)
# ─────────────────────────────────────────────────────────────────────────────

@given(
    n_messages=st.integers(min_value=2, max_value=50),
    keep_recent=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_context_preserves_system(n_messages: int, keep_recent: int):
    """Context truncation always preserves the system message."""
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    for i in range(n_messages - 1):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"Message {i}" * 50})

    cm = ContextManager(max_context_tokens=200, keep_recent=min(keep_recent, n_messages - 1))
    truncated = cm.prepare(messages)

    assert len(truncated) >= 1
    assert truncated[0]["role"] == "system"


# ---------------------------------------------------------------------------
# P10. Budget Cost Non-Negative  (catches M02: subtract instead of add)
# ---------------------------------------------------------------------------

@given(
    prompt_tokens=st.integers(min_value=100, max_value=10000),
    completion_tokens=st.integers(min_value=100, max_value=10000),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_budget_cost_non_negative(prompt_tokens: int, completion_tokens: int):
    """Recorded cost must be non-negative after every call."""
    tracker = BudgetTracker(max_budget_usd=100.0)
    tracker.record("gpt-4o", prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    assert tracker.total_cost >= 0.0, (
        f"Budget total_cost went negative: {tracker.total_cost}"
    )


@given(n=st.integers(min_value=1, max_value=10))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_budget_cost_monotonic(n: int):
    """Budget cost monotonically increases with each call."""
    tracker = BudgetTracker(max_budget_usd=1000.0)  # very high to avoid exception
    prev_cost = 0.0
    for _ in range(n):
        try:
            tracker.record("gpt-4o", prompt_tokens=500, completion_tokens=500)
        except BudgetExceeded:
            break
        assert tracker.total_cost >= prev_cost, (
            f"Cost decreased: {prev_cost} -> {tracker.total_cost}"
        )
        prev_cost = tracker.total_cost


# ---------------------------------------------------------------------------
# P11. Budget Cost Proportionality  (catches M13: /100 instead of /1000)
# ---------------------------------------------------------------------------

@given(
    tokens_small=st.integers(min_value=100, max_value=500),
    tokens_large=st.integers(min_value=5000, max_value=50000),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_budget_cost_proportional(tokens_small: int, tokens_large: int):
    """More tokens should produce proportionally more cost (same rate).

    Specifically: cost(2x tokens) should be approximately 2x cost(1x tokens).
    We test that cost with tokens_large > cost with tokens_small when
    tokens_large > tokens_small.
    """
    assume(tokens_large > tokens_small)

    tracker_small = BudgetTracker(max_budget_usd=10000.0)
    tracker_large = BudgetTracker(max_budget_usd=10000.0)

    cost_small = tracker_small.record("gpt-4o", prompt_tokens=tokens_small, completion_tokens=tokens_small)
    cost_large = tracker_large.record("gpt-4o", prompt_tokens=tokens_large, completion_tokens=tokens_large)

    assert cost_large > cost_small, (
        f"Larger token count ({tokens_large}) should cost more than smaller ({tokens_small}): "
        f"{cost_large} vs {cost_small}"
    )

    # Proportionality: ratio of costs should be close to ratio of tokens
    ratio_tokens = tokens_large / tokens_small
    ratio_costs = cost_large / cost_small if cost_small > 0 else float('inf')

    # Allow 1% tolerance for floating point
    assert abs(ratio_costs - ratio_tokens) < ratio_tokens * 0.01, (
        f"Cost ratio ({ratio_costs:.4f}) should match token ratio ({ratio_tokens:.4f})"
    )


# ---------------------------------------------------------------------------
# P12. Checkpoint Immutability  (catches M28: overwrite instead of append)
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=2, max_value=8))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_checkpoint_history_preserved(n: int):
    """Previous checkpoints must not be lost when new ones are added."""
    state = AgentState()

    for i in range(n):
        state = state.record_usage(prompt_tokens=10 * (i + 1), completion_tokens=5, cost=0.0)
        state = state.checkpoint()

        # After each checkpoint, verify ALL previous checkpoints still exist
        assert len(state.checkpoints) == i + 1, (
            f"After {i + 1} checkpoints, expected {i + 1} entries, got {len(state.checkpoints)}"
        )

        # Verify the latest checkpoint reflects current state
        assert state.checkpoints[-1]["step_count"] == state.step_count


# ---------------------------------------------------------------------------
# P13. Budget Cost Accuracy  (catches M13: /100 instead of /1000, M07: wrong rate)
# ---------------------------------------------------------------------------

@given(
    model=st.sampled_from(["gpt-4o", "gpt-4o-mini"]),
    prompt_tokens=st.integers(min_value=1000, max_value=50000),
    completion_tokens=st.integers(min_value=1000, max_value=50000),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_prop_cost_matches_rate_table(model: str, prompt_tokens: int, completion_tokens: int):
    """Recorded cost must match (tokens / 1000) * rate formula.

    This tests the relationship between the COST_TABLE rates and the
    actual recorded cost. A mutation that changes the divisor (e.g., /100
    instead of /1000) or uses the wrong rate will break this invariant.
    """
    from excelsior_harness.budget import COST_TABLE

    prompt_rate, completion_rate = COST_TABLE[model]
    tracker = BudgetTracker(max_budget_usd=100000.0)

    cost = tracker.record(model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    expected = (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate

    # Allow 0.1% tolerance for floating point
    assert abs(cost - expected) < expected * 0.001 + 1e-12, (
        f"Cost ${cost:.8f} doesn't match expected ${expected:.8f} for {model}"
    )
