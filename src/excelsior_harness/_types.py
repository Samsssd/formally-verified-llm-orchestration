"""Shared enums and type aliases for the excelsior-harness.

Centralizes types used across multiple modules to prevent circular imports.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    """Role a given agent plays in the orchestration.

    Inspired by CrewAI-style agent roles for clear separation of concerns
    in multi-agent teams.
    """

    SUPERVISOR = "supervisor"
    WORKER = "worker"
    RESEARCHER = "researcher"
    CODER = "coder"


class TerminationReason(str, Enum):
    """Why the orchestration loop stopped."""

    BUDGET_EXCEEDED = "budget_exceeded"
    MAX_STEPS = "max_steps"
    TASK_COMPLETE = "task_complete"
    ERROR = "error"


class StepType(str, Enum):
    """What happened during a single orchestration step."""

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    ROUTING = "routing"


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Messages = list[dict[str, Any]]
ToolResult = dict[str, Any]  # {"name": str, "result": Any, "error": str | None}
