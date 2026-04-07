/-!
# Chapter 1: Getting to Know Lean

In this chapter, we start looking at the basic mechanics of Lean.
Let's define a simple function and evaluate it.
-/

def add1 (n : Nat) : Nat := n + 1

#eval add1 7 -- Should print 8
