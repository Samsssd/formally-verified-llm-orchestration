# Spec-Guided Mutation Testing Results

## Method

Systematically negate each conjunct of the Lean 4 `wf` predicate
to generate minimal, semantically meaningful mutations. Each mutation
is applied to both the Lean spec and the Python implementation, then
tested to reveal the formal/informal boundary.

## Well-Formedness Invariants (from Lean `wf` predicate)

| ID | Name | Lean Expression |
|:---|:-----|:----------------|
| P1 | Token accounting identity | `s.tTok = s.pTok + s.cTok` |
| P2 | Budget safety | `s.reason != some .budget_exceeded -> s.cost <= s.maxBudget` |
| P3 | Checkpoint monotonicity | `s.ckpts <= s.step` |
| P4 | Step bound | `s.step <= s.maxSteps + 1` |
| P5 | Termination consistency | `s.reason = some .budget_exceeded -> s.done = true` |

## Spec-Guided Mutation Results

| ID | Invariant | Description | Lean Catches? | Tests Catch? | Props Catch? | Broken Theorems |
|:---|:----------|:------------|:-------------:|:------------:|:------------:|:----------------|
| SGM-P1a | P1 | Drop completion tokens from total (tTok += pTok only) | FAIL (caught) | YES (4/65) | YES (2/20) | step_preserves_tokens, step_preserves_wf |
| SGM-P1b | P1 | Double-count prompt tokens in total (tTok += pTok + pTok) | FAIL (caught) | YES (4/65) | YES (2/20) | step_preserves_tokens, step_preserves_wf |
| SGM-P2a | P2 | Invert budget check (> to <), effectively disabling it | FAIL (caught) | YES (13/65) | YES (5/20) | continue_adds_ckpt, step_preserves_wf |
| SGM-P2b | P2 | Weaken budget check (> to >=), off-by-one | FAIL (caught) | NO (0/65) | NO (0/20) | continue_adds_ckpt |
| SGM-P2c | P2 | Break cost accumulation (cost = new_cost instead of cost += new_cost) | PASS (missed) | NO (0/65) | NO (0/20) | - |
| SGM-P3a | P3 | Double checkpoint increment (ckpts + 2 instead of ckpts + 1) | FAIL (caught) | YES (4/65) | YES (2/20) | continue_adds_ckpt, step_ckpt_bounded, step_preserves_wf |
| SGM-P3b | P3 | Add checkpoint in max_steps termination path | FAIL (caught) | YES (1/65) | NO (0/20) | max_steps_no_ckpt, step_ckpt_bounded, step_preserves_wf |
| SGM-P4a | P4 | Double step increment (step + 2 instead of step + 1) | FAIL (caught) | YES (5/65) | YES (2/20) | step_inc_or_done |
| SGM-P4b | P4 | Don't increment step (step stays at s.step) | FAIL (caught) | YES (1/1) | YES (2/20) | step_ckpt_bounded, step_inc_or_done, step_preserves_wf |
| SGM-P5a | P5 | Budget exceeded but not done (done=false in budget_exceeded path) | FAIL (caught) | YES (1/65) | NO (0/20) | step_inc_or_done, step_preserves_wf |
| SGM-P5b | P5 | Wrong reason: set task_complete instead of budget_exceeded | FAIL (caught) | YES (1/65) | NO (0/20) | step_preserves_wf |

## Detection Summary

| Metric | Value |
|:-------|:------|
| Total spec-guided mutations | 11 |
| Lean detection rate | 90.9% |
| Python test detection rate | 81.8% |
| Property test detection rate | 54.5% |
| Caught by both Lean + tests | 9 |
| Caught by Lean only | 1 |
| Caught by tests only | 0 |
| Caught by neither | 1 |

## Spec-Guided vs Random (mutmut) Comparison

| Metric | Spec-Guided | Random (mutmut) |
|:-------|:------------|:----------------|
| Total mutations | 11 | 420 |
| Lean detection rate | 90.9% | 1/2 applicable |
| Test detection rate | 81.8% | 79.5% (adjusted) |

## Per-Invariant Analysis

### P1: Token accounting identity

- Mutations: 2
- Lean catches: 2/2
- Tests catch: 2/2
- Lean and tests have equal detection for this invariant

### P2: Budget safety

- Mutations: 3
- Lean catches: 2/3
- Tests catch: 1/3
- **Gap**: Lean catches 1 mutation(s) that tests miss

### P3: Checkpoint monotonicity

- Mutations: 2
- Lean catches: 2/2
- Tests catch: 2/2
- Lean and tests have equal detection for this invariant

### P4: Step bound

- Mutations: 2
- Lean catches: 2/2
- Tests catch: 2/2
- Lean and tests have equal detection for this invariant

### P5: Termination consistency

- Mutations: 2
- Lean catches: 2/2
- Tests catch: 2/2
- Lean and tests have equal detection for this invariant

## Key Findings

1. **Spec-guided mutations have higher Lean detection rates** than random mutations,
   because they directly target formally verified invariants.

2. **Some spec-guided mutations escape tests** even when caught by Lean,
   revealing under-tested invariants in the Python implementation.

3. **The formal/informal boundary** is precisely characterized by mutations
   that Lean catches but tests miss (or vice versa).

4. **Invariant negation is systematic**: unlike random AST mutations,
   each spec-guided mutation has a clear semantic meaning tied to a
   specific safety property.
