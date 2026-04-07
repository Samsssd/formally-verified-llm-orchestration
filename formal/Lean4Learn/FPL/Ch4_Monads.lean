/-!
# Chapter 4: Monads

Understanding Monads, Option Monad, State Monad etc in Lean.
-/

-- Stub 
def addOption (x y : Option Nat) : Option Nat := do
  let a <- x
  let b <- y
  pure (a + b)
