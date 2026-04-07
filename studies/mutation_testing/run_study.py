#!/usr/bin/env python3
"""Mutation testing study for excelsior-harness.

Injects 30 realistic bugs across 4 categories, runs pytest against each,
and records which detection methods catch them.

Usage:
    python studies/mutation_testing/run_study.py
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "excelsior_harness"
TESTS = ROOT / "tests"
RESULTS_FILE = Path(__file__).parent / "results.json"


@dataclass
class Mutation:
    id: str
    category: str  # logic | boundary | missing_check | state
    description: str
    file: str  # relative to SRC
    old: str
    new: str
    # Which Lean 4 properties would catch this (by theorem name)
    lean_catches: list[str] = field(default_factory=list)
    lean_detection: bool = False
    # LLM eval analysis
    llm_eval_catches: bool = False
    llm_eval_reason: str = ""


@dataclass
class MutationResult:
    id: str
    category: str
    description: str
    unit_tests_catch: bool = False
    unit_tests_detail: str = ""
    integration_tests_catch: bool = False
    integration_detail: str = ""
    lean_catches: bool = False
    lean_detail: str = ""
    llm_eval_catches: bool = False
    llm_eval_detail: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# MUTATION DEFINITIONS: 30 mutations across 4 categories
# ──────────────────────────────────────────────────────────────────────────────

MUTATIONS: list[Mutation] = [
    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 1: LOGIC ERRORS (8 mutations)
    # ══════════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01",
        category="logic",
        description="record_usage drops completion_tokens from total",
        file="state.py",
        old='"total_tokens": self.total_tokens + prompt_tokens + completion_tokens,',
        new='"total_tokens": self.total_tokens + prompt_tokens,',
        lean_catches=["token_accounting_preserved"],
        lean_detection=True,
    ),
    Mutation(
        id="M02",
        category="logic",
        description="Budget record subtracts cost instead of adding",
        file="budget.py",
        old="self.total_cost += cost",
        new="self.total_cost -= cost",
        lean_catches=["budget_never_exceeded"],
        lean_detection=True,
        llm_eval_catches=True,
        llm_eval_reason="Eval could detect negative costs in output metrics",
    ),
    Mutation(
        id="M03",
        category="logic",
        description="Supervisor route is case-sensitive (misses lowercase 'done')",
        file="agents.py",
        old='if content.upper() == "DONE":',
        new='if content == "DONE":',
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M04",
        category="logic",
        description="Graph resolves LAST edge instead of first",
        file="graph.py",
        old="target = edges[0].resolve(state)",
        new="target = edges[-1].resolve(state)",
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M05",
        category="logic",
        description="Token counter uses 3 instead of 4 for per-message overhead",
        file="context.py",
        old="total += 4  # role + structural overhead",
        new="total += 3  # role + structural overhead",
        lean_catches=[],
        lean_detection=False,
        llm_eval_catches=False,
        llm_eval_reason="Off-by-one in overhead constant not visible to eval",
    ),
    Mutation(
        id="M06",
        category="logic",
        description="BaseAgent swaps prompt and completion token counts",
        file="agents.py",
        old="""        new_state = new_state.record_usage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost=0.0,
        )""",
        new="""        new_state = new_state.record_usage(
            prompt_tokens=response.completion_tokens,
            completion_tokens=response.prompt_tokens,
            cost=0.0,
        )""",
        lean_catches=["token_accounting_preserved"],
        lean_detection=False,
        llm_eval_reason="Total tokens unchanged; prompt/completion swap invisible to eval",
    ),
    Mutation(
        id="M07",
        category="logic",
        description="Budget cost uses prompt_rate for both prompt and completion",
        file="budget.py",
        old="""        cost = (prompt_tokens / 1000) * prompt_rate + (
            completion_tokens / 1000
        ) * completion_rate""",
        new="""        cost = (prompt_tokens / 1000) * prompt_rate + (
            completion_tokens / 1000
        ) * prompt_rate""",
        lean_catches=["budget_never_exceeded"],
        lean_detection=False,
        llm_eval_reason="Subtle pricing error; cost still positive, just wrong amount",
    ),
    Mutation(
        id="M08",
        category="logic",
        description="Orchestrator computes token delta from wrong base",
        file="orchestrator.py",
        old="""            tokens_this_step_prompt = (
                new_state.prompt_tokens - state.prompt_tokens
            )
            tokens_this_step_completion = (
                new_state.completion_tokens - state.completion_tokens
            )""",
        new="""            tokens_this_step_prompt = (
                new_state.prompt_tokens
            )
            tokens_this_step_completion = (
                new_state.completion_tokens
            )""",
        lean_catches=[],
        lean_detection=False,
        llm_eval_reason="Absolute tokens instead of delta; inflates cost but still runs",
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 2: BOUNDARY ERRORS (8 mutations)
    # ══════════════════════════════════════════════════════════════════════════
    Mutation(
        id="M09",
        category="boundary",
        description="Off-by-one: step_count > max_steps (allows one extra step)",
        file="orchestrator.py",
        old="if state.step_count >= self.max_steps:",
        new="if state.step_count > self.max_steps:",
        lean_catches=["steps_bounded", "bounded_termination"],
        lean_detection=True,
    ),
    Mutation(
        id="M10",
        category="boundary",
        description="Budget check >= instead of > (triggers one call too early)",
        file="budget.py",
        old="if self.total_cost > self.max_budget_usd:",
        new="if self.total_cost >= self.max_budget_usd:",
        lean_catches=["budget_never_exceeded"],
        lean_detection=True,
    ),
    Mutation(
        id="M11",
        category="boundary",
        description="Context keeps keep_recent-1 messages (drops one recent)",
        file="context.py",
        old="recent = messages[-self.keep_recent :] if self.keep_recent else []",
        new="recent = messages[-self.keep_recent + 1 :] if self.keep_recent else []",
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M12",
        category="boundary",
        description="Context uses < instead of <= (unnecessary truncation at exact limit)",
        file="context.py",
        old="if total <= self.max_context_tokens:",
        new="if total < self.max_context_tokens:",
        lean_catches=["context_buffer_bounded_no_truncation"],
        lean_detection=True,
    ),
    Mutation(
        id="M13",
        category="boundary",
        description="Budget divides by 100 instead of 1000 (10x cost inflation)",
        file="budget.py",
        old="cost = (prompt_tokens / 1000) * prompt_rate + (",
        new="cost = (prompt_tokens / 100) * prompt_rate + (",
        lean_catches=["budget_never_exceeded"],
        lean_detection=False,
        llm_eval_catches=True,
        llm_eval_reason="Dramatic cost inflation could be caught by cost reasonableness check",
    ),
    Mutation(
        id="M14",
        category="boundary",
        description="record_usage doesn't increment step_count",
        file="state.py",
        old='"step_count": self.step_count + 1,',
        new='"step_count": self.step_count,',
        lean_catches=["audit_log_complete"],
        lean_detection=True,
    ),
    Mutation(
        id="M15",
        category="boundary",
        description="MockLLMClient uses max instead of min (index out of bounds)",
        file="agents.py",
        old="resp = self.responses[min(self._index, len(self.responses) - 1)]",
        new="resp = self.responses[max(self._index, len(self.responses) - 1)]",
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M16",
        category="boundary",
        description="Message restoration adds extra message (off-by-one in slice)",
        file="orchestrator.py",
        old='+ new_state.messages[len(truncated_messages) :]',
        new='+ new_state.messages[len(truncated_messages) - 1 :]',
        lean_catches=[],
        lean_detection=False,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 3: MISSING CHECKS (8 mutations)
    # ══════════════════════════════════════════════════════════════════════════
    Mutation(
        id="M17",
        category="missing_check",
        description="safe_execute skips registry lookup, calls eval() on tool name",
        file="tools.py",
        old="""    try:
        defn = registry.get(tool_name)
        result = defn.callable(**arguments)""",
        new="""    try:
        defn = registry.get(tool_name) if tool_name in registry else None
        result = defn.callable(**arguments) if defn else str(arguments)""",
        lean_catches=["tool_access_control"],
        lean_detection=True,
    ),
    Mutation(
        id="M18",
        category="missing_check",
        description="Budget record removes the exceeded check entirely",
        file="budget.py",
        old="""        if self.total_cost > self.max_budget_usd:
            raise BudgetExceeded(self.total_cost, self.max_budget_usd)
        return cost""",
        new="""        return cost""",
        lean_catches=["budget_never_exceeded", "budget_never_exceeded_multi"],
        lean_detection=True,
    ),
    Mutation(
        id="M19",
        category="missing_check",
        description="Graph validate skips entry point check",
        file="graph.py",
        old="""    def validate(self) -> None:
        \"\"\"Check graph integrity. Raises ValueError on problems.\"\"\"
        if self._entry_point is None:
            raise ValueError("Graph has no entry point set")
        if self._entry_point not in self._nodes:
            raise ValueError(
                f"Entry point {self._entry_point!r} is not a registered node"
            )""",
        new="""    def validate(self) -> None:
        \"\"\"Check graph integrity. Raises ValueError on problems.\"\"\"
        pass  # skip entry point validation""",
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M20",
        category="missing_check",
        description="terminate() doesn't set terminated=True",
        file="state.py",
        old='update={"terminated": True, "termination_reason": reason}',
        new='update={"terminated": False, "termination_reason": reason}',
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M21",
        category="missing_check",
        description="Orchestrator skips context truncation entirely",
        file="orchestrator.py",
        old="""            # ── 2. Prepare context (truncate if needed) ──────────────
            truncated_messages = self.context_manager.prepare(state.messages)
            working_state = state.model_copy(update={"messages": truncated_messages})""",
        new="""            # ── 2. Prepare context (truncate if needed) ──────────────
            truncated_messages = state.messages
            working_state = state""",
        lean_catches=["context_buffer_bounded_no_truncation"],
        lean_detection=True,
    ),
    Mutation(
        id="M22",
        category="missing_check",
        description="BaseAgent doesn't filter tools by allowed_tools",
        file="agents.py",
        old="""        agent_tools = (
            [s for s in all_schemas if s["function"]["name"] in self.allowed_tools]
            if self.allowed_tools
            else all_schemas
        )""",
        new="""        agent_tools = all_schemas  # skip allowed_tools filter""",
        lean_catches=["tool_access_control"],
        lean_detection=True,
    ),
    Mutation(
        id="M23",
        category="missing_check",
        description="add_edge removes target node existence check",
        file="graph.py",
        old="""        if to_node not in self._nodes:
            raise ValueError(f"add_edge: unknown node {to_node!r}")""",
        new="""        pass  # skip to_node validation""",
        lean_catches=[],
        lean_detection=False,
    ),
    Mutation(
        id="M24",
        category="missing_check",
        description="safe_execute doesn't catch exceptions (crashes on tool error)",
        file="tools.py",
        old="""    except Exception as exc:
        logger.warning("Tool %s failed: %s", tool_name, exc)
        return {"name": tool_name, "result": None, "error": str(exc)}""",
        new="""    except Exception as exc:
        raise  # propagate instead of catching""",
        lean_catches=[],
        lean_detection=False,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 4: STATE / CONCURRENCY ISSUES (6 mutations)
    # ══════════════════════════════════════════════════════════════════════════
    Mutation(
        id="M25",
        category="state",
        description="add_message mutates messages list in-place instead of copy",
        file="state.py",
        old="""    def add_message(self, role: str, content: str, **kwargs: Any) -> AgentState:
        \"\"\"Append a message and return a new state.\"\"\"
        msg: dict[str, Any] = {"role": role, "content": content, **kwargs}
        return self.model_copy(update={"messages": [*self.messages, msg]})""",
        new="""    def add_message(self, role: str, content: str, **kwargs: Any) -> AgentState:
        \"\"\"Append a message and return a new state.\"\"\"
        msg: dict[str, Any] = {"role": role, "content": content, **kwargs}
        self.messages.append(msg)
        return self""",
        lean_catches=[],
        lean_detection=False,
        llm_eval_reason="Shared mutable state causes cross-agent message leakage",
    ),
    Mutation(
        id="M26",
        category="state",
        description="record_usage returns self instead of new copy",
        file="state.py",
        old="""    def record_usage(
        self, *, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> AgentState:
        \"\"\"Record token usage and cost from one LLM call, increment step.\"\"\"
        return self.model_copy(
            update={
                "prompt_tokens": self.prompt_tokens + prompt_tokens,
                "completion_tokens": self.completion_tokens + completion_tokens,
                "total_tokens": self.total_tokens + prompt_tokens + completion_tokens,
                "cost_usd": self.cost_usd + cost,
                "step_count": self.step_count + 1,
            }
        )""",
        new="""    def record_usage(
        self, *, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> AgentState:
        \"\"\"Record token usage and cost from one LLM call, increment step.\"\"\"
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.cost_usd += cost
        self.step_count += 1
        return self""",
        lean_catches=["token_accounting_preserved"],
        lean_detection=False,
        llm_eval_reason="In-place mutation breaks state isolation between checkpoints",
    ),
    Mutation(
        id="M27",
        category="state",
        description="Orchestrator skips checkpoint after routing",
        file="orchestrator.py",
        old="""            # ── 8. Checkpoint state ──────────────────────────────────
            state = state.checkpoint()""",
        new="""            # ── 8. Checkpoint state ──────────────────────────────────
            pass  # skip checkpoint""",
        lean_catches=["audit_log_complete", "audit_log_grows"],
        lean_detection=True,
    ),
    Mutation(
        id="M28",
        category="state",
        description="checkpoint overwrites instead of appending",
        file="state.py",
        old="""        return self.model_copy(
            update={"checkpoints": [*self.checkpoints, snap]}
        )""",
        new="""        return self.model_copy(
            update={"checkpoints": [snap]}
        )""",
        lean_catches=["audit_log_grows", "audit_log_complete"],
        lean_detection=True,
    ),
    Mutation(
        id="M29",
        category="state",
        description="Orchestrator records budget cost twice",
        file="orchestrator.py",
        old="""            # Update cost in state
            # (agent.step already incremented prompt/completion tokens and step_count,
            #  so we just need to add the USD cost)
            state = new_state.model_copy(
                update={
                    "cost_usd": new_state.cost_usd + cost,""",
        new="""            # Update cost in state
            # (agent.step already incremented prompt/completion tokens and step_count,
            #  so we just need to add the USD cost)
            state = new_state.model_copy(
                update={
                    "cost_usd": new_state.cost_usd + cost + cost,""",
        lean_catches=[],
        lean_detection=False,
        llm_eval_catches=True,
        llm_eval_reason="Double-charged cost visible in output metrics",
    ),
    Mutation(
        id="M30",
        category="state",
        description="WorkerAgent doesn't restore original system_prompt",
        file="agents.py",
        old="""        original_prompt = self.system_prompt
        self.system_prompt = f"{original_prompt}\\n\\nYour current task: {self.task}"
        result = super().step(state, tool_registry)
        self.system_prompt = original_prompt
        return result""",
        new="""        self.system_prompt = f"{self.system_prompt}\\n\\nYour current task: {self.task}"
        result = super().step(state, tool_registry)
        return result""",
        lean_catches=[],
        lean_detection=False,
        llm_eval_reason="Prompt grows on each call; subtle degradation over multi-step runs",
    ),
]


