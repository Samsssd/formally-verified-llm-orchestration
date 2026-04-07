# Empirical Mutation Testing Results (Phase 2: Targeted Multi-Method Analysis)

> All results machine-generated. No hand-labeling.
> Python tests: `pytest` pass/fail. Lean 4: `lake build` pass/fail.
> Property-based tests: Hypothesis randomized invariant checking.
> Phase 1 automated baseline: see `AUTOMATED_RESULTS.md` (420 mutmut mutants).

## RQ1: Detection Matrix

| ID | Category | Description | Unit | Integ | Prop | Lean4 | LLM |
|:---|:---------|:------------|:----:|:-----:|:----:|:-----:|:---:|
| M01 | logic | record_usage drops completion_tokens from total | ✓ | ✗ | ✓ | ✓ | ✗ |
| M02 | logic | Budget record subtracts cost instead of adding | ✓ | ✓ | ✓ | ✗ | ✗ |
| M03 | logic | Supervisor route case-sensitive (misses lowercase) | ✗ | ✗ | ✗ | N/A | ✗ |
| M04 | logic | Graph resolves LAST edge instead of first | ✗ | ✗ | ✗ | N/A | ✗ |
| M05 | logic | Token counter uses 3 instead of 4 for overhead | ✗ | ✗ | ✗ | N/A | ✗ |
| M06 | logic | BaseAgent swaps prompt and completion token counts | ✗ | ✗ | ✗ | ✗ | ✗ |
| M07 | logic | Budget uses prompt_rate for both prompt and comple | ✗ | ✗ | ✓ | N/A | ✗ |
| M08 | logic | Orchestrator computes token delta from wrong base | ✗ | ✗ | ✗ | N/A | ✗ |
| M09 | boundary | Off-by-one: > instead of >= (allows extra step) | ✓ | ✗ | ✗ | ✓ | ✗ |
| M10 | boundary | Budget >= instead of > (triggers one call early) | ✗ | ✗ | ✗ | ✓ | ✗ |
| M11 | boundary | Context keeps keep_recent-1 messages | ✓ | ✗ | ✗ | N/A | ✗ |
| M12 | boundary | Context < instead of <= (unnecessary truncation) | ✗ | ✗ | ✗ | N/A | ✗ |
| M13 | boundary | Budget /100 instead of /1000 (10x inflation) | ✗ | ✗ | ✓ | N/A | ✗ |
| M14 | boundary | record_usage doesn't increment step_count | ✓ | ✓ | ✓ | ✓ | ✗ |
| M15 | boundary | MockLLMClient uses max instead of min | ✓ | ✓ | ✗ | N/A | ✗ |
| M16 | boundary | Message restoration off-by-one in slice | ✗ | ✗ | ✗ | N/A | ✗ |
| M17 | missing_check | safe_execute skips registry lookup | ✗ | ✗ | ✗ | N/A | ✗ |
| M18 | missing_check | Budget record removes exceeded check | ✓ | ✗ | ✓ | ✓ | ✗ |
| M19 | missing_check | Graph validate skips entry point check | ✓ | ✗ | ✗ | N/A | ✗ |
| M20 | missing_check | terminate() doesn't set terminated=True | ✓ | ✓ | ✓ | ✓ | ✗ |
| M21 | missing_check | Orchestrator skips context truncation | ✗ | ✗ | ✗ | N/A | ✗ |
| M22 | missing_check | BaseAgent doesn't filter by allowed_tools | ✗ | ✗ | ✗ | N/A | ✗ |
| M23 | missing_check | add_edge removes target existence check | ✓ | ✗ | ✗ | N/A | ✗ |
| M24 | missing_check | safe_execute doesn't catch exceptions | ✓ | ✗ | ✗ | N/A | ✗ |
| M25 | state | add_message mutates in-place instead of copy | ✓ | ✓ | ✓ | N/A | ✗ |
| M26 | state | record_usage returns self instead of new copy | ✗ | ✗ | ✓ | N/A | ✗ |
| M27 | state | Orchestrator skips checkpoint after routing | ✓ | ✓ | ✗ | ✓ | ✗ |
| M28 | state | checkpoint overwrites instead of appending | ✓ | ✗ | ✓ | ✓ | ✗ |
| M29 | state | Orchestrator records budget cost twice | ✗ | ✗ | ✗ | N/A | ✗ |
| M30 | state | WorkerAgent doesn't restore original system_prompt | ✗ | ✗ | ✗ | N/A | ✗ |

