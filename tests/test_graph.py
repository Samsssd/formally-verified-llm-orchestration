"""Tests for the StateGraph router."""

import pytest

from excelsior_harness._types import AgentRole
from excelsior_harness.agents import BaseAgent, MockLLMClient, MockResponse
from excelsior_harness.graph import StateGraph
from excelsior_harness.state import AgentState


def _make_agent(name: str) -> BaseAgent:
    return BaseAgent(
        name=name,
        role=AgentRole.WORKER,
        system_prompt=f"You are {name}.",
        llm_client=MockLLMClient(),
    )


class TestStateGraph:
    def test_add_node_and_get_agent(self):
        g = StateGraph()
        agent = _make_agent("a")
        g.add_node("a", agent)
        assert g.get_agent("a") is agent

    def test_get_nonexistent_node_raises(self):
        g = StateGraph()
        with pytest.raises(KeyError):
            g.get_agent("missing")

    def test_unconditional_edge(self):
        g = StateGraph()
        g.add_node("a", _make_agent("a"))
        g.add_node("b", _make_agent("b"))
        g.add_edge("a", "b")
        g.set_entry_point("a")
        g.set_finish_point("b")
        state = AgentState(current_agent="a")
        assert g.route(state) == "b"

    def test_conditional_edge(self):
        g = StateGraph()
        g.add_node("supervisor", _make_agent("supervisor"))
        g.add_node("worker1", _make_agent("worker1"))
        g.add_node("worker2", _make_agent("worker2"))
        g.add_conditional_edge(
            "supervisor",
            lambda s: "worker1" if s.step_count < 3 else "worker2",
        )
        g.set_entry_point("supervisor")
        state = AgentState(current_agent="supervisor", step_count=1)
        assert g.route(state) == "worker1"
        state = AgentState(current_agent="supervisor", step_count=5)
        assert g.route(state) == "worker2"

    def test_finish_point_returns_none(self):
        g = StateGraph()
        g.add_node("a", _make_agent("a"))
        g.set_entry_point("a")
        g.set_finish_point("a")
        state = AgentState(current_agent="a")
        assert g.route(state) is None

    def test_validate_missing_entry_point(self):
        g = StateGraph()
        g.add_node("a", _make_agent("a"))
        with pytest.raises(ValueError, match="entry point"):
            g.validate()

    def test_validate_edge_references_unknown_node(self):
        g = StateGraph()
        g.add_node("a", _make_agent("a"))
        g.set_entry_point("a")
        with pytest.raises(ValueError, match="unknown node"):
            g.add_edge("a", "nonexistent")

    def test_validate_passes_for_valid_graph(self):
        g = StateGraph()
        g.add_node("a", _make_agent("a"))
        g.add_node("b", _make_agent("b"))
        g.add_edge("a", "b")
        g.set_entry_point("a")
        g.set_finish_point("b")
        g.validate()
