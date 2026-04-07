"""Main orchestration loop — the heart of the harness.

Modeled after AutoGen/AG2 conversational multi-agent patterns with typed
state transitions. The Harness class runs a deterministic loop:

    while not terminated:
        1. Check budget & step limits
        2. Prepare context (truncate if needed)
        3. Call LLM with current state + available tools
        4. Parse response (tool calls OR final answer)
        5. If tool calls: execute safely, retry on failure, inject results
        6. Update state + log everything
        7. Route to next agent (supervisor decision or graph edge)
        8. Checkpoint state

This is the pseudocode from the spec, implemented exactly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from excelsior_harness._types import StepType, TerminationReason
from excelsior_harness.budget import BudgetExceeded, BudgetTracker
from excelsior_harness.context import ContextManager
from excelsior_harness.graph import StateGraph
from excelsior_harness.state import AgentState
from excelsior_harness.tools import ToolRegistry, safe_execute

logger = logging.getLogger(__name__)


def _execute_with_retry(
    registry: ToolRegistry, tool_name: str, arguments: dict
) -> dict:
    """Execute a tool with exponential backoff + jitter on failure.

    Custom retry pattern drawing from production patterns in minimal
    frameworks like agenkit and shekel.
    """

    @retry(
        wait=wait_exponential(multiplier=1, max=10) + wait_random(0, 2),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _inner() -> dict:
        result = safe_execute(registry, tool_name, arguments)
        if result["error"] is not None:
            raise RuntimeError(result["error"])
        return result

    try:
        return _inner()
    except Exception:
        # All retries exhausted — return the error result
        logger.warning("Tool %s failed after retries", tool_name)
        return safe_execute(registry, tool_name, arguments)


@dataclass
class Harness:
    """Main orchestration engine.

    Wires together the state graph, tool registry, budget tracker, and
    context manager into a single deterministic execution loop.

    Usage::

        harness = Harness(
            graph=graph,
            tool_registry=registry,
            budget_tracker=BudgetTracker(max_budget_usd=5.0),
            context_manager=ContextManager(),
            max_steps=50,
        )
        result = harness.run(AgentState(current_agent="supervisor"))
    """

    graph: StateGraph
    tool_registry: ToolRegistry
    budget_tracker: BudgetTracker
    context_manager: ContextManager
    max_steps: int = 50

    def run(self, initial_state: AgentState) -> AgentState:
        """Execute the orchestration loop until termination.

        Returns the final AgentState with full observability data:
        messages, token counts, costs, checkpoints, and termination reason.
        """
        state = initial_state
        logger.info(
            "Harness starting: agent=%s, max_steps=%d, budget=$%.2f",
            state.current_agent,
            self.max_steps,
            self.budget_tracker.max_budget_usd,
        )

        while not state.terminated:
            # ── 1. Check step limit ──────────────────────────────────
            if state.step_count >= self.max_steps:
                state = state.terminate(TerminationReason.MAX_STEPS)
                logger.info("Terminated: max steps (%d) reached", self.max_steps)
                break

            # ── 2. Prepare context (truncate if needed) ──────────────
            truncated_messages = self.context_manager.prepare(state.messages)
            working_state = state.model_copy(update={"messages": truncated_messages})

            # ── 3. Call LLM with current agent ───────────────────────
            agent = self.graph.get_agent(state.current_agent)
            new_state, step_type = agent.step(working_state, self.tool_registry)

            # ── 4 & 5. Handle tool calls ─────────────────────────────
            if step_type == StepType.TOOL_CALL:
                last_msg = new_state.messages[-1]
                tool_calls = last_msg.get("tool_calls", [])
                for tc in tool_calls:
                    tool_name = tc["name"]
                    arguments = tc.get("arguments", {})
                    logger.info(
                        "Executing tool: %s(%s)", tool_name, arguments
                    )
                    result = _execute_with_retry(
                        self.tool_registry, tool_name, arguments
                    )
                    new_state = new_state.add_message("tool", result)

            # ── 6. Record cost via budget tracker ────────────────────
            # Find the usage from the latest agent step
            tokens_this_step_prompt = (
                new_state.prompt_tokens - state.prompt_tokens
            )
            tokens_this_step_completion = (
                new_state.completion_tokens - state.completion_tokens
            )

            try:
                cost = self.budget_tracker.record(
                    model=agent.model,
                    prompt_tokens=tokens_this_step_prompt,
                    completion_tokens=tokens_this_step_completion,
                )
            except BudgetExceeded:
                state = new_state.terminate(TerminationReason.BUDGET_EXCEEDED)
                logger.info(
                    "Terminated: budget exceeded ($%.4f / $%.4f)",
                    self.budget_tracker.total_cost,
                    self.budget_tracker.max_budget_usd,
                )
                break

            # Update cost in state
            # (agent.step already incremented prompt/completion tokens and step_count,
            #  so we just need to add the USD cost)
            state = new_state.model_copy(
                update={
                    "cost_usd": new_state.cost_usd + cost,
                    # Restore full messages (not truncated)
                    "messages": state.messages
                    + new_state.messages[len(truncated_messages) :],
                }
            )

            # ── Log this step ────────────────────────────────────────
            logger.info(
                "Step %d | agent=%s | type=%s | tokens=%d+%d | cost=$%.4f | total=$%.4f",
                state.step_count,
                state.current_agent,
                step_type.value,
                tokens_this_step_prompt,
                tokens_this_step_completion,
                cost,
                state.cost_usd,
            )

            # ── 7. Route to next agent ───────────────────────────────
            next_agent = self.graph.route(state)
            if next_agent is None:
                state = state.terminate(TerminationReason.TASK_COMPLETE)
                logger.info("Terminated: task complete")
                break
            state = state.model_copy(update={"current_agent": next_agent})

            # ── 8. Checkpoint state ──────────────────────────────────
            state = state.checkpoint()

        # Final summary
        logger.info(
            "Harness finished: steps=%d, tokens=%d, cost=$%.4f, reason=%s",
            state.step_count,
            state.total_tokens,
            state.cost_usd,
            state.termination_reason,
        )
        return state
