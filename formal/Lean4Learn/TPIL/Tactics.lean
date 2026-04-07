/-!
# Tactics Mode

This module will contain your exercises in Tactic Mode proofs (e.g. `intro`, `apply`, `rw`, `exact`).
-/

theorem p_implies_p (p : Prop) : p -> p := by
  intro hp
  exact hp
