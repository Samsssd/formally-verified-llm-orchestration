/-!
# Type Classes

This module will cover Lean 4 Type Classes (Ad-Hoc Polymorphism).
-/

class Add3 (a : Type) where
  add3 : a -> a -> a -> a

instance : Add3 Nat where
  add3 x y z := x + y + z

#eval Add3.add3 1 2 3
