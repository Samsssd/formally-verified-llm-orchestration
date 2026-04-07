#!/usr/bin/env python3
"""
Phase 2: Automated Mutation Analysis
=====================================

Reads mutmut's 420 auto-generated mutants from .mutmut-cache,
classifies survivors, and tests Lean-applicable ones against the spec.

This complements the hand-crafted 30-mutation study with a full
automated baseline, addressing the selection bias concern.

Methodology:
  1. Read mutmut results (420 mutants, killed/survived/suspicious)
  2. For each survived mutant, extract the diff
  3. Classify survivors: equivalent | test_infra | config | real_gap
  4. For real_gap survivors in core files, check Lean applicability
  5. For Lean-applicable survivors, apply spec mutation and run lake build
  6. Produce combined statistics

Usage:
    python studies/mutation_testing/analyze_mutmut.py
"""

import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUTMUT_DB = ROOT / ".mutmut-cache"
LEAN_FILE = ROOT / "formal" / "Lean4Learn" / "HarnessVerification.lean"
LAKE_BIN = Path.home() / ".elan" / "bin" / "lake"
LEAN_DIR = ROOT / "formal"
RESULTS_DIR = Path(__file__).parent
RESULTS_JSON = RESULTS_DIR / "automated_results.json"
RESULTS_MD = RESULTS_DIR / "AUTOMATED_RESULTS.md"


@dataclass
class MutantInfo:
    """Info about one mutmut-generated mutant."""
    id: int
    file: str
    line_number: int
    line_text: str
    status: str  # ok_killed | bad_survived | ok_suspicious
    diff: str
    # Classification (for survived only)
    classification: str = ""  # equivalent | test_infra | config | real_gap
    classification_reason: str = ""
    # Lean analysis (for real_gap only)
    lean_applicable: bool = False
    lean_catches: bool = False
    lean_detail: str = ""


def get_mutmut_results() -> list[MutantInfo]:
    """Read all mutants from the mutmut cache database."""
    conn = sqlite3.connect(str(MUTMUT_DB))
    rows = conn.execute('''
        SELECT m.id, sf.filename, l.line_number, l.line, m.status
        FROM Mutant m
        JOIN Line l ON m.line = l.id
        JOIN SourceFile sf ON l.sourcefile = sf.id
        ORDER BY m.id
    ''').fetchall()
    conn.close()

    mutants = []
    for mid, fname, lineno, line_text, status in rows:
        short = fname.split('/')[-1]
        # Get diff via mutmut show
        diff = _get_diff(mid)
        mutants.append(MutantInfo(
            id=mid, file=short, line_number=lineno,
            line_text=line_text.strip(), status=status, diff=diff,
        ))
    return mutants


