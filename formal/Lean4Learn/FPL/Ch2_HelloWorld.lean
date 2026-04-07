/-!
# Chapter 2: Hello World

This chapter will discuss structures, polymorphic types, and basic I/O in Lean.
-/

structure Point where
  x : Float
  y : Float
  deriving Repr

def origin : Point := { x := 0.0, y := 0.0 }

#eval origin
