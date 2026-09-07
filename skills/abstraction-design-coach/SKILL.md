---
name: abstraction-design-coach
description: Help design, review, simplify, and refactor software abstractions, especially in TypeScript and JavaScript.
---

# Abstraction Design Coach

## What this skill does
Use this skill when the user wants help designing, reviewing, simplifying, or refactoring a software abstraction.

This skill is optimized for TypeScript and JavaScript, but it also works for general software design questions.

The skill helps:
- choose the right abstraction level for a problem
- decide whether a pattern is warranted or overbuilt
- separate compile-time types from runtime architecture
- design boundaries that are easy to change, test, and understand
- produce code sketches and migration plans that are practical, not ceremonial

## When to use this skill
Use this skill when the user is:
- evaluating whether an API, service, class hierarchy, or pattern is elegant or overengineered
- designing domain models, extension points, infrastructure boundaries, or plugin systems
- choosing between unions, interfaces, functions, classes, factories, abstract factories, adapters, facades, decorators, strategies, builders, and state machines
- refactoring class-heavy or generic-heavy code into clearer architecture
- trying to make abstractions more maintainable, more idiomatic, or more resilient to change

Do not use this skill for:
- low-level algorithm optimization unrelated to architecture
- purely stylistic naming debates without a design problem
- framework-specific setup unless the main question is still about abstraction design

## Primary design philosophy
- The simplest viable abstraction is usually best.
- Abstractions should be justified by change pressure, not by pattern prestige.
- Good abstractions reduce the cost of future change without hiding the truth of runtime behavior.
- A type-level abstraction is not automatically a runtime abstraction.
- Favor plain data and functions until identity, lifecycle, or stateful behavior truly require more structure.
- Prefer composition over inheritance unless inheritance removes duplication without obscuring behavior.
- Make invalid states hard to represent.
- Keep public APIs smaller than internal implementations.
- An abstraction that no longer pays rent should be simplified or deleted.

## Core lenses
Always analyze the problem through these lenses:

### 1) Change lens
- What is likely to change?
- What should remain stable?
- Where is the volatility: domain rules, vendors, workflows, construction, lifecycle, or integrations?

### 2) Openness lens
- Is the set of variants closed or open?
- Are new cases expected often?
- Who owns the extension point: the application, users, plugins, or third-party systems?

### 3) Runtime lens
- Does this abstraction need a real runtime object?
- Does it need identity, state, lifecycle, caching, resource management, or polymorphic behavior at runtime?
- Or is the abstraction compile-time only?

### 4) Ergonomics lens
- Is the call site clear?
- Will the common path feel obvious?
- Does the design preserve inference and readable errors?
- Is the public surface area minimal?

### 5) Boundary lens
- Is the problem internal modeling, an external boundary, behavioral variation, construction complexity, or lifecycle/state management?
- Are vendor types, transport details, or framework APIs leaking into the core domain?

## Default abstraction ladder
Evaluate options in this order. Stop when a simpler option fully satisfies the problem.

1. Keep the code concrete as-is.
2. Plain data + plain functions.
3. Discriminated union.
4. Small interface + implementation object.
5. Wrapper or factory function.
6. Class.
7. Multiple cooperating classes.
8. Pattern combination such as adapter + interface, facade + factory, or state machine + union.
9. Abstract factory or plugin architecture.
10. A larger pattern stack only if the change pressures are strong and specific.

Never skip directly to a heavyweight pattern without first ruling out simpler options.

## Preferred pattern guidance

### Discriminated unions
Prefer when:
- the domain has a finite set of cases
- behavior branches by kind, status, or stage
- exhaustive handling is valuable
- the goal is modeling state, messages, commands, workflow stages, AST nodes, or events

Avoid when:
- the set of cases is genuinely open and externally extensible
- each instance needs meaningful identity or rich encapsulated mutable state

### Interfaces
Prefer when:
- you need an open contract at a boundary
- different implementations can satisfy the same capability
- the caller should depend on behavior, not construction details
- you are isolating storage, HTTP, payments, queues, email, analytics, or feature flags

Avoid when:
- there is only one meaningful implementation and no boundary pressure
- an interface is added only to make the code “look enterprise”

### Plain functions
Prefer when:
- behavior is the main axis of variation
- strategies are stateless or lightly stateful
- wrapping or composition simplifies logging, retry, metrics, validation, caching, or authorization
- object identity is not important

### Classes
Prefer when:
- the abstraction needs identity, encapsulated mutable state, lifecycle, or instance methods
- invariants must be protected across operations
- the object owns resources or long-lived internal state
- a runtime object is part of the actual design

### Abstract classes
Use sparingly. Prefer only when subclasses truly share implementation and must conform to required hooks.
Do not use them just to imitate nominal typing.

### Factory functions
Prefer when:
- creation logic is nontrivial
- defaults, dependency injection, or hidden implementation details matter
- object literals or constructors would leak too much

### Abstract factory
Prefer when:
- the system must choose a *family* of compatible implementations at runtime
- collaborators produced together must match each other
- the client should remain unaware of concrete implementations

Typical cases:
- prod vs test infrastructure bundles
- browser vs server service families
- region-specific formatting/policy bundles
- coordinated renderer families

Do not use abstract factory just because there are “multiple classes.”

### Adapter / Facade
Prefer when:
- an external SDK or subsystem leaks complexity
- you want a smaller internal contract than the vendor API
- you want to isolate churn, vendor lock-in, or transport details
- you need stable internal semantics around unstable external interfaces

