# Two-Phase Mutation Testing Study Design

> Methodology document for the empirical evaluation.
> This bridges the automated baseline (Phase 1) and targeted analysis (Phase 2)
> into a coherent study design suitable for peer review.

## Study Overview

We evaluate the complementarity of five verification methods applied to an
LLM orchestration harness (780 LOC Python, 8 modules).  The study uses a
**two-phase design** that combines automated mutation generation for
population-level statistics with hand-crafted mutations for deep
multi-method comparison.

### Why Two Phases?

- **Phase 1 alone** (automated) gives unbiased population statistics but
  can only test against the pytest suite.  It cannot evaluate Lean 4
  or LLM-based review because those require manual semantic mapping.
- **Phase 2 alone** (hand-crafted) enables multi-method comparison but
  is vulnerable to selection bias.
- **Combined**: Phase 1 establishes the baseline and validates that
  Phase 2's selection is representative of the mutation population.

## Phase 1: Automated Baseline (mutmut)

**Tool**: mutmut 2.5.1 (AST-level operator mutations)

**Population**: 420 mutants across 8 source files, generated mechanically.

**Detection**: Single test suite (65 pytest tests: 40 unit + 5 integration
+ 20 property-based).

**Key results**:
- Raw mutation score: 55% (232/420)
- Survivor classification: 60 real gaps, 76 equivalent, 12 test
  infrastructure, 40 configuration
- Adjusted mutation score (excluding non-functional): 80% (232/292)

**Lean mapping**: 15 survivors systematically mapped to the Lean 4 spec.
2 applicable (within spec scope), 1 caught (50% within scope), 13 outside
spec scope with documented rationale.

**Key finding**: Mutant 64 (`total_cost += cost` -> `total_cost = cost`)
passes the Lean spec despite being a real bug.  The `wf` predicate checks
`cost <= maxBudget` but lacks a cost-accumulation invariant.  Since
`c.cost <= s.cost + c.cost <= maxBudget` (Nat arithmetic), the mutated
assignment still satisfies all theorems.

**Output**: `AUTOMATED_RESULTS.md`, `automated_results.json`

## Phase 2: Targeted Multi-Method Analysis

**Selection methodology**: 30 mutations selected to cover:
- All 4 semantic categories proportionally (logic, boundary, missing_check, state)
- All 8 source files
- Mutations within and outside Lean spec scope
- Overlap with Phase 1 survivors where possible

**Selection is NOT cherry-picked**: The 30 mutations span the same files
and categories as Phase 1's 60 real gaps, with proportional representation.
13 of 30 have direct Phase 1 equivalents (see mapping table below).

**Detection methods** (5):
1. Unit tests (40 pytest tests)
2. Integration tests (5 end-to-end tests)
3. Property-based tests (20 Hypothesis tests)
4. Lean 4 formal specification (15 theorems, `lake build` pass/fail)
5. LLM code review (structured evaluation)

**Key results**:
- Unit: 14/30 = 47% (4 unique detections)
- Integration: 6/30 = 20% (0 unique)
- Property-based: 10/30 = 33% (3 unique: M07, M13, M26)
- Lean 4: 8/10 = 80% within scope (1 unique: M10)
- Combined: 18/30 = 60%

**Output**: `RESULTS.md`, `empirical_results.json`

## Phase 1 <-> Phase 2 Mapping

| Phase 2 ID | Description | Phase 1 Equivalent | mutmut ID |
|:----------:|:------------|:-------------------|:---------:|
| M02 | Budget subtract instead of add | Cost accumulation | #64 |
| M05 | Token overhead 3 vs 4 | Token counting | #259 |
| M07 | Prompt rate for both | Rate constant | #57 |
| M09 | Off-by-one max_steps | Break removal | #330 |
| M10 | Budget >= vs > | Budget threshold | #69 |
| M13 | Budget /100 vs /1000 | Division constant | #57,61 |
| M14 | No step_count increment | Arithmetic mutation | (killed) |
| M17 | Skip registry lookup | Tool execution | #316 |
| M18 | Remove exceeded check | Budget check removal | (killed) |
| M20 | terminate() no flag | State mutation | (killed) |
| M27 | Skip checkpoint | State management | #360 |
| M28 | Overwrite checkpoint | Checkpoint structure | #413,414 |
| M30 | No prompt restore | System prompt | #228 |

13/30 Phase 2 mutations have direct Phase 1 counterparts.  The remaining
17 target behaviors that mutmut doesn't generate (e.g., semantic route
changes, case sensitivity, algorithm substitution).

## Combined Findings

### RQ1: Detection Complementarity

| Method | Phase 1 (n=420) | Phase 2 (n=30) |
|:-------|:---------------:|:--------------:|
| Unit tests | 53% raw | 47% |
| + Integration | -- | 20% |
| + Property-based | -- | 33% (3 unique) |
| + Lean 4 | 50% in scope | 80% in scope (1 unique) |
| Combined | 55% raw / 80% adj | 60% |

### RQ2: Formal Verification Scope

Lean 4 specs model 5 state invariants (token accounting, budget bounds,
checkpoint monotonicity, step bounds, termination consistency).

**Phase 1**: Of 60 real-gap survivors, only 2/15 mapped mutants (13%)
fall within the Lean spec scope.  The remaining 87% involve:
- Agent message construction (8 gaps)
- Tool schema generation (9 gaps)
- System prompt manipulation (4 gaps)
- Context window management (7 gaps)
- Routing decision logic (2 gaps)

**Phase 2**: Of 30 mutations, 10 (33%) have Lean spec equivalents.
Within scope, Lean catches 80% -- but scope covers only the
step/budget/token/checkpoint accounting layer.

### RQ3: Abstraction Gap Taxonomy

| Gap Category | Count (P1) | Count (P2) | Example |
|:-------------|:----------:|:----------:|:--------|
| Rate-level arithmetic | 2 | 2 | /1000 vs /1001 |
| Per-model tracking | 3 | 0 | _by_model dict |
| Loop control flow | 3 | 1 | break vs continue |
| Token deltas | 2 | 1 | Absolute vs relative |
| Checkpoint structure | 2 | 2 | Nat counter vs dict |
| Agent/tool logic | 0 | 11 | Message construction |
| Context management | 0 | 3 | Truncation logic |

## Threats to Validity

### Internal Validity
- **Survivor classification**: Rule-based, not manual inspection of all
  188 survivors.  We mitigate this by using conservative rules (default
  to "real_gap" for unclassified core-file mutations) and reporting both
  raw and adjusted scores.
- **Lean mapping completeness**: Only 15/188 survivors mapped.  More
  survivors in agents.py/tools.py/context.py are unmapped because the
  Lean spec doesn't model those components.

### External Validity
- **Single system**: Results may not generalize beyond LLM orchestration
  harnesses.  The mutation categories (agent logic, budget accounting,
  context management) are domain-specific.
- **Spec maturity**: The Lean spec was written alongside the code by
  the same author.  A third-party spec might cover different invariants.

### Construct Validity
- **Equivalent mutant problem**: We use rule-based classification
  following Papadakis et al. (IEEE TSE 2019) guidelines.  Some mutations
  classified as "equivalent" may be genuine bugs, and vice versa.
- **Phase 2 selection bias**: Mitigated by Phase 1 baseline and the
  Phase 1/Phase 2 mapping table above, but 17/30 Phase 2 mutations
  have no Phase 1 counterpart.

---
*Generated alongside `analyze_mutmut.py` and `run_empirical_study.py`*
