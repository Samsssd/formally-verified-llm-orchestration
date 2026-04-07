/-!
# Inductive Types

This module focuses on custom Inductive Types, which are at the heart of Lean 4.
-/

inductive Weekday where
  | sunday : Weekday
  | monday : Weekday
  | tuesday : Weekday
  | wednesday : Weekday
  | thursday : Weekday
  | friday : Weekday
  | saturday : Weekday
  deriving Repr

def nextDay (d : Weekday) : Weekday :=
  match d with
  | .sunday    => .monday
  | .monday    => .tuesday
  | .tuesday   => .wednesday
  | .wednesday => .thursday
  | .thursday  => .friday
  | .friday    => .saturday
  | .saturday  => .sunday

#eval nextDay .tuesday
