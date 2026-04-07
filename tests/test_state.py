"""Tests for AgentState."""

from excelsior_harness._types import TerminationReason
from excelsior_harness.state import AgentState


class TestAgentState:
    def test_default_creation(self):
        state = AgentState()
        assert state.messages == []
        assert state.current_agent == ""
        assert state.step_count == 0
        assert state.cost_usd == 0.0
        assert state.terminated is False
        assert state.termination_reason is None

    def test_add_message_returns_new_state(self):
        state = AgentState()
        new_state = state.add_message("user", "hello")
        assert len(new_state.messages) == 1
        assert new_state.messages[0]["role"] == "user"
        assert new_state.messages[0]["content"] == "hello"
        assert len(state.messages) == 0

    def test_add_message_with_kwargs(self):
        state = AgentState()
        new_state = state.add_message("assistant", "hi", tool_calls=[{"id": "1"}])
        assert new_state.messages[0]["tool_calls"] == [{"id": "1"}]

    def test_record_usage(self):
        state = AgentState()
        new_state = state.record_usage(
            prompt_tokens=100, completion_tokens=50, cost=0.002
        )
        assert new_state.prompt_tokens == 100
        assert new_state.completion_tokens == 50
        assert new_state.total_tokens == 150
        assert new_state.cost_usd == 0.002
        assert new_state.step_count == 1

    def test_record_usage_accumulates(self):
        state = AgentState()
        state = state.record_usage(prompt_tokens=100, completion_tokens=50, cost=0.002)
        state = state.record_usage(prompt_tokens=200, completion_tokens=100, cost=0.005)
        assert state.prompt_tokens == 300
        assert state.completion_tokens == 150
        assert state.total_tokens == 450
        assert state.cost_usd == 0.007
        assert state.step_count == 2

    def test_checkpoint(self):
        state = AgentState(current_agent="worker1", step_count=3)
        new_state = state.checkpoint()
        assert len(new_state.checkpoints) == 1
        assert new_state.checkpoints[0]["step_count"] == 3
        assert new_state.checkpoints[0]["current_agent"] == "worker1"

    def test_terminate(self):
        state = AgentState()
        new_state = state.terminate(TerminationReason.MAX_STEPS)
        assert new_state.terminated is True
        assert new_state.termination_reason == TerminationReason.MAX_STEPS