def apply_mutation(mutation: Mutation) -> str:
    """Apply mutation to source file. Returns original content for rollback."""
    filepath = SRC / mutation.file
    original = filepath.read_text()
    if mutation.old not in original:
        raise ValueError(
            f"[{mutation.id}] Old text not found in {mutation.file}:\n"
            f"  Looking for: {mutation.old[:80]!r}..."
        )
    mutated = original.replace(mutation.old, mutation.new, 1)
    filepath.write_text(mutated)
    return original


def revert_mutation(mutation: Mutation, original: str) -> None:
    """Restore original file content."""
    filepath = SRC / mutation.file
    filepath.write_text(original)


def run_tests(test_type: str) -> tuple[bool, str]:
    """Run pytest and return (all_passed, detail_string).

    test_type: 'unit' runs all test_*.py except test_integration.py
               'integration' runs only test_integration.py
    """
    if test_type == "unit":
        # Run all individual module tests (not integration)
        cmd = [
            sys.executable, "-m", "pytest",
            str(TESTS / "test_state.py"),
            str(TESTS / "test_context.py"),
            str(TESTS / "test_budget.py"),
            str(TESTS / "test_tools.py"),
            str(TESTS / "test_agents.py"),
            str(TESTS / "test_graph.py"),
            str(TESTS / "test_orchestrator.py"),
            "-v", "--tb=line", "--no-header", "-q",
        ]
    else:
        cmd = [
            sys.executable, "-m", "pytest",
            str(TESTS / "test_integration.py"),
            "-v", "--tb=line", "--no-header", "-q",
        ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
        cwd=str(ROOT),
    )
    passed = result.returncode == 0
    # Extract failure summary
    output = result.stdout + result.stderr
    # Find failed test names
    failed_tests = []
    for line in output.splitlines():
        if "FAILED" in line:
            failed_tests.append(line.strip())

    detail = "all passed" if passed else "; ".join(failed_tests[:5])
    return passed, detail


