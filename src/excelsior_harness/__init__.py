"""excelsior-harness: Minimal agent orchestration harness.

Reference implementation for the arXiv paper "Publishing arXiv research
without academic credentials." Implements Option C — a hybrid design
modeled after real patterns from LangGraph, CrewAI, and AutoGen/AG2.

Design Inspirations:
    - State management + graph transitions: LangGraph's StateGraph
    - Role-based multi-agent teams: CrewAI's agent roles
    - Dynamic routing + shared state: AutoGen/AG2 conversational patterns
    - Budget & retry patterns: agenkit and shekel
"""

from excelsior_harness._types import AgentRole, StepType, TerminationReason
from excelsior_harness.agents import (
    BaseAgent,
    MockLLMClient,
    MockResponse,
    SupervisorAgent,
    WorkerAgent,
)
from excelsior_harness.budget import BudgetExceeded, BudgetTracker
from excelsior_harness.context import ContextManager, TokenCounter
from excelsior_harness.graph import StateGraph
from excelsior_harness.orchestrator import Harness
from excelsior_harness.state import AgentState
from excelsior_harness.tools import ToolRegistry, safe_execute

__all__ = [
    "AgentRole",
    "AgentState",
    "BaseAgent",
    "BudgetExceeded",
    "BudgetTracker",
    "ContextManager",
    "Harness",
    "MockLLMClient",
    "MockResponse",
    "StateGraph",
    "StepType",
    "SupervisorAgent",
    "TerminationReason",
    "TokenCounter",
    "ToolRegistry",
    "WorkerAgent",
    "safe_execute",
]