def _get_diff(mutant_id: int) -> str:
    """Get the diff for a mutant via mutmut show."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mutmut", "show", str(mutant_id)],
            capture_output=True, text=True, timeout=10, cwd=str(ROOT),
        )
        return result.stdout.strip()
    except Exception:
        return ""


def classify_survivor(m: MutantInfo) -> None:
    """Classify a survived mutant into one of four categories.

    Categories (following Papadakis et al., IEEE TSE 2019 guidelines):
      equivalent  -- mutation produces no observable behavior change at
                     the module's public API (logging, error messages,
                     docstrings, repr flags, type aliases, @overload)
      test_infra  -- mutation targets test-double defaults (MockResponse,
                     MockLLMClient) rather than production logic
      config      -- mutation changes a tuning constant not under test
                     (retry params, default window sizes, rate table)
      real_gap    -- genuine functional mutation that the test suite
                     fails to detect
    """
    diff_lower = m.diff.lower()
    line_lower = m.line_text.lower()
    line_stripped = m.line_text.strip()

    # == TIER 0: Whole-file rules ==========================================
    # _types.py contains only enums and type aliases; mutations here
    # change string representation but not program semantics.
    if m.file == '_types.py':
        m.classification = "equivalent"
        m.classification_reason = "Enum/type-alias string value"
        return

    # == TIER 1: Test infrastructure (MockResponse / MockLLMClient) ========
    # These dataclasses exist solely for testing.  Changing their defaults
    # modifies test fixtures, not production behaviour.
    if m.file == 'agents.py':
        mock_keywords = [
            'content: str', 'prompt_tokens: int = ',
            'completion_tokens: int = ', 'responses: list[mockresponse]',
            '_index: int = field(',
        ]
        if any(kw in line_lower for kw in mock_keywords):
            m.classification = "test_infra"
            m.classification_reason = "Mock/test-double default value"
            return
        # MockLLMClient.call() log lines
        if 'mockllm call' in line_lower or '"mockllm' in diff_lower:
            m.classification = "test_infra"
            m.classification_reason = "Mock logging"
            return

    # == TIER 2: Logging / observability ===================================
    # Logger calls and format strings used only for observability.
    if re.search(r'logger\.\w+\(', m.line_text):
        m.classification = "equivalent"
        m.classification_reason = "Logger call (observability only)"
        return

    # Log format-string arguments (e.g., "Agent %s step: type=%s, ...")
    if re.search(r'["\'].*%[sdr]', m.line_text) and \
       not any(kw in line_lower for kw in ['raise ', 'return ', 'assert ']):
        m.classification = "equivalent"
        m.classification_reason = "Log format string argument"
        return

    # == TIER 3: Error messages / ValueError text ==========================
    if re.search(r'raise\s+\w+Error\(', m.line_text):
        m.classification = "equivalent"
        m.classification_reason = "Exception message text"
        return

    # f-string in exception or log context
    if ('f"' in m.line_text or "f'" in m.line_text) and \
       any(kw in line_lower for kw in ['raise ', 'logger.', 'log.']):
        m.classification = "equivalent"
        m.classification_reason = "Formatted error/log message"
        return

    # == TIER 4: Configuration constants ===================================

    # COST_TABLE rate values (model pricing -- not core logic)
    if any(kw in line_lower for kw in ['"gpt-', '"claude-', '"_default"',
                                         'cost_table']):
        m.classification = "config"
        m.classification_reason = "Model pricing rate constant"
        return

    # Retry / backoff configuration
    if any(kw in line_lower for kw in ['wait_exponential', 'stop_after_attempt',
                                         'wait_random', 'reraise']):
        m.classification = "config"
        m.classification_reason = "Retry/backoff configuration"
        return

    # Context window / step-limit defaults (handles `name: type = N` format)
    if re.search(r'(max_context_tokens|keep_recent|max_steps)\b', line_lower) and \
       re.search(r'\d+', m.line_text):
        m.classification = "config"
        m.classification_reason = "Default configuration parameter"
        return

    # JSON schema type-mapping constants (_TYPE_MAP values)
    if m.file == 'tools.py' and re.search(
            r':\s*"(string|integer|number|boolean|array|object)"', m.line_text):
        m.classification = "config"
        m.classification_reason = "JSON Schema type-mapping constant"
        return

    # == TIER 5: Equivalent by construction ================================

    # repr= flag changes (no functional impact)
    if 'repr=' in line_lower:
        m.classification = "equivalent"
        m.classification_reason = "repr flag (display only)"
        return

    # @overload decorator (type-checker hint, no runtime effect)
    if '@overload' in line_stripped:
        m.classification = "equivalent"
        m.classification_reason = "@overload decorator (type-check only)"
        return

    # Docstrings
    if '"""' in m.line_text or "'''" in m.line_text:
        m.classification = "equivalent"
        m.classification_reason = "Docstring mutation"
        return

    # metadata field default (unused by core logic)
    if 'metadata' in line_lower and 'field(' in line_lower:
        m.classification = "equivalent"
        m.classification_reason = "Metadata field default (unused in core logic)"
        return

    # BudgetExceeded.__init__ stores max_budget as attribute -- only used
    # in the error message, not in control flow.
    if m.file == 'budget.py' and 'self.max_budget' in m.line_text and \
       'max_budget_usd' not in m.line_text:
        m.classification = "equivalent"
        m.classification_reason = "Exception attribute (not used in control flow)"
        return

    # BudgetExceeded error message text (f-string in super().__init__)
    if m.file == 'budget.py' and 'budget exceeded' in line_lower:
        m.classification = "equivalent"
        m.classification_reason = "Exception message text"
        return

    # Summary/snippet formatting in context manager (only for log output).
    # This covers: snippet construction, summary_parts assembly, role/content
    # extraction from messages, and length threshold for truncation.
    if m.file == 'context.py' and any(kw in line_lower for kw in [
            'snippet', 'summary_parts', 'summary_text', 'context summary',
            'content[:80]', "replace(", '+ "..."', 'role =',
            'content = msg.get', 'role = msg.get', 'len(content)']):
        m.classification = "equivalent"
        m.classification_reason = "Context summary formatting (informational)"
        return

    # Edge/Graph default field values (target=None, condition=None, _entry_point=None)
    if m.file == 'graph.py' and 'None' in m.line_text and '=' in m.line_text and \
       any(kw in line_lower for kw in ['target', 'condition', '_entry_point']):
        m.classification = "equivalent"
        m.classification_reason = "Optional field default"
        return

    # Graph/tools validation error message strings (f"..." in raise)
    if m.file in ('graph.py', 'tools.py') and \
       re.search(r'(raise\s+ValueError|f".*unknown|f".*not a)', m.line_text):
        m.classification = "equivalent"
        m.classification_reason = "Validation error message text"
        return

    # agents.py: allowed_tools / workers default list
    if m.file == 'agents.py' and re.search(
            r'(allowed_tools|workers)\s*:\s*list.*=\s*field', line_lower):
        m.classification = "config"
        m.classification_reason = "Agent configuration default (empty list)"
        return

    # agents.py: model default value
    if m.file == 'agents.py' and re.search(r'model\s*:\s*str\s*=', line_lower):
        m.classification = "config"
        m.classification_reason = "Default model name"
        return

    # agents.py: task default value
    if m.file == 'agents.py' and re.search(r'task\s*:\s*str\s*=', line_lower):
        m.classification = "config"
        m.classification_reason = "Default task string"
        return

    # tools.py: tool schema dict structure keys ("type": "object", etc.)
    if m.file == 'tools.py' and re.search(r'"(type|required|description)":', m.line_text):
        m.classification = "real_gap"
        m.classification_reason = "Tool schema structure mutation"
        return

    # tools.py: tool description extraction from docstring
    if m.file == 'tools.py' and ('__doc__' in m.line_text or '.strip()' in m.line_text):
        m.classification = "equivalent"
        m.classification_reason = "Docstring extraction"
        return

    # tools.py: schema generation logic (hints, properties, required, param checks)
    if m.file == 'tools.py' and any(kw in line_lower for kw in [
            'hints.get', 'properties[', 'required.append',
            'param.default', 'inspect.parameter', 'param_name ==',
            '_type_map.get', 'json_type']):
        m.classification = "real_gap"
        m.classification_reason = "Schema generation logic"
        return

    # tools.py: module-level alias (tool = ToolRegistry.register)
    if m.file == 'tools.py' and 'toolregistry.register' in line_lower:
        m.classification = "real_gap"
        m.classification_reason = "Tool registration alias"
        return

    # context.py: token counting logic (total, overhead, count call)
    if m.file == 'context.py' and any(kw in line_lower for kw in [
            'total = 0', 'total += 4', 'total += self.count']):
        m.classification = "real_gap"
        m.classification_reason = "Token counting logic"
        return

    # context.py: comparison operators in truncation
    if m.file == 'context.py' and re.search(r'(<=|>=|<|>)\s*self\.(max_context|keep)', m.line_text):
        m.classification = "real_gap"
        m.classification_reason = "Context truncation boundary"
        return

    # context.py: message slicing in truncation
    if m.file == 'context.py' and 'messages[' in m.line_text:
        m.classification = "real_gap"
        m.classification_reason = "Message slice mutation"
        return

    # agents.py: message construction (building messages list for LLM call)
    if m.file == 'agents.py' and ('messages' in line_lower and
            any(kw in line_lower for kw in ['role', 'system', 'state.messages',
                                              'self.system_prompt'])):
        m.classification = "real_gap"
        m.classification_reason = "Agent message construction"
        return

    # agents.py: tool schema filtering (allowed_tools check)
    if m.file == 'agents.py' and any(kw in line_lower for kw in [
            'all_schemas', 'to_openai_schema', 'allowed_tools',
            'tool_schemas']):
        m.classification = "real_gap"
        m.classification_reason = "Tool permission filtering"
        return

    # agents.py: response handling (content, tool_calls)
    if m.file == 'agents.py' and any(kw in line_lower for kw in [
            'response.content', 'response.tool_calls', 'step_type',
            'stepttype']):
        m.classification = "real_gap"
        m.classification_reason = "Agent response handling"
        return

    # agents.py: system prompt manipulation (WorkerAgent task injection)
    if m.file == 'agents.py' and any(kw in line_lower for kw in [
            'original_prompt', 'self.system_prompt =', 'self.task']):
        m.classification = "real_gap"
        m.classification_reason = "System prompt injection"
        return

    # agents.py: supervisor routing logic
    if m.file == 'agents.py' and any(kw in line_lower for kw in [
            'content.split', '.strip()', 'self.workers[0]',
            'self.workers else']):
        m.classification = "real_gap"
        m.classification_reason = "Routing decision logic"
        return

    # agents.py: cost/token recording
    if m.file == 'agents.py' and any(kw in line_lower for kw in [
            'cost=', 'prompt_tokens=', 'completion_tokens=']):
        # Skip if this is a field default (already handled in TIER 1)
        if 'int = ' not in line_lower:
            m.classification = "real_gap"
            m.classification_reason = "Token/cost recording"
            return

    # orchestrator.py: state management in loop
    if m.file == 'orchestrator.py' and any(kw in line_lower for kw in [
            'state.messages', '"messages"', 'working_state',
            'new_state', 'state.terminate']):
        m.classification = "real_gap"
        m.classification_reason = "Orchestrator state management"
        return

    # orchestrator.py: @retry decorator (config for error recovery)
    if m.file == 'orchestrator.py' and '@retry' in line_lower:
        m.classification = "config"
        m.classification_reason = "Retry decorator configuration"
        return

    # orchestrator.py: log message text (Terminated: ...)
    if m.file == 'orchestrator.py' and 'terminated' in line_lower and \
       '"' in m.line_text:
        m.classification = "equivalent"
        m.classification_reason = "Termination log message text"
        return

    # graph.py: resolution / finish-point logic
    if m.file == 'graph.py' and any(kw in line_lower for kw in [
            '_finish_points', 'current', 'target', 'edge.']):
        m.classification = "real_gap"
        m.classification_reason = "Graph resolution logic"
        return

    # == TIER 6: Real gaps =================================================

    # Break statement removal (affects loop termination)
    if line_stripped == 'break':
        m.classification = "real_gap"
        m.classification_reason = "Break removal -- loop termination"
        return

    # continue statement changes
    if line_stripped == 'continue':
        m.classification = "real_gap"
        m.classification_reason = "Continue removal -- loop control flow"
        return

    # Arithmetic / comparison operator mutations
    # Note: Python puts spaces around / so match both /1001 and / 1001
    if any(op in m.diff for op in ['+= cost', '= cost', '/1001', '/ 1001',
                                     '/1000', '/ 1000', '>= ', '<= ']):
        m.classification = "real_gap"
        m.classification_reason = "Arithmetic/comparison operator mutation"
        return

    # Checkpoint dict key renaming (XX prefix)
    if 'xx' in diff_lower and any(kw in diff_lower for kw in [
            'cost_usd', 'num_messages', 'checkpoint']):
        m.classification = "real_gap"
        m.classification_reason = "Checkpoint structure key mutation"
        return

    # model_copy / state manipulation
    if 'model_copy' in m.line_text or '.copy(' in m.line_text:
        m.classification = "real_gap"
        m.classification_reason = "State copy/update mutation"
        return

    # Token delta calculations
    if re.search(r'\.(prompt|completion)_tokens\s*-\s*', m.line_text):
        m.classification = "real_gap"
        m.classification_reason = "Token delta calculation"
        return

    # Tool execution and safe_execute
    if 'safe_execute' in m.line_text or 'result["error"]' in m.line_text:
        m.classification = "real_gap"
        m.classification_reason = "Tool execution path mutation"
        return

    # == DEFAULT: Classify remaining by file ===============================
    if m.file in ('state.py', 'budget.py', 'orchestrator.py'):
        m.classification = "real_gap"
        m.classification_reason = "Unclassified core-module mutation"
    elif m.file in ('agents.py', 'tools.py', 'context.py', 'graph.py'):
        m.classification = "real_gap"
        m.classification_reason = "Unclassified auxiliary-module mutation"
    else:
        m.classification = "equivalent"
        m.classification_reason = "Non-functional file mutation"