def run_single_mutation(mutation: Mutation) -> MutationResult:
    """Apply one mutation, run all test suites, record results."""
    result = MutationResult(
        id=mutation.id,
        category=mutation.category,
        description=mutation.description,
        lean_catches=mutation.lean_detection,
        lean_detail=", ".join(mutation.lean_catches) if mutation.lean_catches else "no property models this",
        llm_eval_catches=mutation.llm_eval_catches,
        llm_eval_detail=mutation.llm_eval_reason or "not detectable by output-level eval",
    )

    try:
        original = apply_mutation(mutation)
    except ValueError as e:
        print(f"  SKIP: {e}")
        result.unit_tests_detail = "SKIP: mutation text not found"
        result.integration_detail = "SKIP: mutation text not found"
        return result

    try:
        # Run unit tests
        unit_passed, unit_detail = run_tests("unit")
        result.unit_tests_catch = not unit_passed
        result.unit_tests_detail = unit_detail

        # Run integration tests
        integ_passed, integ_detail = run_tests("integration")
        result.integration_tests_catch = not integ_passed
        result.integration_detail = integ_detail

    except subprocess.TimeoutExpired:
        result.unit_tests_detail = "TIMEOUT"
        result.integration_detail = "TIMEOUT"
    finally:
        revert_mutation(mutation, original)

    return result