### Strategy
Prefer when:
- the same job can be done by interchangeable algorithms
- the selection logic should be decoupled from the caller

Use function-based strategies first.
Upgrade to class-based strategies only when state, lifecycle, or partial shared implementation justify them.

### Builder
Prefer when:
- construction is staged
- ordering matters
- some intermediate states must be impossible
- defaults and validation are complex enough that literals or constructors become error-prone

Avoid when:
- a plain object or factory function is sufficient

### State / state machine
Prefer when:
- behavior depends on current mode or lifecycle stage
- valid transitions are meaningful
- the code otherwise grows conditionals around multiple status flags
- boolean soup or invalid combined states are causing bugs

## TypeScript-specific rules
For TypeScript and JavaScript questions, strongly prefer:
- plain objects, unions, and functions before class hierarchies
- `unknown` at trust boundaries; narrow before use
- unions over overloads when return types do not fundamentally differ
- `interface` for open object contracts and `type` for unions/type composition
- `satisfies` when validating object shape while preserving inference
- exhaustive `switch` handling with `never` checks
- small generic surfaces
- avoiding type parameters that appear only once
- separating static typing from runtime validation
- avoiding `any` except as a deliberate, contained escape hatch
- keeping clever conditional and mapped types mostly internal unless they materially improve the API

See `typescript-notes.md` and `examples.md` for detailed reference.

## Workflow

### Step 1: Restate the real problem
Translate the user’s description into:
- what changes
- what stays stable
- where the coupling pain is
- whether the pressure is domain, boundary, construction, behavior, or lifecycle related

### Step 2: Classify the abstraction problem
Decide which category dominates:
- domain modeling
- external boundary / integration
- behavioral variation
- construction / assembly
- lifecycle / state transitions
- plugin / extension surface

If more than one category applies, identify the primary one and any secondary ones.

### Step 3: Separate compile-time from runtime
Explicitly state:
- which concerns are type-only
- which require runtime objects or runtime validation
- whether the current design is mixing these concerns

### Step 4: Identify the simplest viable candidate
Walk the abstraction ladder from simplest to more complex.
For each plausible candidate, ask:
- does it solve the actual change pressure?
- does it reduce coupling?
- does it preserve call-site clarity?
- does it make the system easier to change or only more abstract?

### Step 5: Choose one recommended design
Recommend one primary design.
State:
- the abstraction or pattern to use
- why it fits this problem
- what it intentionally does *not* abstract
- why simpler options fall short
- why heavier options are unnecessary

### Step 6: Produce code
Show a TypeScript sketch when possible, using realistic names.
The code should:
- reflect the recommendation clearly
- avoid placeholder architecture
- show the public surface, not just internals
- be runnable or nearly runnable

### Step 7: Compare alternatives
Compare 1–3 plausible alternatives:
- one simpler
- one heavier
- optionally one lateral alternative

Explain tradeoffs honestly.

### Step 8: Review for smells
Use `smells-and-countermoves.md` as a checklist.
Identify any issues such as:
- abstract patterns without real pressure
- boundary leakage
- invalid states
- hidden runtime assumptions
- overgeneric APIs
- unnecessary layering

### Step 9: Score the beauty of the abstraction
Use `beauty-rubric.md`.
Assess:
- fit to problem
- API surface
- call-site ergonomics
- runtime honesty
- change isolation
- testability
- deletion friendliness
- overengineering risk

### Step 10: Give a practical next move
End with one actionable conclusion:
- keep current design
- simplify current design
- refactor in phases
- redesign the boundary now
- split one abstraction into two smaller ones

## Required output format
Unless the user asks for a different format, respond with:

### Recommendation
A concise statement of the best abstraction choice.

### Why this fits
Tie the recommendation to the user’s actual change pressures.

### Proposed shape
Explain the public-facing design in plain language.

### TypeScript sketch
Show realistic example code.

### Alternatives considered
Compare 1–3 alternatives and explain why they are weaker or heavier here.

### Tradeoffs
State the cost of the recommended design.

### Migration path
If the user is refactoring existing code, provide phased steps.

### Beauty check
Give a short final verdict on:
- surface area
- inference / ergonomics
- runtime clarity
- extensibility
- overengineering risk

## Quality bar
Before finalizing, verify that the answer:
- picks the lightest abstraction that actually solves the problem
- distinguishes compile-time and runtime concerns
- prefers composition over inheritance unless inheritance is clearly justified
- avoids recommending patterns by reputation alone
- explains why the chosen design is better than both simpler and heavier alternatives
- includes practical code
- minimizes unnecessary generics and layering
- does not use `any` without explicit justification
- tells the user what to do next, not just what to think

## Behavior when information is missing
Do not stall on missing details.
Infer a reasonable design and explicitly mark assumptions.
If crucial context is missing, provide:
- a best-fit recommendation under stated assumptions
- the main ways the recommendation would change if those assumptions are false

## Support files
Use these files as references:
- `decision-matrix.md` for fast pattern selection
- `smells-and-countermoves.md` for code review and refactoring guidance
- `examples.md` for canonical before/after patterns
- `beauty-rubric.md` for final evaluation
- `typescript-notes.md` for TS-native guidance

## Example invocation
User:
“We have a hierarchy of `PaymentProcessor` classes, plus two layers of factories. We want to support Stripe, PayPal, and a test double. Is this elegant or overbuilt?”

Expected behavior:
- determine whether the problem is boundary design, runtime family selection, or unnecessary factory layering
- compare unions, interfaces, factory functions, and abstract factory
- recommend the simplest viable design
- show idiomatic TypeScript
- give a phased migration plan
