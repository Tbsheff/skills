# Code-shaped blocks

Every block here is available on all eight kinds. Seven kinds treat all of them as optional; `architecture` requires `invariants` with at least one entry. All are semantic: you record meaning, the engine draws it.

Read this first, because it is where these blocks usually break:

- **Never hand-indent.** Not `path` in `file_tree`, not `call` in `call_stacks` or `call_flow`. Set `depth` and let the engine draw the box glyphs, close the last sibling with the corner glyph, and align the markers. Hand-indented strings render as double-indented garbage.
- `depth` starts at 0 in `file_tree` and at 1 in `call_stacks` and `call_flow`.
- `status` in `call_flow` is one of `same`, `added`, `removed`, `moved`. Derive `moved` only when the same stable key is removed under one parent and added under another. Never infer a move from similar names. A rename is a remove plus an add.
- Container shapes: `call_stacks`, `pseudocode`, and `api_contracts` are arrays. `call_flow`, `naming`, and `file_tree` are single objects. `invariants` is an array of strings.
- The engine owns colour. Added is blue, removed is magenta. Moved rows carry strong ink and the `↳` marker, boundary rows carry a rule, and neither takes a tint. Green, amber, and red stay reserved for domain status, so add and remove never read as good and bad. Do not request colour anywhere in the contract.

## naming

A naming ledger. Show the words before the code. Verbs come first: the action names the concept.

```json
{
  "verbs": ["collect", "build", "publish"],
  "nouns": ["review", "chart", "packet"],
  "functions": ["collectChart()", "buildReviewPacket()"],
  "renames": [{"current": "ingestPatient()", "proposed": "collectChart()", "why": "The name says what the call does."}],
  "mapping": [{"external": "externalRunId", "domain": "collectionRunId"}]
}
```

Rename only when it improves meaning, ownership, or behavior.

## file_tree

Where the code is expected to live. Show new, moved, changed, and removed entries. Omit unchanged noise.

Set `depth` per entry. The engine draws the box-drawing glyphs, closes the last sibling with `└─`, and picks the change marker. Never hand-indent `path`.

```json
{"entries": [{"path": "lib/review-packet/", "depth": 0},
             {"path": "publish-review-packet.ts", "depth": 1, "change": "new", "note": "atomic"},
             {"path": "ingest-patient.ts", "depth": 1, "change": "removed"}]}
```

Markers: `+` new, `-` removed, `~` changed, `↳` moved.

## call_stacks and call_flow

`call_stacks` holds at most 6 stacks. `call_flow` shows how who-calls-whom changes and renders with a legend. Shapes are listed at the top of this file.

```json
[{"entry": "createQaChartReview()", "note": "Proposed. Not observed from a build.",
 "calls": [{"call": "ingestPatient()", "depth": 1, "status": "removed"},
           {"call": "collectChart()", "depth": 1, "status": "added", "boundary": "HTTP boundary"},
           {"call": "reportChartCollection()", "depth": 2, "status": "moved", "annotation": "MOVED"}]}]
```

`note` records whether the graph is observed or proposed.

When the code exists, prefer observed evidence:

```bash
npx calldiff@latest diff main HEAD --entry createQaChartReview --format json
```

If the graph is proposed, say so in `note`.

## api_contracts

One block per cross-service boundary. Route, smallest useful payload, result semantics, and the idempotency identity.

```json
[{"call": "POST /chart-collections", "caller": "Dashboard", "callee": "Integrations",
 "request": "{\n  \"collectionRunId\": \"uuid\"\n}",
 "response": "202 Accepted\n{\n  \"status\": \"QUEUED\"\n}",
 "idempotency": "collectionRunId"}]
```

## pseudocode

Use it for transactions, retries, locking, idempotency, fallback, partial failure, and replay. Use proposed function names. Expose the invariant rather than pretending it compiles.

```json
[{"title": "Publish", "language": "ts",
  "code": "async function publishPacket(id) {\n  const lock = await claim(id)\n  if (!lock) return alreadyRunning()\n  await writePacket(id)\n  await release(lock)\n}",
  "annotations": [{"line": 3, "text": "atomic boundary"}]}]
```

Languages: `ts`, `tsx`, `json`, `sql`, `prisma`, `bash`, `diff`, `yaml`, `python`, `text`.

## invariants

Rules that can become tests. Numbered by the engine.

```json
["PREPARING reviews cannot be claimed.",
 "Two reviews never share a collectionRunId.",
 "Refresh failure never changes the live packet."]
```

Avoid soft goals such as "the system should avoid inconsistent state."