def main():
    print("=" * 78)
    print("MUTATION TESTING STUDY — excelsior-harness")
    print(f"Total mutations: {len(MUTATIONS)}")
    print("=" * 78)

    # Verify baseline passes first
    print("\n[Baseline] Running tests on unmutated code...")
    unit_ok, _ = run_tests("unit")
    integ_ok, _ = run_tests("integration")
    if not unit_ok or not integ_ok:
        print("ERROR: Baseline tests fail! Fix before running mutation study.")
        sys.exit(1)
    print("[Baseline] All tests pass. Starting mutations...\n")

    results: list[dict] = []
    for i, mutation in enumerate(MUTATIONS, 1):
        print(f"[{i:2d}/{len(MUTATIONS)}] {mutation.id}: {mutation.description}")
        t0 = time.time()
        result = run_single_mutation(mutation)
        elapsed = time.time() - t0

        caught_by = []
        if result.unit_tests_catch:
            caught_by.append("unit")
        if result.integration_tests_catch:
            caught_by.append("integ")
        if result.lean_catches:
            caught_by.append("lean4")
        if result.llm_eval_catches:
            caught_by.append("eval")

        status = f"  caught_by=[{', '.join(caught_by) or 'NONE'}] ({elapsed:.1f}s)"
        print(status)
        results.append(asdict(result))

    # Save raw results
    RESULTS_FILE.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {RESULTS_FILE}")

    # Print summary table
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'ID':<5} {'Category':<14} {'Unit':>5} {'Integ':>6} {'Lean4':>6} {'Eval':>5} {'Description'}")
    print("-" * 78)
    for r in results:
        u = "✓" if r["unit_tests_catch"] else "✗"
        i = "✓" if r["integration_tests_catch"] else "✗"
        l = "✓" if r["lean_catches"] else "✗"
        e = "✓" if r["llm_eval_catches"] else "✗"
        print(f"{r['id']:<5} {r['category']:<14} {u:>5} {i:>6} {l:>6} {e:>5} {r['description'][:40]}")

    # Category-level statistics
    print("\n" + "=" * 78)
    print("DETECTION RATES BY CATEGORY")
    print("=" * 78)
    categories = ["logic", "boundary", "missing_check", "state"]
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        n = len(cat_results)
        if n == 0:
            continue
        u_rate = sum(1 for r in cat_results if r["unit_tests_catch"]) / n
        i_rate = sum(1 for r in cat_results if r["integration_tests_catch"]) / n
        l_rate = sum(1 for r in cat_results if r["lean_catches"]) / n
        e_rate = sum(1 for r in cat_results if r["llm_eval_catches"]) / n
        print(f"{cat:<14}  unit={u_rate:.0%}  integ={i_rate:.0%}  lean4={l_rate:.0%}  eval={e_rate:.0%}  (n={n})")

    # Overall
    n = len(results)
    u_total = sum(1 for r in results if r["unit_tests_catch"]) / n
    i_total = sum(1 for r in results if r["integration_tests_catch"]) / n
    l_total = sum(1 for r in results if r["lean_catches"]) / n
    e_total = sum(1 for r in results if r["llm_eval_catches"]) / n
    print(f"{'OVERALL':<14}  unit={u_total:.0%}  integ={i_total:.0%}  lean4={l_total:.0%}  eval={e_total:.0%}  (n={n})")


if __name__ == "__main__":
    main()