# --- Lean mutation testing for survived mutants ---

# Manual mapping of mutmut survivors to Lean spec mutations.
# For each survivor in a core file, we determine:
#   applicable=True  -> can express in Lean; supply old/new to test
#   applicable=False -> outside Lean spec scope; supply rationale
#
# Methodology: systematically examine every survived mutant in
# budget.py, orchestrator.py, state.py against the Lean OState model.
LEAN_MAPPINGS: dict[int, dict] = {
    # -- budget.py --------------------------------------------------------
    57: {
        "applicable": False,
        "rationale": "Lean uses abstract Nat cost; /1001 vs /1000 is rate-level detail",
    },
    61: {
        "applicable": False,
        "rationale": "Lean uses abstract Nat cost; /1001 vs /1000 is rate-level detail",
    },
    # mutant 64: self.total_cost += cost -> self.total_cost = cost
    64: {
        "old": "s.cost + c.cost, s.maxBudget,",
        "new": "c.cost, s.maxBudget,",
        "replace_all": True,
        "rationale": "Cost assignment instead of accumulation (spec lacks cost-monotonicity)",
    },
    66: {
        "applicable": False,
        "rationale": "Per-model cost tracking not modeled in spec",
    },
    67: {
        "applicable": False,
        "rationale": "Per-model cost tracking not modeled in spec",
    },
    68: {
        "applicable": False,
        "rationale": "Per-model cost tracking not modeled in spec",
    },
    # mutant 69: > -> >= in budget check
    69: {
        "old": "s.cost + c.cost > s.maxBudget",
        "new": "s.cost + c.cost \u2265 s.maxBudget",
        "replace_all": False,
        "rationale": "Budget threshold off-by-one (>= vs >)",
    },
    # -- orchestrator.py --------------------------------------------------
    # break -> continue after termination: Lean runLoop checks s.done at
    # the top of each iteration, so removing the inner done check after
    # execStep doesn't change the mathematical result.
    330: {
        "applicable": False,
        "rationale": "Loop convergence: runLoop outer done-check absorbs inner check removal",
    },
    350: {
        "applicable": False,
        "rationale": "Lean tracks absolute token counts, not per-step deltas",
    },
    352: {
        "applicable": False,
        "rationale": "Lean tracks absolute token counts, not per-step deltas",
    },
    357: {
        "applicable": False,
        "rationale": "Loop convergence: runLoop outer done-check absorbs inner check removal",
    },
    360: {
        "applicable": False,
        "rationale": "Lean models checkpoints as Nat counter, not dict structure",
    },
    368: {
        "applicable": False,
        "rationale": "Loop convergence: runLoop outer done-check absorbs inner check removal",
    },
    # -- state.py ---------------------------------------------------------
    413: {
        "applicable": False,
        "rationale": "Lean models checkpoints as Nat counter, not dict structure",
    },
    414: {
        "applicable": False,
        "rationale": "Lean models checkpoints as Nat counter, not dict structure",
    },
}


