"""Tests for the Harness orchestrator."""

import pytest

from excelsior_harness._types import AgentRole, TerminationReason
from excelsior_harness.agents import BaseAgent, MockLLMClient, MockResponse
from excelsior_harness.budget import BudgetTracker
from excelsior_harness.context import ContextManager
from excelsior_harness.graph import StateGraph
from excelsior_harness.orchestrator import Harness
from excelsior_harness.state import AgentState
from excelsior_harness.tools import ToolRegistry


def _simple_graph() -> tuple[StateGraph, ToolRegistry]:
    """Build a minimal one-agent graph for testing."""
    client = MockLLMClient(
        responses=[
            MockResponse(content="Step 1 done", prompt_tokens=10, completion_tokens=5),
            MockResponse(content="Step 2 done", prompt_tokens=10, completion_tokens=5),
            MockResponse(content="FINAL ANSWER", prompt_tokens=10, completion_tokens=5),
        ]
    )
    agent = BaseAgent(
        name="worker",
        role=AgentRole.WORKER,
        system_prompt="You are a worker.",
        llm_client=client,
    )
    graph = StateGraph()
    graph.add_node("worker", agent)
    graph.add_edge("worker", "worker")  # Self-loop until max_steps
    graph.set_entry_point("worker")
    graph.set_finish_point("worker")
    graph.validate()
    return graph, ToolRegistry()


class TestHarness:
    def test_max_steps_termination(self):
        graph, registry = _simple_graph()
        harness = Harness(
            graph=graph,
            tool_registry=registry,
            budget_tracker=BudgetTracker(max_budget_usd=10.0),
            context_manager=ContextManager(),
            max_steps=2,
        )
        state = AgentState(current_agent="worker")
        result = harness.run(state)
        assert result.terminated is True
        assert result.termination_reason == TerminationReason.MAX_STEPS
        assert result.step_count == 2

    def test_budget_termination(self):
        graph, registry = _simple_graph()
        # Tiny budget that will be exceeded
        harness = Harness(
            graph=graph,
            tool_registry=registry,
            budget_tracker=BudgetTracker(max_budget_usd=0.0),
            context_manager=ContextManager(),
            max_steps=50,
        )
        state = AgentState(current_agent="worker")
        result = harness.run(state)
        assert result.terminated is True
        assert result.termination_reason == TerminationReason.BUDGET_EXCEEDED

    def test_tool_execution_in_loop(self):
        registry = ToolRegistry()

        @registry.register
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        client = MockLLMClient(
            responses=[
                MockResponse(
                    content="",
                    tool_calls=[
                        {"id": "t1", "name": "add", "arguments": {"a": 2, "b": 3}}
                    ],
                    prompt_tokens=15,
                    completion_tokens=8,
                ),
                MockResponse(content="The answer is 5", prompt_tokens=20, completion_tokens=10),
            ]
        )
        agent = BaseAgent(
            name="calculator",
            role=AgentRole.WORKER,
            system_prompt="You calculate.",
            llm_client=client,
        )
        graph = StateGraph()
        graph.add_node("calculator", agent)
        graph.set_entry_point("calculator")
        graph.set_finish_point("calculator")
        graph.validate()

        harness = Harness(
            graph=graph,
            tool_registry=registry,
            budget_tracker=BudgetTracker(max_budget_usd=10.0),
            context_manager=ContextManager(),
            max_steps=5,
        )
        state = AgentState(current_agent="calculator")
        result = harness.run(state)
        # Should have tool result in messages
        tool_msgs = [m for m in result.messages if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"]["result"] == 5

    def test_checkpoints_created(self):
        graph, registry = _simple_graph()
        harness = Harness(
            graph=graph,
            tool_registry=registry,
            budget_tracker=BudgetTracker(max_budget_usd=10.0),
            context_manager=ContextManager(),
            max_steps=2,
        )
        state = AgentState(current_agent="worker")
        result = harness.run(state)
        assert len(result.checkpoints) == 2
