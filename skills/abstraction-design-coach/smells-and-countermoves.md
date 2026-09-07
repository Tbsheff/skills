# Smells and Countermoves

Use this file when reviewing an existing abstraction.

## Smell: class hierarchy for a closed set of domain variants
**Typical symptom**
- `PendingOrder`, `PaidOrder`, `CancelledOrder`
- logic mostly switches on type
- adding cases requires touching many subclasses

**Better move**
- Replace with a discriminated union plus pure functions or focused helpers.

**Why**
- Closed variant sets are easier to reason about, test, and exhaustively handle as data.

---

## Smell: abstract class with little or no shared implementation
**Typical symptom**
- abstract methods only
- subclasses barely share code
- base class exists mostly to feel “OO”

**Better move**
- Replace with an interface or smaller capability interfaces.

**Why**
- Inheritance without meaningful shared implementation is nominal ceremony.

---

## Smell: factory that creates one thing
**Typical symptom**
- `UserServiceFactory.create()` always returns `new UserService(...)`
- no family coordination
- no real selection logic

**Better move**
- Inline construction or use a plain factory function.

**Why**
- A factory should hide meaningful creation complexity or selection, not add a wrapper around `new`.

---

## Smell: multiple factories that mirror dependency injection wiring
**Typical symptom**
- `RepositoryFactory`, `ServiceFactory`, `ControllerFactory`
- each layer mostly forwards dependencies

**Better move**
- Collapse to composition root wiring or a smaller dependency bundle.

**Why**
- Wiring is not the same thing as an abstraction boundary.

---

## Smell: boundary leakage from third-party SDKs
**Typical symptom**
- domain code imports vendor request/response types
- business logic knows transport details
- provider swap would touch broad areas of the codebase

**Better move**
- Add an adapter or facade and map external models to internal semantics.

**Why**
- Boundaries should absorb external weirdness.

---

## Smell: boolean soup
**Typical symptom**
- multiple flags like `isLoading`, `isLoaded`, `hasError`, `isCancelled`
- impossible combinations exist
- behavior is controlled by nested conditionals

**Better move**
- Use a discriminated union or explicit state machine.

**Why**
- State combinations should be constrained by the type model.

---

## Smell: one-off generic parameter
**Typical symptom**
- a type parameter appears once
- callers must pass or infer it but it adds little meaning

**Better move**
- Remove the generic or move the abstraction lower.

**Why**
- Generics are complexity; each one should earn its keep.

---

## Smell: public API depends on clever conditional or mapped types
**Typical symptom**
- consumers see dense utility types
- error messages are hard to read
- the type system becomes the product

**Better move**
- Keep advanced type transformations internal. Export simpler named types.

**Why**
- Public types are part of UX.

---

## Smell: strategy class with no state
**Typical symptom**
- `SortStrategy`, `PriceStrategy`, `ValidationStrategy` classes
- each class just implements one method

**Better move**
- Replace with function strategies or a lookup table of functions.

**Why**
- Behavior variation without identity is usually better modeled as functions.

---

## Smell: over-normalized service layers
**Typical symptom**
- repository → manager → service → provider → client
- each layer adds tiny or unclear value

**Better move**
- Remove or merge layers until each surviving layer has a crisp responsibility.

**Why**
- Layers should absorb real complexity, not distribute confusion.

---

## Smell: pattern stacking
**Typical symptom**
- interface + abstract class + concrete class + factory + singleton
- every pattern exists “just in case”

**Better move**
- Identify the actual change pressure and keep only the pieces that address it.

**Why**
- Patterns are tools, not collectible cards.

---

## Smell: runtime abstraction created for a compile-time-only distinction
**Typical symptom**
- classes introduced mainly to separate static types
- runtime instances have no meaningful lifecycle or behavior

**Better move**
- Use `type`, `interface`, unions, or helper functions instead.

**Why**
- Compile-time distinctions do not require runtime objects.

---

## Smell: domain model mirrors transport layer
**Typical symptom**
- domain entities shaped exactly like HTTP or DB payloads
- transport concerns bleed into business logic

**Better move**
- Map transport models to domain models at the boundary.

**Why**
- The domain should not be handcuffed to storage or transport shape.

---

## Smell: impossible-to-delete abstractions
**Typical symptom**
- touching one layer requires touching six more
- abstractions are referenced everywhere
- nobody knows which one owns what

**Better move**
- Reduce fan-out, shrink public surfaces, and introduce a composition root if needed.

**Why**
- A good abstraction should be easier to change than the thing it replaced.

## General countermoves
When an abstraction smells, try these in order:
1. Inline the abstraction mentally: what real job is it doing?
2. Name the change pressure it is supposed to handle.
3. Remove layers that do not absorb complexity.
4. Replace inheritance with composition where possible.
5. Replace classes with functions or data when state is weak.
6. Replace open-ended extension with a closed union if the domain is actually finite.
7. Add an adapter when the problem is boundary leakage rather than domain complexity.
8. Re-run the beauty rubric before accepting the redesign.