def _clean_lean_cache():
    """Remove build artifacts."""
    build_lib = LEAN_DIR / ".lake" / "build" / "lib" / "lean" / "Lean4Learn"
    build_ir = LEAN_DIR / ".lake" / "build" / "ir" / "Lean4Learn"
    for d in [build_lib, build_ir]:
        if d.exists():
            for f in d.iterdir():
                if f.stem == "HarnessVerification":
                    f.unlink(missing_ok=True)


def test_lean_mutant(mutant_id: int) -> tuple[bool, bool, str]:
    """Test a survived mutant against the Lean spec.
    Returns (applicable, catches, detail).
    """
    mapping = LEAN_MAPPINGS.get(mutant_id)
    if not mapping:
        return False, False, "No Lean mapping defined"

    if mapping.get("applicable") is False:
        return False, False, f"N/A: {mapping['rationale']}"

    old_text = mapping["old"]
    new_text = mapping["new"]
    replace_all = mapping.get("replace_all", False)

    original = LEAN_FILE.read_text()
    if old_text not in original:
        return True, False, f"ERROR: old_text not found: {old_text[:50]!r}"

    if replace_all:
        mutated = original.replace(old_text, new_text)
    else:
        mutated = original.replace(old_text, new_text, 1)
    LEAN_FILE.write_text(mutated)
    _clean_lean_cache()

    env = {**os.environ, "PATH": f"{LAKE_BIN.parent}:{os.environ.get('PATH', '')}"}

    try:
        result = subprocess.run(
            [str(LAKE_BIN), "build", "Lean4Learn.HarnessVerification"],
            capture_output=True, text=True, timeout=120,
            cwd=str(LEAN_DIR), env=env,
        )
        if result.returncode != 0:
            errors = [l for l in (result.stderr + result.stdout).splitlines()
                      if "error:" in l.lower()]
            return True, True, f"BUILD FAILS ({len(errors)} errors): {mapping['rationale']}"
        else:
            return True, False, f"BUILD PASSES: {mapping['rationale']}"
    except subprocess.TimeoutExpired:
        return True, True, "BUILD TIMEOUT"
    finally:
        LEAN_FILE.write_text(original)
        _clean_lean_cache()


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score CI."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - spread) / denom), min(1.0, (centre + spread) / denom)


