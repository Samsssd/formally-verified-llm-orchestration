"""Tests for agent classes and MockLLMClient."""

from excelsior_harness._types import AgentRole, StepType
from excelsior_harness.agents import (
    BaseAgent,
    MockLLMClient,
    MockResponse,
    SupervisorAgent,
    WorkerAgent,
)
from excelsior_harness.state import AgentState
from excelsior_harness.tools import ToolRegistry


class TestMockLLMClient:
    def test_returns_queued_responses(self):
        client = MockLLMClient(
            responses=[
                MockResponse(content="first", prompt_tokens=10, completion_tokens=5),
                MockResponse(content="second", prompt_tokens=20, completion_tokens=10),
            ]
        )
        r1 = client.call(messages=[], tools=[])
        assert r1.content == "first"
        r2 = client.call(messages=[], tools=[])
        assert r2.content == "second"

    def test_cycles_when_exhausted(self):
        client = MockLLMClient(
            responses=[MockResponse(content="only")]
        )
        r1 = client.call(messages=[], tools=[])
        r2 = client.call(messages=[], tools=[])
        assert r1.content == "only"
        assert r2.content == "only"

    def test_tool_call_response(self):
        client = MockLLMClient(
            responses=[
                MockResponse(
                    content="",
                    tool_calls=[{"id": "t1", "name": "search", "arguments": {"query": "test"}}],
                )
            ]
        )
        r = client.call(messages=[], tools=[])
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0]["name"] == "search"


class TestBaseAgent:
    def test_step_returns_updated_state(self):
        client = MockLLMClient(
            responses=[MockResponse(content="Hello!", prompt_tokens=10, completion_tokens=5)]
        )
        agent = BaseAgent(
            name="test_agent",
            role=AgentRole.WORKER,
            system_prompt="You are a test agent.",
            llm_client=client,
        )
        state = AgentState(current_agent="test_agent")
        new_state, step_type = agent.step(state, ToolRegistry())
        assert step_type == StepType.LLM_CALL
        assert any(m["role"] == "assistant" for m in new_state.messages)


class TestWorkerAgent:
    def test_has_task_field(self):
        client = MockLLMClient(responses=[MockResponse(content="done")])
        worker = WorkerAgent(
            name="coder",
            role=AgentRole.CODER,
            system_prompt="You write code.",
            task="Implement feature X",
            llm_client=client,
        )
        assert worker.task == "Implement feature X"


class TestSupervisorAgent:
    def test_route_returns_worker_name(self):
        client = MockLLMClient(
            responses=[MockResponse(content="ROUTE:researcher")]
        )
        supervisor = SupervisorAgent(
            name="supervisor",
            role=AgentRole.SUPERVISOR,
            system_prompt="You supervise.",
            workers=["researcher", "coder"],
            llm_client=client,
        )
        state = AgentState(current_agent="supervisor")
        next_agent = supervisor.route(state)
        assert next_agent == "researcher"

    def test_route_returns_done_for_completion(self):
        client = MockLLMClient(
            responses=[MockResponse(content="DONE")]
        )
        supervisor = SupervisorAgent(
            name="supervisor",
            role=AgentRole.SUPERVISOR,
            system_prompt="You supervise.",
            workers=["researcher"],
            llm_client=client,
        )
        state = AgentState(current_agent="supervisor")
        next_agent = supervisor.route(state)
        assert next_agent is None