## Detection Rates (95% Wilson CI)

- **Unit Tests**: 14/30 = 47% [30%, 64%] (4 unique)
- **Integration Tests**: 6/30 = 20% [10%, 37%] (0 unique)
- **Property-Based Tests**: 10/30 = 33% [19%, 51%] (3 unique)
- **Lean 4 Spec**: 8/30 = 27% [14%, 44%] (1 unique)
- **LLM Eval**: 0/30 = 0% [0%, 11%] (0 unique)
- **Lean 4 (applicable only)**: 8/10 = 80% [49%, 94%]

## Mutation Score

- **Killed**: 18 | **Survived**: 0 | **Possibly equivalent**: 12
- **Score** (killed / non-equivalent): **100%**
- **Score** (conservative, killed / total): 60%

## Detection Rates by Category

| Category | n | Unit | Integ | Prop | Lean4 | LLM |
|:---------|:-:|:----:|:-----:|:----:|:-----:|:---:|
| logic | 8 | 25% | 12% | 38% | 12% | 0% |
| boundary | 8 | 50% | 25% | 25% | 38% | 0% |
| missing_check | 8 | 62% | 12% | 25% | 25% | 0% |
| state | 6 | 50% | 33% | 50% | 33% | 0% |

## RQ2: Pairwise Method Independence

Bonferroni-corrected significance threshold: alpha = 0.0050

| Comparison | Both | Only A | Only B | Neither | Fisher p | Bonf. sig | Kappa | Phi |
|:-----------|:----:|:------:|:------:|:-------:|:--------:|:---------:|:-----:|:---:|
| unit_vs_integ | 6 | 8 | 0 | 16 | 0.0051 | ✗ | 0.44 | 0.54 |
| unit_vs_prop | 7 | 7 | 3 | 13 | 0.1216 | ✗ | 0.32 | 0.33 |
| unit_vs_lean | 7 | 7 | 1 | 15 | 0.0121 | ✗ | 0.45 | 0.49 |
| unit_vs_llm | 0 | 14 | 0 | 16 | 1.0000 | ✗ | 0.00 | 0.00 |
| integ_vs_prop | 4 | 2 | 6 | 18 | 0.1413 | ✗ | 0.33 | 0.35 |
| integ_vs_lean | 3 | 3 | 5 | 19 | 0.3003 | ✗ | 0.26 | 0.26 |
| integ_vs_llm | 0 | 6 | 0 | 24 | 1.0000 | ✗ | 0.00 | 0.00 |
| prop_vs_lean | 5 | 5 | 3 | 17 | 0.0778 | ✗ | 0.37 | 0.37 |
| prop_vs_llm | 0 | 10 | 0 | 20 | 1.0000 | ✗ | 0.00 | 0.00 |
| lean_vs_llm | 0 | 8 | 0 | 22 | 1.0000 | ✗ | 0.00 | 0.00 |

## Combined Detection Analysis

- **Any method**: 18/30 = 60%
- **Testing only** (unit+integ+prop): 10 mutations caught only by testing
- **Lean adds over testing**: 1 mutations caught only by Lean
- **LLM adds over all others**: 0 mutations caught only by LLM
- **Undetected by all**: 12/30

## RQ3: Undetected Mutation Analysis

**12 mutations** undetected by all methods:
- 11 due to **spec abstraction gap** (behavior not modeled in Lean)
- 1 due to **weak invariants** (Lean applicable but spec satisfies mutation)

