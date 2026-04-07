/-!
# Chapter 6: Proofs as Data

Here we will explore propositions and proofs in Lean, which is the cornerstone to proving properties about your code!
-/

-- A simple property: an even number
def isEven (n : Nat) : Bool := n % 2 == 0

-- Example theorem to prove eventually
-- theorem even_plus_even (n m : Nat) (h1 : isEven n = true) (h2 : isEven m = true) : isEven (n + m) = true := by sorry
