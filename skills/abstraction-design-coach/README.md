# Abstraction Design Coach

A reusable skill for designing, reviewing, simplifying, and refactoring software abstractions.

## Primary target
- TypeScript / JavaScript application and library design
- Service boundaries, SDK wrappers, domain models, APIs, workflows, and runtime architecture
- General software abstraction questions when no language is specified

## Included files
- `SKILL.md` — core workflow and rules
- `decision-matrix.md` — fast lookup for which abstraction fits which problem
- `smells-and-countermoves.md` — review guide for overengineering and weak abstractions
- `examples.md` — worked examples with idiomatic TypeScript
- `beauty-rubric.md` — final scoring rubric for abstraction quality
- `typescript-notes.md` — TypeScript-native guidance for runtime vs compile-time design

## Design goal
Help the model recommend the *simplest abstraction that satisfies the actual change pressures*.

This skill should bias toward:
- clear public APIs
- explicit runtime behavior
- strong inference
- invalid states being hard to represent
- composition over inheritance
- adapters around external complexity
- avoiding pattern cargo cults

## Key idea
An abstraction is “good” when it pays rent:
- it makes change easier,
- reduces coupling,
- preserves clarity at call sites,
- and does not introduce speculative complexity.