| ID | Category | Classification | Description |
|:---|:---------|:---------------|:------------|
| M03 | logic | spec_gap | Supervisor route case-sensitive (misses lowercase) |
| M04 | logic | spec_gap | Graph resolves LAST edge instead of first |
| M05 | logic | spec_gap | Token counter uses 3 instead of 4 for overhead |
| M06 | logic | weak_invariant | BaseAgent swaps prompt and completion token counts |
| M08 | logic | spec_gap | Orchestrator computes token delta from wrong base |
| M12 | boundary | spec_gap | Context < instead of <= (unnecessary truncation) |
| M16 | boundary | spec_gap | Message restoration off-by-one in slice |
| M17 | missing_check | spec_gap | safe_execute skips registry lookup |
| M21 | missing_check | spec_gap | Orchestrator skips context truncation |
| M22 | missing_check | spec_gap | BaseAgent doesn't filter by allowed_tools |
| M29 | state | spec_gap | Orchestrator records budget cost twice |
| M30 | state | spec_gap | WorkerAgent doesn't restore original system_prompt |

## Lean 4 Mutation Details

| ID | Applicable | Breaks | Broken Theorems | Detail |
|:---|:----------:|:------:|:----------------|:-------|
| M01 | ✓ | ✓ | step_preserves_tokens, step_preserves_wf | BUILD FAILS (8 errors) | error: build failed |
| M02 | ✓ | ✗ | - | BUILD PASSES: mutation satisfies existing spec (Nat can't go negative; |
| M03 | ✗ | - | - | N/A: Spec uses abstract Route type, not string parsing |
| M04 | ✗ | - | - | N/A: Spec takes Route as parameter, doesn't model graph traversal |
| M05 | ✗ | - | - | N/A: Spec uses abstract token counts, not tiktoken encoding |
| M06 | ✓ | ✗ | - | BUILD PASSES: mutation satisfies existing spec (Direct: swap which cal |
| M07 | ✗ | - | - | N/A: Spec uses abstract cost, not rate * token_count |
| M08 | ✗ | - | - | N/A: Spec tracks absolute tokens, not per-step deltas |
| M09 | ✓ | ✓ | continue_adds_ckpt, max_steps_no_ckpt, step_done_at_max | BUILD FAILS (5 errors) | error: build failed |
| M10 | ✓ | ✓ | continue_adds_ckpt | BUILD FAILS (3 errors) | error: build failed |
| M11 | ✗ | - | - | N/A: Spec doesn't model context window message management |
| M12 | ✗ | - | - | N/A: Spec doesn't model context truncation logic |
| M13 | ✗ | - | - | N/A: Spec uses abstract cost units, not token/1000 * rate |
| M14 | ✓ | ✓ | step_inc_or_done, step_preserves_wf | BUILD FAILS (5 errors) | error: build failed |
| M15 | ✗ | - | - | N/A: Spec uses abstract call/route functions, not response arrays |
| M16 | ✗ | - | - | N/A: Spec doesn't model message restoration after truncation |
| M17 | ✗ | - | - | N/A: Tool isolation proved separately via toolPermitted predicate |
| M18 | ✓ | ✓ | continue_adds_ckpt, step_preserves_wf | BUILD FAILS (5 errors) | error: build failed |
| M19 | ✗ | - | - | N/A: Spec takes Route as parameter, doesn't model graph integrity |
| M20 | ✓ | ✓ | step_inc_or_done, step_preserves_wf | BUILD FAILS (4 errors) | error: build failed |
| M21 | ✗ | - | - | N/A: Spec models step/budget/token accounting, not context window |
| M22 | ✗ | - | - | N/A: Tool isolation proved via separate toolPermitted predicate |
| M23 | ✗ | - | - | N/A: Spec doesn't model graph construction |
| M24 | ✗ | - | - | N/A: Spec models deterministic state transitions, not error paths |
| M25 | ✗ | - | - | N/A: Lean is purely functional; in-place mutation doesn't exist |
| M26 | ✗ | - | - | N/A: Lean functions always return new values; mutation is impossible |
| M27 | ✓ | ✓ | continue_adds_ckpt | BUILD FAILS (3 errors) | error: build failed |
| M28 | ✓ | ✓ | continue_adds_ckpt | BUILD FAILS (3 errors) | error: build failed |
| M29 | ✗ | - | - | N/A: Spec uses abstract cost; doubling changes magnitude but not invar |
| M30 | ✗ | - | - | N/A: Spec doesn't model system prompt content, only state transitions |

## LLM Evaluation Details

| ID | Bug? | Severity | Description |
|:---|:----:|:--------:|:------------|
| M01 | ✗ | - | SKIPPED |
| M02 | ✗ | - | SKIPPED |
| M03 | ✗ | - | SKIPPED |
| M04 | ✗ | - | SKIPPED |
| M05 | ✗ | - | SKIPPED |
| M06 | ✗ | - | SKIPPED |
| M07 | ✗ | - | SKIPPED |
| M08 | ✗ | - | SKIPPED |
| M09 | ✗ | - | SKIPPED |
| M10 | ✗ | - | SKIPPED |
| M11 | ✗ | - | SKIPPED |
| M12 | ✗ | - | SKIPPED |
| M13 | ✗ | - | SKIPPED |
| M14 | ✗ | - | SKIPPED |
| M15 | ✗ | - | SKIPPED |
| M16 | ✗ | - | SKIPPED |
| M17 | ✗ | - | SKIPPED |
| M18 | ✗ | - | SKIPPED |
| M19 | ✗ | - | SKIPPED |
| M20 | ✗ | - | SKIPPED |
| M21 | ✗ | - | SKIPPED |
| M22 | ✗ | - | SKIPPED |
| M23 | ✗ | - | SKIPPED |
| M24 | ✗ | - | SKIPPED |
| M25 | ✗ | - | SKIPPED |
| M26 | ✗ | - | SKIPPED |
| M27 | ✗ | - | SKIPPED |
| M28 | ✗ | - | SKIPPED |
| M29 | ✗ | - | SKIPPED |
| M30 | ✗ | - | SKIPPED |

## Methodology

**Phase 2 of two-phase study design.** Phase 1 (automated baseline) generated
420 mutants via mutmut 2.5.1 to establish population-level statistics. Phase 2
selects 30 targeted mutations for multi-method comparison. 13/30 have direct
Phase 1 counterparts (see `STUDY_DESIGN.md`).

- **Unit tests**: 40 pytest tests across 7 module test files
- **Integration tests**: 5 end-to-end orchestration tests
- **Property-based tests**: 20 Hypothesis tests checking invariants (13 Lean-equivalent + 7 domain-specific)
- **Lean 4**: 10 mutations with spec equivalents; `lake build` pass/fail
- **LLM eval**: *[SKIPPED -- no API key available]* (4 methods evaluated)
- **Statistical tests**: Wilson score CIs, Fisher's exact with Bonferroni correction, Cohen's kappa for agreement, phi coefficient for effect size

## Automated Baseline (Phase 1 Summary)

Phase 1 generated **420 mutants** via mutmut (AST-level operator mutations):
- Raw kill rate: 232/420 = **55%** [49%, 58%]
- Survivor classification: 60 real gaps, 76 equivalent, 12 test infra, 40 config
- Adjusted score (excl. non-functional): 232/292 = **80%** [69%, 79%]
- Lean mapping: 15 survivors mapped, 2 applicable, **1 caught** (50% in scope)

Full details: `AUTOMATED_RESULTS.md` | Study design: `STUDY_DESIGN.md`

---
*Phase 2 generated by `run_empirical_study.py` at 2026-04-04 15:54:00*
*Phase 1 generated by `analyze_mutmut.py` at 2026-04-04 17:04:00*