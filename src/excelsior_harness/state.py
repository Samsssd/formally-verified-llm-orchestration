"""Agent state management for the orchestration harness.

Inspired by LangGraph's StateGraph approach to explicit state management —
state is treated as a first-class, immutable-friendly data structure that
flows through the orchestration graph.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from excelsior_harness._types import Messages, TerminationReason


class AgentState(BaseModel):
    """Full state of an orchestration run.

    All mutation methods return new copies, keeping the state immutable-friendly.
    The orchestrator loop reassigns the local variable on each step.
    """

    messages: Messages = Field(default_factory=list)
    current_agent: str = ""
    step_count: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    terminated: bool = False
    termination_reason: TerminationReason | None = None
    checkpoints: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> AgentState:
        """Append a message and return a new state."""
        msg: dict[str, Any] = {"role": role, "content": content, **kwargs}
        return self.model_copy(update={"messages": [*self.messages, msg]})

    def record_usage(
        self, *, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> AgentState:
        """Record token usage and cost from one LLM call, increment step."""
        return self.model_copy(
            update={
                "prompt_tokens": self.prompt_tokens + prompt_tokens,
                "completion_tokens": self.completion_tokens + completion_tokens,
                "total_tokens": self.total_tokens + prompt_tokens + completion_tokens,
                "cost_usd": self.cost_usd + cost,
                "step_count": self.step_count + 1,
            }
        )

    def checkpoint(self) -> AgentState:
        """Snapshot current counters into the checkpoints list."""
        snap = {
            "step_count": self.step_count,
            "current_agent": self.current_agent,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "num_messages": len(self.messages),
        }
        return self.model_copy(
            update={"checkpoints": [*self.checkpoints, snap]}
        )

    def terminate(self, reason: TerminationReason) -> AgentState:
        """Mark the run as terminated with a reason."""
        return self.model_copy(
            update={"terminated": True, "termination_reason": reason}
        )
