---
name: writing-architecture-plans
description: Write concise implementation-ready architecture plans and ADRs with human naming, ASCII diagrams, pseudocode, proposed file trees, call stacks, calldiff-style call-flow diffs, API contracts, state/failure models, concurrency and idempotency semantics, rollout steps, testable invariants, and optional standalone HTML output. Use for architecture plans, ADRs, system redesigns, migrations, saga/workflow design, service boundaries, reliability work, and technical implementation planning.
---

# Writing Architecture Plans

## Goal

Produce plans engineers can implement without translating architecture prose into code first.

Use as few words as possible without dropping a decision.

Prefer:

```text
diagram
pseudocode
contract
file tree / call stack / call-flow diff
table
prose
```

Use prose mostly for **why**. Use code-shaped artifacts for **how**.

## Output modes

Default to `markdown`; also support `html` and `both`. Use HTML for visual artifacts, webpages, or explicit HTML requests. HTML must preserve the same decisions, names, contracts, and invariants as Markdown. Read `references/html-output.md`.

## Research first

When repository access exists, inspect the code before designing around it.

Read the smallest useful set:

1. current entry point;
2. state/data model;
3. worker, saga, queue, lock, or transaction primitive involved;
4. idempotency and ownership checks;
5. nearby implementation representing the local pattern;
6. existing names in the area being changed.

Verify behavior from source, not memory.

Do not preserve a bad abstraction merely because the current code uses its name.

## Name the system first

Choose words that describe what a person thinks is happening.

Prefer ordinary nouns:

```text
review chart packet collection run manifest file path task account lease refresh generation
```

Prefer concrete verbs:

```text
create collect build publish open refresh read write start finish retry report acquire release replace
```

Be suspicious of vague verbs:

```text
process handle manage hydrate materialize orchestrate finalize execute sync transform
```

Use one noun for one concept.

Prefer intent-revealing functions:

```ts
collectChart()
startChartCollection()
getChartCollection()
buildReviewPacket()
publishReviewPacket()
refreshReviewPacket()
openReview()
```

If infrastructure vocabulary differs, map it once:

```text
Saga vocabulary        Domain vocabulary
externalRunId      <-> collectionRunId
```

Then use domain vocabulary in the plan.

## Include a naming ledger

For non-trivial designs, show:

```text
Nouns
  review
  chart
  packet

Verbs
  collect
  build
  publish

Functions
  collectChart()
  buildReviewPacket()
  publishReviewPacket()
```

Show meaningful renames:

```text
Current            Proposed
ingest-patient     collect-chart
correlationId      collectionRunId
```

Rename only when it improves meaning, ownership, or behavior.

## State the decision first

Open with one short statement of what changes, then draw it.

```text
create review
    |
    v
 PREPARING
    |
    v
collect chart
    |
    v
build packet
    |
    v
publish + open review
    |
    v
PENDING_REVIEW
```

Do not build suspense before the recommendation.

## Use ASCII first

Use ASCII when it explains structure faster than prose:

- flow;
- ownership;
- state;
- call stacks;
- call-flow diffs;
- request/response;
- concurrency;
- retries;
- refresh;
- rollout.

Keep diagrams terminal-readable and copyable. Do not explain them again line by line.

## Show the proposed file tree

Every implementation-ready plan should show where important code is expected to live.

```text
apps/dashboard/
  lib/core/qa-reviews/
    chart-collection/
      start-chart-collection.ts
    review-packet/
      build-review-packet.ts
      publish-review-packet.ts
```

Use real paths when known. Group by ownership and concept. Avoid invented `utils` layers. Show important new, moved, renamed, and removed files; omit unchanged noise.

## Show call stacks

For non-trivial flows, show the proposed application-level call stack.

```text
createQaChartReview()
  |
  +-- createReview()
  |
  +-- startQaChartReviewSaga()
        |
        +-- collectChartJob()
              |
              +-- startChartCollection()
```

Show only functions that clarify boundaries. Skip framework internals unless they affect correctness.

## Show call-flow diffs

When existing call flow is rewired, show the before/after shape.

Use calldiff semantics plus a presentation-only move marker:

```text
    unchanged
+   added
-   removed
↳   moved / reparented
```

Example:

```text
createQaChartReview()
  |
- ├─ ingestPatient()
+ ├─ collectChart()
+ │  ├─ startChartCollection()
↳ │  └─ reportChartCollection()   MOVED
```

Color is a second channel:

```text
unchanged    muted neutral
added        blue
removed      magenta
moved        amber
boundary     cyan / blue rule
invariant    green annotation
blocked      red
```

