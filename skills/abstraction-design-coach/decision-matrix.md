# Decision Matrix

Use this file as a fast lookup for which abstraction usually fits which kind of problem.

| Situation | Usually prefer | Avoid by default | Why |
|---|---|---|---|
| Finite domain variants (`pending`, `paid`, `failed`) | Discriminated union | Class hierarchy | Closed sets are modeled naturally and exhaustively with unions. |
| Open implementation boundary (`EmailClient`, `PaymentGateway`) | Small interface + adapter | Abstract class | Interfaces fit open contracts without forcing inheritance. |
| Stateless interchangeable behavior | Function strategy | Strategy class hierarchy | Functions compose more simply and read better at the call site. |
| Cross-cutting concerns (logging, retry, metrics, caching) | Wrapper / higher-order function | Deep decorator stacks | Simple wrapping often gives the same value with less ceremony. |
| Complex third-party SDK or subsystem | Facade or adapter | Leaking vendor types into domain | Internal code should depend on stable semantics, not vendor churn. |
| Nontrivial creation with defaults / DI | Factory function | Factory class unless justified | Most creation logic does not need class-based factories. |
| Runtime-selected bundle of compatible services | Abstract factory or dependency bundle | Independent ad hoc creation everywhere | Coordinated families are the real use case for abstract factory. |
| Lifecycle-dependent behavior | State machine / state object | Boolean flags plus conditionals | State transitions deserve explicit modeling. |
| Rich object identity and encapsulated mutable state | Class | Plain bag-of-functions when state is central | Runtime identity is one of the real reasons classes exist. |
| Staged construction with invariants | Builder | Giant mutable config objects | Builder is justified when order and partial validity matter. |
| One concrete implementation, no boundary pressure | Concrete code | Interface + factory + service stack | Do not abstract preemptively. |
| Type-level transformation only | `type`, mapped/conditional types | Runtime architecture changes | Keep type-level complexity out of runtime design decisions. |
| Runtime validation of unknown input | Parser/validator + domain mapping | Trusting static types alone | Types do not validate external data at runtime. |
| Vendor-specific formatting / policy bundles by region | Abstract factory or strategy bundle | `if` trees scattered everywhere | Centralizing coordinated variation reduces drift. |

## Quick choice rules

### Choose a discriminated union when:
- the cases are known
- the behavior branches by case
- invalid combinations should be impossible

### Choose an interface when:
- callers should depend on capabilities
- implementations may vary independently
- the boundary matters more than the implementation

### Choose a function when:
- behavior varies, not identity
- you want easy composition
- state is minimal or absent

### Choose a class when:
- the instance has durable state or lifecycle
- identity matters
- runtime behavior belongs to the object

### Choose a factory function when:
- construction is the main problem
- you want defaults or hidden internals
- “new” at the call site would reveal too much

### Choose abstract factory when:
- a *family* of implementations must stay compatible
- selection happens at runtime
- multiple collaborators should be chosen together

## Tie-breakers

If two options both seem workable:
1. pick the one with the smaller public API
2. pick the one with clearer call-site ergonomics
3. pick the one that preserves better inference
4. pick the one with less speculative extensibility
5. pick the one that is easier to delete or simplify later

## Red flags
These often indicate the abstraction is too heavy:
- multiple layers of factories with only one real variant
- abstract base classes with empty or trivial shared behavior
- runtime classes created only to satisfy a type-level distinction
- generic APIs that require explicit type arguments at normal call sites
- exported utility types more complex than the code they describe
