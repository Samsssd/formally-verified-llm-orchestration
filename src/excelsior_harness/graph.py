"""Lightweight directed-graph router for multi-agent orchestration.

Inspired by LangGraph's StateGraph and conditional edges for explicit,
reproducible control flow. Nodes are agents, edges are transitions
(unconditional or state-conditional). The graph validates its own
structure before execution.

This module is intentionally kept under 150 lines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from excelsior_harness.agents import BaseAgent
from excelsior_harness.state import AgentState

logger = logging.getLogger(__name__)


@dataclass
class _Edge:
    """An edge in the state graph — either unconditional or conditional."""

    target: str | None = None
    condition: Callable[[AgentState], str] | None = None

    def resolve(self, state: AgentState) -> str:
        """Return the target node name for the given state."""
        if self.condition is not None:
            return self.condition(state)
        if self.target is not None:
            return self.target
        raise ValueError("Edge has neither target nor condition")


@dataclass
class StateGraph:
    """Directed graph of agent nodes with conditional routing."""

    _nodes: dict[str, BaseAgent] = field(default_factory=dict)
    _edges: dict[str, list[_Edge]] = field(default_factory=dict)
    _entry_point: str | None = field(default=None)
    _finish_points: set[str] = field(default_factory=set)

    def add_node(self, name: str, agent: BaseAgent) -> None:
        """Register an agent as a named node."""
        self._nodes[name] = agent
        logger.debug("Graph: added node %r", name)

    def get_agent(self, name: str) -> BaseAgent:
        """Look up the agent for a node. Raises KeyError if not found."""
        return self._nodes[name]

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add an unconditional edge between two existing nodes."""
        if from_node not in self._nodes:
            raise ValueError(f"add_edge: unknown node {from_node!r}")
        if to_node not in self._nodes:
            raise ValueError(f"add_edge: unknown node {to_node!r}")
        self._edges.setdefault(from_node, []).append(_Edge(target=to_node))
        logger.debug("Graph: edge %s -> %s", from_node, to_node)

    def add_conditional_edge(
        self, from_node: str, condition: Callable[[AgentState], str]
    ) -> None:
        """Add a conditional edge: condition(state) returns the target node name."""
        if from_node not in self._nodes:
            raise ValueError(f"add_conditional_edge: unknown node {from_node!r}")
        self._edges.setdefault(from_node, []).append(_Edge(condition=condition))
        logger.debug("Graph: conditional edge from %s", from_node)

    def set_entry_point(self, name: str) -> None:
        """Set the starting node for orchestration."""
        self._entry_point = name

    def set_finish_point(self, name: str) -> None:
        """Mark a node as a terminal — routing returns None when reached."""
        self._finish_points.add(name)

    def route(self, state: AgentState) -> str | None:
        """Given current state, return the next node name or None (finished)."""
        current = state.current_agent
        edges = self._edges.get(current, [])

        if not edges:
            if current in self._finish_points:
                return None
            logger.warning("No edges from node %r and not a finish point", current)
            return None

        target = edges[0].resolve(state)
        logger.info("Graph route: %s -> %s", current, target)
        return target

    def validate(self) -> None:
        """Check graph integrity. Raises ValueError on problems."""
        if self._entry_point is None:
            raise ValueError("Graph has no entry point set")
        if self._entry_point not in self._nodes:
            raise ValueError(
                f"Entry point {self._entry_point!r} is not a registered node"
            )
        for from_node, edges in self._edges.items():
            for edge in edges:
                if edge.target is not None and edge.target not in self._nodes:
                    raise ValueError(
                        f"Edge from {from_node!r} references unknown node {edge.target!r}"
                    )
