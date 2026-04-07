"""Agent definitions with role-based hierarchy and mock LLM client.

Adopted CrewAI-style agent roles and hierarchical supervisor pattern
for clear separation of concerns in multi-agent teams. Each agent has
a role, system prompt, and step() method that calls the LLM.

The MockLLMClient simulates LLM responses so the harness can run
without API keys, enabling full reproducibility for the arXiv paper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from excelsior_harness._types import AgentRole, StepType
from excelsior_harness.state import AgentState
from excelsior_harness.tools import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock LLM Client
# ---------------------------------------------------------------------------

@dataclass
class MockResponse:
    """Simulated LLM response matching the shape of real SDK responses."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 10
    completion_tokens: int = 5


@dataclass
class MockLLMClient:
    """Configurable mock that returns pre-scripted responses.

    Cycles back to the last response when the queue is exhausted.
    Swap in a real anthropic/openai client for live usage.
    """

    responses: list[MockResponse] = field(default_factory=lambda: [MockResponse(content="OK")])
    _index: int = field(default=0, repr=False)

    def call(self, *, messages: list[dict], tools: list[dict] | None = None) -> MockResponse:
        """Simulate an LLM API call."""
        resp = self.responses[min(self._index, len(self.responses) - 1)]
        self._index += 1
        logger.debug(
            "MockLLM call #%d -> content=%r, tool_calls=%d",
            self._index,
            resp.content[:40],
            len(resp.tool_calls),
        )
        return resp


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@dataclass
class BaseAgent:
    """Base agent with an LLM client and a step() method."""

    name: str
    role: AgentRole
    system_prompt: str
    llm_client: MockLLMClient
    allowed_tools: list[str] = field(default_factory=list)
    model: str = "gpt-4o"

    def step(
        self, state: AgentState, tool_registry: ToolRegistry
    ) -> tuple[AgentState, StepType]:
        """Execute one LLM call and return updated state + step type."""
        messages = [{"role": "system", "content": self.system_prompt}] + state.messages

        all_schemas = tool_registry.to_openai_schema()
        agent_tools = (
            [s for s in all_schemas if s["function"]["name"] in self.allowed_tools]
            if self.allowed_tools
            else all_schemas
        )

        response = self.llm_client.call(messages=messages, tools=agent_tools)

        if response.tool_calls:
            step_type = StepType.TOOL_CALL
            new_state = state.add_message(
                "assistant", response.content, tool_calls=response.tool_calls
            )
        else:
            step_type = StepType.LLM_CALL
            new_state = state.add_message("assistant", response.content)

        new_state = new_state.record_usage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost=0.0,
        )

        logger.info(
            "Agent %s step: type=%s, tokens=%d+%d",
            self.name,
            step_type.value,
            response.prompt_tokens,
            response.completion_tokens,
        )
        return new_state, step_type


@dataclass
class WorkerAgent(BaseAgent):
    """A worker agent with a specific task assignment."""

    task: str = ""

    def step(
        self, state: AgentState, tool_registry: ToolRegistry
    ) -> tuple[AgentState, StepType]:
        """Step with task context injected into system prompt."""
        original_prompt = self.system_prompt
        self.system_prompt = f"{original_prompt}\n\nYour current task: {self.task}"
        result = super().step(state, tool_registry)
        self.system_prompt = original_prompt
        return result


@dataclass
class SupervisorAgent(BaseAgent):
    """Supervisor that routes work to named workers.

    The route() method parses the LLM response for routing directives:
    - "ROUTE:<worker_name>" -> return that worker name
    - "DONE" -> return None (task complete)
    """

    workers: list[str] = field(default_factory=list)

    def route(self, state: AgentState) -> str | None:
        """Decide which worker to hand off to, or None if done."""
        messages = [{"role": "system", "content": self.system_prompt}] + state.messages
        response = self.llm_client.call(messages=messages, tools=[])

        content = response.content.strip()
        if content.upper() == "DONE":
            return None

        if content.upper().startswith("ROUTE:"):
            target = content.split(":", 1)[1].strip()
            if target in self.workers:
                return target
            logger.warning(
                "Supervisor routed to unknown worker %r, available: %s",
                target,
                self.workers,
            )

        logger.warning("Could not parse routing from: %r", content)
        return self.workers[0] if self.workers else None
