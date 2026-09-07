# Beauty Rubric

Use this rubric to evaluate whether an abstraction is genuinely good.

Score each dimension from 1 to 5.

## 1) Problem fit
**Question**
Does the abstraction directly address the real change pressure?

- **1**: mostly decorative or speculative
- **3**: solves part of the real problem
- **5**: tightly aligned to the actual source of volatility

## 2) Surface area
**Question**
Is the public API as small as it can be?

- **1**: large, leaky, or redundant
- **3**: acceptable but can be trimmed
- **5**: compact, intention-revealing, hard to misuse

## 3) Call-site ergonomics
**Question**
Does the common usage path feel obvious?

- **1**: awkward, verbose, or requires ceremony
- **3**: workable but not elegant
- **5**: natural names, strong inference, readable usage

## 4) Runtime honesty
**Question**
Does the design reflect what truly exists at runtime?

- **1**: runtime objects exist mainly to satisfy static structure
- **3**: partly honest, partly ceremonial
- **5**: runtime architecture matches real behavior and lifecycle

## 5) Change isolation
**Question**
Will the abstraction localize likely future changes?

- **1**: future changes still cut across many modules
- **3**: some changes become easier
- **5**: major volatility is clearly absorbed

## 6) Type ergonomics
**Question**
Are the types helpful without becoming the main source of complexity?

- **1**: dense, fragile, or inference-hostile
- **3**: mixed
- **5**: clear, narrow, and supportive

## 7) Testability
**Question**
Can the abstraction be tested without heroics?

- **1**: difficult to isolate or substitute
- **3**: testable with some pain
- **5**: boundaries and state are easy to exercise

## 8) Deletion friendliness
**Question**
Could this abstraction be simplified later without surgery?

- **1**: deeply entangled and hard to unwind
- **3**: somewhat sticky
- **5**: modular and easy to collapse if it stops paying rent

## 9) Overengineering risk
**Question**
How much accidental complexity does this abstraction add?

- **1**: high accidental complexity
- **3**: some complexity, partly justified
- **5**: low complexity relative to its value

## Interpreting the score

### 38–45
Strong abstraction.
It likely fits the problem well and is earning its keep.

### 30–37
Good but worth pressure-testing.
Look for places to shrink the surface area or simplify types.

### 22–29
Borderline.
The abstraction may be partly justified but likely contains decorative complexity.

### Below 22
Overbuilt or misfit.
Re-run the problem framing and choose a lighter structure.

## Final check questions
Before accepting a design, ask:
- Could a union or plain function solve this more simply?
- Does this abstraction hide the right complexity or just move it around?
- Would a new engineer understand the common path quickly?
- Does the design make invalid states harder to represent?
- If the expected variation never arrives, will this still feel reasonable?
