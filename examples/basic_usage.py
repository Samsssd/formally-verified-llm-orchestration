#!/usr/bin/env python3
"""Multi-agent research demo using excelsior-harness.

Demonstrates the full orchestration loop with mock LLM calls:
  1. Supervisor receives task, dispatches to researcher
  2. Researcher uses web_search tool
  3. Supervisor dispatches to coder
  4. Coder uses code_execute tool
  5. Supervisor signals completion

All LLM calls are mocked — no API keys required.
Run: python examples/basic_usage.py
"""

import logging
import sys

from excelsior_harness import (
    AgentRole,
    AgentState,
    BudgetTracker,
    ContextManager,
    Harness,
    MockLLMClient,
    MockResponse,
    StateGraph,
    SupervisorAgent,
    ToolRegistry,
    WorkerAgent,
)


def main() -> None:
    # ── Configure logging for full observability ──
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-30s | %(levelname)-5s | %(message)s",
        stream=sys.stdout,
    )

    # ── Register mock tools ──
    registry = ToolRegistry()

    @registry.register
    def web_search(query: str) -> str:
        """Search the web for information on a topic."""
        return (
            f"Results for '{query}': Recent advances in AI agent frameworks "
            f"include LangGraph (state machines), CrewAI (role-based teams), "
            f"and AutoGen (conversational patterns)."
        )

    @registry.register
    def code_execute(code: str) -> str:
        """Execute Python code and return the output."""
        return "Output: Analysis complete. 3 frameworks compared across 5 dimensions."

    # ── Create agents with mock LLM clients ──
    # The supervisor's client is called twice per visit: once by step(), once by route()
    supervisor = SupervisorAgent(
        name="supervisor",
        role=AgentRole.SUPERVISOR,
        system_prompt=(
            "You coordinate a research team. Route to 'researcher' for "
            "information gathering and 'coder' for data analysis. "
            "Reply DONE when the task is complete."
        ),
        workers=["researcher", "coder"],
        llm_client=MockLLMClient(
            responses=[
                # Visit 1: step + route
                MockResponse(content="Starting research phase.", prompt_tokens=50, completion_tokens=10),
                MockResponse(content="ROUTE:researcher"),
                # Visit 2: step + route
                MockResponse(content="Research done. Starting analysis.", prompt_tokens=80, completion_tokens=10),
                MockResponse(content="ROUTE:coder"),
                # Visit 3: step + route
                MockResponse(content="All tasks complete. Final report ready.", prompt_tokens=120, completion_tokens=15),
                MockResponse(content="DONE"),
            ]
        ),
    )

    researcher = WorkerAgent(
        name="researcher",
        role=AgentRole.RESEARCHER,
        system_prompt="You gather information using web search.",
        task="Research AI agent framework patterns",
        llm_client=MockLLMClient(
            responses=[
                MockResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "name": "web_search",
                            "arguments": {"query": "AI agent framework patterns 2025"},
                        }
                    ],
                    prompt_tokens=60,
                    completion_tokens=20,
                ),
                MockResponse(
                    content="Research complete. Found 3 major framework patterns.",
                    prompt_tokens=100,
                    completion_tokens=30,
                ),
            ]
        ),
    )

    coder = WorkerAgent(
        name="coder",
        role=AgentRole.CODER,
        system_prompt="You analyze data by executing code.",
        task="Compare the frameworks quantitatively",
        llm_client=MockLLMClient(
            responses=[
                MockResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_2",
                            "name": "code_execute",
                            "arguments": {"code": "compare_frameworks()"},
                        }
                    ],
                    prompt_tokens=70,
                    completion_tokens=25,
                ),
                MockResponse(
                    content="Analysis complete. LangGraph best for reproducibility.",
                    prompt_tokens=90,
                    completion_tokens=35,
                ),
            ]
        ),
    )

    # ── Build the state graph ──
    graph = StateGraph()
    graph.add_node("supervisor", supervisor)
    graph.add_node("researcher", researcher)
    graph.add_node("coder", coder)

    graph.add_edge("researcher", "supervisor")
    graph.add_edge("coder", "supervisor")
    graph.add_conditional_edge("supervisor", supervisor.route)

    graph.set_entry_point("supervisor")
    graph.set_finish_point("supervisor")
    graph.validate()

    # ── Run the harness ──
    print("=" * 70)
    print("excelsior-harness: Multi-Agent Research Demo")
    print("=" * 70)

    harness = Harness(
        graph=graph,
        tool_registry=registry,
        budget_tracker=BudgetTracker(max_budget_usd=2.0),
        context_manager=ContextManager(max_context_tokens=4000, keep_recent=10),
        max_steps=20,
    )

    result = harness.run(AgentState(current_agent="supervisor"))

    # ── Print results ──
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"  Steps:           {result.step_count}")
    print(f"  Total tokens:    {result.total_tokens}")
    print(f"  Cost:            ${result.cost_usd:.4f}")
    print(f"  Terminated:      {result.termination_reason}")
    print(f"  Checkpoints:     {len(result.checkpoints)}")
    print(f"  Messages:        {len(result.messages)}")

    print("\n  Budget Summary:")
    for k, v in harness.budget_tracker.summary().items():
        print(f"    {k}: {v}")

    print("\n  Message Flow:")
    for i, msg in enumerate(result.messages):
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, dict):
            content = f"[tool result: {content.get('name', '?')}]"
        elif isinstance(content, str) and len(content) > 60:
            content = content[:60] + "..."
        print(f"    [{i}] {role}: {content}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
