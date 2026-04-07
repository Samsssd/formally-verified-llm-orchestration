"""End-to-end integration test: multi-agent orchestration with mock LLM."""

from excelsior_harness._types import AgentRole, TerminationReason
from excelsior_harness.agents import (
    MockLLMClient,
    MockResponse,
    SupervisorAgent,
    WorkerAgent,
)
from excelsior_harness.budget import BudgetTracker
from excelsior_harness.context import ContextManager
from excelsior_harness.graph import StateGraph
from excelsior_harness.orchestrator import Harness
from excelsior_harness.state import AgentState
from excelsior_harness.tools import ToolRegistry


def test_multi_agent_research_flow():
    """Full supervisor -> researcher -> supervisor -> coder -> supervisor -> DONE flow."""

    # ── Tools ──
    registry = ToolRegistry()

    @registry.register
    def web_search(query: str) -> str:
        """Search the web for information."""
        return f"Search results for '{query}': AI agents are software that act autonomously."

    @registry.register
    def code_execute(code: str) -> str:
        """Execute Python code."""
        return "Execution output: 42"

    # ── Agents ──
    # The supervisor's LLM client is called twice per visit:
    # once by agent.step() in the main loop, then once by supervisor.route()
    # via the conditional graph edge. So we need paired responses.
    supervisor_client = MockLLMClient(
        responses=[
            # Visit 1: step() produces a message, route() decides next agent
            MockResponse(content="Dispatching researcher.", prompt_tokens=15, completion_tokens=10),
            MockResponse(content="ROUTE:researcher"),
            # Visit 2: step() produces a message, route() decides next agent
            MockResponse(content="Dispatching coder.", prompt_tokens=15, completion_tokens=10),
            MockResponse(content="ROUTE:coder"),
            # Visit 3: step() produces final message, route() signals done
            MockResponse(content="All tasks complete.", prompt_tokens=15, completion_tokens=10),
            MockResponse(content="DONE"),
        ]
    )
    supervisor = SupervisorAgent(
        name="supervisor",
        role=AgentRole.SUPERVISOR,
        system_prompt="You coordinate research tasks.",
        workers=["researcher", "coder"],
        llm_client=supervisor_client,
    )

    researcher_client = MockLLMClient(
        responses=[
            MockResponse(
                content="",
                tool_calls=[
                    {"id": "t1", "name": "web_search", "arguments": {"query": "AI agents"}}
                ],
                prompt_tokens=20,
                completion_tokens=15,
            ),
            MockResponse(
                content="Research complete: AI agents are autonomous software.",
                prompt_tokens=30,
                completion_tokens=20,
            ),
        ]
    )
    researcher = WorkerAgent(
        name="researcher",
        role=AgentRole.RESEARCHER,
        system_prompt="You research topics.",
        task="Research AI agents",
        llm_client=researcher_client,
    )

    coder_client = MockLLMClient(
        responses=[
            MockResponse(
                content="",
                tool_calls=[
                    {"id": "t2", "name": "code_execute", "arguments": {"code": "print(42)"}}
                ],
                prompt_tokens=15,
                completion_tokens=10,
            ),
            MockResponse(
                content="Analysis complete: result is 42.",
                prompt_tokens=25,
                completion_tokens=15,
            ),
        ]
    )
    coder = WorkerAgent(
        name="coder",
        role=AgentRole.CODER,
        system_prompt="You write and execute code.",
        task="Analyze data",
        llm_client=coder_client,
    )

    # ── Graph ──
    graph = StateGraph()
    graph.add_node("supervisor", supervisor)
    graph.add_node("researcher", researcher)
    graph.add_node("coder", coder)

    # Workers always return to supervisor
    graph.add_edge("researcher", "supervisor")
    graph.add_edge("coder", "supervisor")

    # Supervisor uses conditional routing (via its route() method)
    graph.add_conditional_edge("supervisor", supervisor.route)

    graph.set_entry_point("supervisor")
    graph.set_finish_point("supervisor")
    graph.validate()

    # ── Harness ──
    harness = Harness(
        graph=graph,
        tool_registry=registry,
        budget_tracker=BudgetTracker(max_budget_usd=5.0),
        context_manager=ContextManager(max_context_tokens=4000),
        max_steps=20,
    )

    state = AgentState(current_agent="supervisor")
    result = harness.run(state)

    # ── Assertions ──
    assert result.terminated is True
    assert result.termination_reason == TerminationReason.TASK_COMPLETE
    assert result.step_count > 0
    assert result.total_tokens > 0
    assert result.cost_usd > 0
    assert len(result.checkpoints) > 0

    # Verify tool calls happened
    tool_msgs = [m for m in result.messages if m["role"] == "tool"]
    assert len(tool_msgs) >= 2  # web_search + code_execute

    # Verify budget tracking
    budget = harness.budget_tracker.summary()
    assert budget["total_cost_usd"] > 0
    assert budget["remaining_usd"] < 5.0