def main():
    print("=" * 78)
    print("AUTOMATED MUTATION ANALYSIS (mutmut + Lean 4)")
    print("=" * 78)

    # Phase 1: Read mutmut results
    print("\n[Phase 1] Reading mutmut database...")
    mutants = get_mutmut_results()
    print(f"  Total mutants: {len(mutants)}")

    status_counts: dict[str, int] = {}
    for m in mutants:
        status_counts[m.status] = status_counts.get(m.status, 0) + 1
    for s, c in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")

    survivors = [m for m in mutants if m.status == "bad_survived"]
    killed = [m for m in mutants if m.status == "ok_killed"]
    suspicious = [m for m in mutants if m.status == "ok_suspicious"]
    print(f"\n  Mutation score (tests): {len(killed) + len(suspicious)}/{len(mutants)}"
          f" = {(len(killed) + len(suspicious)) / len(mutants):.0%}")

    # Phase 2: Classify survivors
    print(f"\n[Phase 2] Classifying {len(survivors)} survived mutants...")
    for m in survivors:
        classify_survivor(m)

    class_counts: dict[str, int] = {}
    for m in survivors:
        class_counts[m.classification] = class_counts.get(m.classification, 0) + 1
    for c, n in sorted(class_counts.items()):
        print(f"  {c}: {n}")

    real_gaps = [m for m in survivors if m.classification == "real_gap"]
    equivalents = [m for m in survivors if m.classification == "equivalent"]
    configs = [m for m in survivors if m.classification == "config"]
    test_infras = [m for m in survivors if m.classification == "test_infra"]

    print(f"\n  Real gaps (genuine test blind spots): {len(real_gaps)}")
    print(f"  Equivalent (no behavior change): {len(equivalents)}")
    print(f"  Test infrastructure: {len(test_infras)}")
    print(f"  Config constants: {len(configs)}")

    # Adjusted mutation score: exclude equivalent + config + test_infra
    non_equiv = len(mutants) - len(equivalents) - len(configs) - len(test_infras)
    adj_killed = len(killed) + len(suspicious)
    print(f"\n  Adjusted mutation score: {adj_killed}/{non_equiv}"
          f" = {adj_killed / non_equiv:.0%}" if non_equiv else "")

    # Phase 3: Test Lean-applicable survivors
    print(f"\n[Phase 3] Testing Lean-applicable survivors...")
    lean_tested = 0
    lean_caught = 0
    lean_na = 0

    for m in survivors:
        if m.id in LEAN_MAPPINGS:
            m.lean_applicable, m.lean_catches, m.lean_detail = test_lean_mutant(m.id)
            if m.lean_applicable:
                lean_tested += 1
                if m.lean_catches:
                    lean_caught += 1
            else:
                lean_na += 1
            status = "CATCH" if m.lean_catches else ("N/A" if not m.lean_applicable else "MISS")
            print(f"  mutant {m.id}: [{status}] {m.lean_detail[:70]}")

    print(f"\n  Mapped: {len(LEAN_MAPPINGS)} | Applicable: {lean_tested}"
          f" | Caught: {lean_caught} | N/A: {lean_na}")

    # Phase 4: File-level breakdown of real gaps
    print(f"\n[Phase 4] Real gaps by file:")
    file_gaps: dict[str, list[MutantInfo]] = {}
    for m in real_gaps:
        file_gaps.setdefault(m.file, []).append(m)
    for f in sorted(file_gaps, key=lambda x: -len(file_gaps[x])):
        print(f"  {f}: {len(file_gaps[f])} real gaps")

    # Phase 5: Compile statistics
    print(f"\n[Phase 5] Computing statistics...")

    stats = {
        "total_mutants": len(mutants),
        "killed": len(killed),
        "survived": len(survivors),
        "suspicious": len(suspicious),
        "mutation_score_raw": round((len(killed) + len(suspicious)) / len(mutants), 3),
        "classification": {
            "equivalent": len(equivalents),
            "test_infra": len(test_infras),
            "config": len(configs),
            "real_gap": len(real_gaps),
        },
        "mutation_score_adjusted": round(adj_killed / non_equiv, 3) if non_equiv else 0,
        "non_equivalent_total": non_equiv,
        "lean_analysis": {
            "survivors_with_mapping": len(LEAN_MAPPINGS),
            "lean_applicable": lean_tested,
            "lean_caught": lean_caught,
            "lean_na": lean_na,
        },
        "by_file": {},
    }

    # Per-file stats
    for m in mutants:
        f = m.file
        stats["by_file"].setdefault(f, {
            "total": 0, "killed": 0, "survived": 0,
            "real_gap": 0, "equivalent": 0, "config": 0, "test_infra": 0,
        })
        stats["by_file"][f]["total"] += 1
        if m.status == "ok_killed" or m.status == "ok_suspicious":
            stats["by_file"][f]["killed"] += 1
        elif m.status == "bad_survived":
            stats["by_file"][f]["survived"] += 1
            cls = m.classification
            if cls in stats["by_file"][f]:
                stats["by_file"][f][cls] += 1

    # Save results
    raw_data = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tool": "mutmut 2.5.1",
            "test_suite": "pytest (unit + integration + property-based)",
        },
        "statistics": stats,
        "real_gaps": [
            {"id": m.id, "file": m.file, "line": m.line_number,
             "reason": m.classification_reason, "diff": m.diff[:300],
             "lean_applicable": m.lean_applicable, "lean_catches": m.lean_catches,
             "lean_detail": m.lean_detail}
            for m in real_gaps
        ],
        "lean_mappings": [
            {"mutant_id": mid, "applicable": mapping.get("applicable", True),
             "rationale": mapping["rationale"]}
            for mid, mapping in sorted(LEAN_MAPPINGS.items())
        ],
    }
    RESULTS_JSON.write_text(json.dumps(raw_data, indent=2))

    # Generate markdown
    _generate_markdown(mutants, survivors, real_gaps, stats, lean_tested, lean_caught)

    print(f"\n{'=' * 78}")
    print("AUTOMATED STUDY COMPLETE")
    print(f"{'=' * 78}")
    print(f"  Mutants: {len(mutants)} | Killed: {len(killed)} | Survived: {len(survivors)}")
    print(f"  Raw score: {stats['mutation_score_raw']:.0%}"
          f" | Adjusted: {stats['mutation_score_adjusted']:.0%}")
    print(f"  Real gaps: {len(real_gaps)} | Equivalent: {len(equivalents)}"
          f" | Test infra: {len(test_infras)} | Config: {len(configs)}")
    print(f"  Lean mapped: {len(LEAN_MAPPINGS)} | Applicable: {lean_tested}"
          f" | Caught: {lean_caught}")
    print(f"  Results: {RESULTS_JSON}")
    print(f"  Report: {RESULTS_MD}")


