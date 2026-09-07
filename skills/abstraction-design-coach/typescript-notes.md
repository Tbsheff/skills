# TypeScript Notes

Use this file when the problem is specifically about TypeScript.

## The central rule
In TypeScript, the most elegant abstractions are often built from:
- object shapes
- discriminated unions
- helper functions
- small interfaces at boundaries
- light factory functions

Do not default to class hierarchies just because classic design-pattern literature does.

## Type-level vs runtime abstractions

### Type-level abstractions
Examples:
- `type`
- `interface`
- mapped types
- conditional types
- generic utilities

These help the compiler and developer experience.
They do **not** create runtime behavior.

### Runtime abstractions
Examples:
- objects with real state
- service wrappers
- caches
- adapters
- resource-owning classes
- plugin registries
- state machines

These exist in the executing program.

Always separate these two questions:
1. What shape should the compiler understand?
2. What object or behavior should exist at runtime?

## TypeScript-native best practices

### Prefer `unknown` to `any` at trust boundaries
Use `unknown` for:
- parsed JSON
- HTTP input
- environment variables
- message payloads
- external SDK results

Narrow or validate before use.

### Prefer unions over overloads when practical
If multiple inputs produce the same shape of output, unions often yield simpler APIs and better maintainability.

### Prefer `interface` for open contracts
Use `interface` when:
- callers depend on capabilities
- implementations can vary
- the contract may evolve or be extended

### Prefer `type` for compositions
Use `type` for:
- unions
- intersections
- utility compositions
- branded patterns
- computed type expressions

### Use `satisfies` to preserve inference
When checking object literals against a shape, `satisfies` is often better than explicit annotation because it preserves narrower inferred property types.

### Keep generics small
Each generic parameter should:
- relate multiple values
- improve inference or correctness
- materially help the consumer

If it appears only once, question it.

### Avoid exporting cleverness
A dense internal utility type may be fine.
A dense public utility type is user-facing complexity.

### Use exhaustive checks
For discriminated unions, use `never` in default branches to ensure new cases are handled.

## Typical TypeScript recommendations by problem

### “We have many status booleans”
Use a discriminated union.

### “We need to support multiple providers”
Use a small interface plus adapters. Add a factory only if runtime selection or construction complexity justifies it.

### “We have a bunch of strategy classes”
Use function strategies unless the strategies have state or lifecycle.

### “We have a base class and many subclasses”
Ask whether the domain is actually a closed union or whether the shared behavior should be extracted into helpers/composition.

### “We need a plugin system”
Use explicit runtime registries, capability interfaces, and validation. Do not mistake generic type parameters for a plugin architecture.

### “We need strong typing for API data”
Add runtime validation at the boundary and map external data to internal domain types.

## Common traps

### Trap: believing type safety equals runtime safety
It does not. TypeScript erases types.

### Trap: using classes to model every distinction
Many distinctions are better represented as data or unions.

### Trap: exporting internals
Public type machinery should be simpler than internal machinery, not more complicated.

### Trap: abstracting before the second pressure signal
A possible future variant is not always enough to justify a new layer today.

## Rule of thumb
If the design feels “impressive” but the call site becomes less obvious, the abstraction is probably losing the plot.
