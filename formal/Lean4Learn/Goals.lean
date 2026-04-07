/-!
# Final Goals: Example Proofs

You mentioned:
> write and prove simple properties (like "this function always returns a value less than N" or "this state machine never reaches state X") before moving on.

Here are the concrete proofs for exactly those two scenarios natively in standard Lean 4.
-/

--------------------------------------------------------------------------------
-- 1. "This function always returns a value less than N"
--------------------------------------------------------------------------------

/-- A function that caps a number at `N - 1`. -/
def cap (n N : Nat) : Nat :=
  if n < N then
    n
  else
    N - 1

/-- Proof that our function always returns `< N`, assuming `N > 0`. -/
theorem cap_lt_N (n N : Nat) (hN : N > 0) : cap n N < N := by
  -- Unfold the definition of our function
  unfold cap
  -- Split the if-else branches
  split
  · -- Branch 1: `n < N` evaluates to true. Our goal is `n < N`.
    -- The hypothesis `h✝ : n < N` is exactly our goal.
    assumption
  · -- Branch 2: `n < N` evaluates to false. Our goal is `N - 1 < N`.
    -- `omega` is Lean's built-in arithmetic solver — it handles linear Nat goals.
    omega

--------------------------------------------------------------------------------
-- 2. "This state machine never reaches state X"
--------------------------------------------------------------------------------

/-- A simple system that cycles through states, but has a trap `error_X` state. -/
inductive State where
  | start
  | processing
  | done
  | error_X
  deriving Repr, DecidableEq

/-- The state transition logic. Notice how nothing transitions into `error_X`. -/
def step (s : State) : State :=
  match s with
  | .start => .processing
  | .processing => .done
  | .done => .start
  | .error_X => .error_X

/-- 
  Inductive proposition capturing the concept of "Reachable from start".
  - Rule 1: We are initially at `.start`.
  - Rule 2: If we reach state `s`, we can reach `step s`.
-/
inductive Reachable : State → Prop where
  | init : Reachable .start
  | next (s : State) (h : Reachable s) : Reachable (step s)

/-- 
  The proof that the state machine starting at `start` will NEVER reach `error_X`.
-/
theorem never_reaches_error_x (s : State) (h : Reachable s) : s ≠ .error_X := by
  -- We prove this by structural induction on the rules of reachability.
  induction h with
  | init => 
    -- Case 1: Start state is not error_X. 
    -- They are distinct constructors, so `intro` followed by `contradiction` solves it.
    intro hEq
    contradiction
  | next s_prev h_reach ih =>
    -- Case 2: We advanced by one step (`step s_prev`).
    -- `ih` is our inductive hypothesis: `s_prev ≠ error_X`.
    -- We must show that `step s_prev ≠ error_X`.
    -- Since `step` is defined by cases on `s_prev`, we do cases on `s_prev` here too:
    cases s_prev with
    | start => intro; contradiction      -- step start = processing ≠ error_X
    | processing => intro; contradiction -- step processing = done ≠ error_X
    | done => intro; contradiction       -- step done = start ≠ error_X
    | error_X => 
      -- Contradiction: our inductive hypothesis `ih` says we are NOT in error_X,
      -- but this case branch says we ARE in error_X.
      contradiction