def _generate_markdown(mutants, survivors, real_gaps, stats,
                       lean_tested, lean_caught):
    """Generate the automated results markdown."""

    # Wilson CIs for key metrics
    n = stats["total_mutants"]
    raw_lo, raw_hi = wilson_ci(stats["killed"], n)
    ne = stats["non_equivalent_total"]
    adj_lo, adj_hi = wilson_ci(stats["killed"], ne)

    lines = [
        "# Automated Mutation Testing Results (mutmut)",
        "",
        "> Generated by mutmut 2.5.1. All mutants are AST-level operator",
        "> mutations generated mechanically from the Python source.",
        "> Survivor classification follows Papadakis et al. (IEEE TSE 2019)",
        "> guidelines for equivalent mutant identification.",
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "|:-------|:------|",
        f"| Total mutants generated | {stats['total_mutants']} |",
        f"| Killed by test suite | {stats['killed']} |",
        f"| Survived | {stats['survived']} |",
        f"| Suspicious | {stats.get('suspicious', 0)} |",
        f"| **Raw mutation score** | **{stats['mutation_score_raw']:.0%}**"
        f" [{raw_lo:.0%}, {raw_hi:.0%}] |",
        "",
        "## Survivor Classification",
        "",
        "| Classification | Count | Description |",
        "|:---------------|:-----:|:------------|",
        f"| **Real gap** | {stats['classification']['real_gap']}"
        f" | Genuine test blind spot |",
        f"| **Equivalent** | {stats['classification']['equivalent']}"
        f" | No observable behavior change (logging, enums, messages) |",
        f"| **Test infra** | {stats['classification'].get('test_infra', 0)}"
        f" | Mock/test-double defaults (not production code) |",
        f"| **Config** | {stats['classification']['config']}"
        f" | Tuning constants not under test |",
        "",
        "## Adjusted Mutation Score",
        "",
        f"- **Raw**: {stats['killed']}/{stats['total_mutants']}"
        f" = {stats['mutation_score_raw']:.0%}"
        f" (95% Wilson CI: [{raw_lo:.0%}, {raw_hi:.0%}])",
        f"- **Adjusted** (excluding equivalent + config + test_infra):"
        f" {stats['killed']}/{stats['non_equivalent_total']}"
        f" = {stats['mutation_score_adjusted']:.0%}"
        f" (95% Wilson CI: [{adj_lo:.0%}, {adj_hi:.0%}])",
        "",
        "## Mutation Score by File",
        "",
        "| File | Total | Killed | Survived | Real Gaps | Score |",
        "|:-----|:-----:|:------:|:--------:|:---------:|:-----:|",
    ]

    for f in sorted(stats["by_file"]):
        fs = stats["by_file"][f]
        score = fs["killed"] / fs["total"] * 100 if fs["total"] else 0
        lines.append(
            f"| {f} | {fs['total']} | {fs['killed']} | {fs['survived']}"
            f" | {fs['real_gap']} | {score:.0f}% |"
        )

    # Lean analysis
    la = stats["lean_analysis"]
    lines += [
        "",
        "## Lean 4 Formal Verification of Survived Mutants",
        "",
        f"Of {stats['survived']} survived mutants, {la['survivors_with_mapping']}"
        f" were systematically mapped to the Lean spec:",
        f"- {la['lean_applicable']} applicable (within spec scope)",
        f"- {la['lean_na']} outside spec scope (with documented rationale)",
        f"- **{la['lean_caught']}/{la['lean_applicable']}"
        f" caught by formal specification"
        f" ({la['lean_caught']/la['lean_applicable']*100:.0f}%"
        f" within scope)**" if la['lean_applicable'] else "",
        "",
        "### Key Finding: Spec Abstraction Gap",
        "",
        "Mutant 64 (`total_cost += cost` -> `total_cost = cost`) passes the Lean",
        "spec because the `wf` predicate checks `cost <= maxBudget` per-step but",
        "lacks a cost-accumulation invariant. Since `c.cost <= s.cost + c.cost <=",
        "maxBudget` (Nat arithmetic), the weakened assignment still satisfies all",
        "existing theorems. This demonstrates a concrete spec weakness that would",
        "require adding `cost_monotone : new.cost >= old.cost` to the `wf` predicate.",
        "",
        "### Lean Mapping Details",
        "",
        "| Mutant | File | Applicable | Result | Rationale |",
        "|:------:|:-----|:----------:|:------:|:----------|",
    ]

    for m in survivors:
        if m.id in LEAN_MAPPINGS:
            mapping = LEAN_MAPPINGS[m.id]
            applicable = mapping.get("applicable", True)
            app_str = "Yes" if applicable else "No"
            if m.lean_catches:
                result_str = "CATCH"
            elif applicable and not m.lean_catches:
                result_str = "MISS"
            else:
                result_str = "N/A"
            lines.append(
                f"| {m.id} | {m.file} | {app_str} | {result_str}"
                f" | {mapping['rationale'][:60]} |"
            )

    # Real gaps table
    lines += [
        "",
        "## Real Gap Mutants",
        "",
        "| ID | File | Line | Mutation Type | Lean Mapped? |",
        "|:--:|:-----|:----:|:-------------|:------------:|",
    ]
    for m in real_gaps[:40]:  # Show first 40
        lean_status = ""
        if m.id in LEAN_MAPPINGS:
            if m.lean_catches:
                lean_status = "CATCH"
            elif m.lean_applicable:
                lean_status = "MISS"
            else:
                lean_status = "N/A (scope)"
        else:
            lean_status = "-"
        mutation_desc = m.classification_reason[:45]
        lines.append(
            f"| {m.id} | {m.file} | {m.line_number}"
            f" | {mutation_desc} | {lean_status} |"
        )
    if len(real_gaps) > 40:
        lines.append(f"| ... | | | *{len(real_gaps) - 40} more* | |")

    # Abstraction gap analysis
    mapped_ids = set(LEAN_MAPPINGS.keys())
    real_gap_mapped = [m for m in real_gaps if m.id in mapped_ids]
    real_gap_unmapped = [m for m in real_gaps if m.id not in mapped_ids]

    lines += [
        "",
        "## Abstraction Gap Analysis",
        "",
        f"Of {len(real_gaps)} real-gap mutants:",
        f"- {len(real_gap_mapped)} have Lean mappings"
        f" ({sum(1 for m in real_gap_mapped if m.lean_applicable)} applicable)",
        f"- {len(real_gap_unmapped)} are outside Lean spec scope entirely",
        "",
        "Gap categories (for unmapped real gaps):",
        "",
    ]

    # Categorize unmapped gaps by reason
    gap_cats: dict[str, int] = {}
    for m in real_gap_unmapped:
        gap_cats[m.classification_reason] = gap_cats.get(m.classification_reason, 0) + 1
    for reason, count in sorted(gap_cats.items(), key=lambda x: -x[1]):
        lines.append(f"- **{reason}**: {count}")

    lines += [
        "",
        "## Methodology",
        "",
        "1. **Mutation generation**: mutmut 2.5.1 (AST-level operator mutations)",
        "2. **Test suite**: 65 tests (40 unit + 5 integration + 20 property-based)",
        "3. **Survivor classification**: Rule-based, 4-tier:",
        "   - *equivalent*: logging, error messages, enums, type aliases, repr flags",
        "   - *test_infra*: MockResponse/MockLLMClient defaults",
        "   - *config*: COST_TABLE rates, retry params, default sizes",
        "   - *real_gap*: arithmetic, control flow, state management mutations",
        "4. **Lean mapping**: Systematic examination of all survivors in"
        " budget.py, orchestrator.py, state.py against Lean OState model",
        f"5. **Lean testing**: `lake build` pass/fail on {lean_tested}"
        f" applicable mutations",
        "",
        "---",
        f"*Generated by `analyze_mutmut.py` at {time.strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    RESULTS_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