Do not use red/green for ordinary add/remove semantics.

When code exists, prefer observed call-flow evidence:

```bash
npx calldiff@latest diff main HEAD --entry createQaChartReview
npx calldiff@latest diff main HEAD --file path/to/entrypoint.ts
npx calldiff@latest diff main HEAD --format json
```

Use structured output for HTML when possible.

Derive `moved` only when the same stable key is removed under one parent and added under another. Never infer a move from similar names.

If the graph is proposed, label it **Proposed call flow**.

Read `references/call-flow-diff.md` for rendering rules.

## Show API contracts

Every cross-service boundary should show the call and smallest useful payload.

```text
Dashboard                         Integrations

POST /chart-collections
--------------------------------------------->
{ collectionRunId, reviewId, patientId }

<---------------------------------------------
202 Accepted
{ collectionRunId, status: "QUEUED" }
```

Show route/RPC name, important fields, result semantics, idempotency identity, and ownership/fencing fields when relevant. Omit incidental payload detail.

## Use pseudocode for correctness

Use pseudocode for transactions, retries, locking, idempotency, fallback, partial failure, publication, and replay.

Use proposed function names. Expose invariants rather than pretending the pseudocode compiles.

Read `references/examples.md` for examples.

## Show state explicitly

If state matters, draw it.

```text
PREPARING
    |
    | packet published
    v
PENDING_REVIEW
    |
    | claimed
    v
IN_PROGRESS
```

State names should answer **what is true right now?**

Separate execution state from business outcome when needed:

```text
Run state:  COLLECTED
Outcome:    READY_WITH_GAPS
```

A valid incomplete result is not an infrastructure failure.

## Choose boundaries by retry cost

Split work when failure should retry only part of the flow.

```text
collect chart
    |
    v
build packet
    |
    v
publish packet
```

If collection succeeds and build fails, retry build, not collection.

## Make concurrency literal

Never write only “ensure concurrency safety.”

Distinguish:

```text
deduplicate same request
        !=
serialize work sharing one account
```

Show what the primitive actually does and the desired behavior. Give different mechanisms different names.

## Make idempotency visible

Use a compact identity map:

```text
review creation       -> idempotencyKey
collection attempt    -> collectionRunId
collection item       -> run + item identity
published file        -> review + logical path
task                  -> review
```

Each durable operation should have one obvious identity.

## Treat gaps as data

Do not model every missing source as workflow failure.

```text
collection
    |
    +---- complete ----------> READY
    +---- optional missing --> READY_WITH_GAPS
    +---- unusable context --> BLOCKED
    +---- system failed -----> FAILED
```

Keep business outcome separate from execution failure.

## Explain failure with arrows

Prefer:

```text
callback fails
    |
    v
retry callback
```

over “the callback should be resilient.”

Include a compact failure map for important systems.

## Show refresh as generation replacement

```text
packet A is live
       |
       | refresh
       v
build packet B
       |
       +---- failure ----> A stays live
       |
       v
publish B
       |
       v
packet B is live
```

Say what happens if a user is actively working against A.

## End with invariants

State rules that can become tests.

```text
1. PREPARING reviews cannot be claimed.
2. No task exists before initial packet publication.
3. Two reviews never share a collectionRunId.
4. Callback failure never causes recollection.
5. Refresh failure never changes the live packet.
6. Active reviews never silently switch packet generation.
```

Avoid soft goals such as “the system should avoid inconsistent state.”

## Rollout as a sequence

```text
1. fix readiness
       |
2. durable collection
       |
3. reliable reporting
       |
4. packet builder
       |
5. atomic publisher
       |
6. shadow
       |
7. pilot
       |
8. remove old path
```

Each phase gets one purpose. Do not invent sprint dates unless asked.

## Default plan shape

Use only sections that help.

For substantial plans, prefer:

```text
# <Decision title>

## Decision
## Why
## Vocabulary
## Naming
## Ownership
## Proposed file tree
## Call stacks
## Call-flow diff
## API contracts
## State
## Data model
## Pseudocode
## Concurrency and idempotency
## Failure model
## Refresh / replay
## Rollout
## Invariants
```

## Editing pass

Remove:

- repeated conclusions;
- throat-clearing;
- generic architecture language;
- unnecessary adjectives;
- explanations already shown by diagrams;
- speculative abstractions without a use;
- names that need a paragraph to explain;
- payloads or code blocks that do not clarify a boundary.

Ask:

> Can an engineer see the implementation and call-flow change without mentally converting prose into code?

Then:

> Would a new engineer guess what each important function does from its name alone?

If not, improve the plan.
