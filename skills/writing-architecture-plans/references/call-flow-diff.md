# Call-flow Diff Design

Call-flow diffs show how who-calls-whom changes across a design or code change.

Use the same base semantics as `calldiff`:

```text
same
added
removed
```

For HTML presentation, add a derived `moved` state when the same stable node key is removed under one parent and added under another.

## Markdown fallback

```text
createQaChartReview()
  |
- ├─ ingestPatient()
+ ├─ collectChart()
+ │  ├─ startChartCollection()
↳ │  └─ reportChartCollection()   MOVED
  |
  └─ startQaChartReviewSaga()
```

Markers always carry meaning:

```text
+  added
-  removed
↳  moved
   unchanged
```

## Color semantics

```text
unchanged    muted neutral
added        blue
removed      magenta
moved        amber
boundary     cyan / blue
invariant    green
blocked      red
gap          amber + explicit GAP label
```

Suggested tokens:

```css
--call-same: #737373;
--call-added: #4f7cff;
--call-added-bg: rgb(79 124 255 / 8%);
--call-removed: #b85ac9;
--call-removed-bg: rgb(184 90 201 / 8%);
--call-moved: #b57913;
--call-moved-bg: rgb(181 121 19 / 10%);
--call-boundary: #4aa3df;
```

Do not use red/green for add/remove. Those colors are reserved for domain status.

## HTML structure

When structured status exists, render semantic rows rather than one generic `<pre>`.

```html
<div class="call-diff">
  <div class="call same">
    <span class="mark"> </span>
    <code>├─ createReview()</code>
  </div>

  <div class="call removed">
    <span class="mark">−</span>
    <code>├─ ingestPatient()</code>
  </div>

  <div class="call added">
    <span class="mark">+</span>
    <code>├─ collectChart()</code>
  </div>

  <div class="call moved">
    <span class="mark">↳</span>
    <code>│  └─ reportChartCollection()</code>
    <span class="annotation">MOVED</span>
  </div>
</div>
```

## CSS

```css
.call-diff {
  font-family: var(--mono);
  font-size: 12.5px;
}

.call {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  gap: 6px;
  padding: 1px 10px;
  border-left: 3px solid transparent;
}

.call.same { color: var(--call-same); }

.call.added {
  color: var(--call-added);
  background: var(--call-added-bg);
  border-left-color: var(--call-added);
}

.call.removed {
  color: var(--call-removed);
  background: var(--call-removed-bg);
  border-left-color: var(--call-removed);
}

.call.moved {
  color: var(--call-moved);
  background: var(--call-moved-bg);
  border-left-color: var(--call-moved);
}
```

## Move pairing

Derive `moved` only from structured data:

```text
same stable key
+
removed under old parent
+
added under new parent
```

Do not infer a move from label similarity.

It is often useful to keep both locations visible:

```text
- ├─ AuthStorage.create()                FROM
+ ├─ getServices()
↳ │  ├─ AuthStorage.create()             MOVED HERE
```

## Boundaries

Service or transaction boundaries are separate from diff status.

```text
Dashboard
  |
+ ├─ startChartCollection()
  |      HTTP boundary
  v
Integrations
+ └─ runChartCollection()
```

Use a subtle rule or label, not an add/remove color.

## Invariant annotations

Annotate only lines where a correctness rule becomes true.

```text
+ ├─ publishReviewPacket()
+ │  ├─ openReview()                 INVARIANT: claimable here
+ │  └─ createChartReviewTask()
```

Keep annotations short.

## Using calldiff

Prefer observed call-flow evidence when code already exists:

```bash
npx calldiff@latest diff main HEAD --entry createQaChartReview
npx calldiff@latest diff main HEAD --file apps/dashboard/path.ts
npx calldiff@latest diff main HEAD --format json
```

Structured nodes expose stable keys and `same | added | removed` status. Child locations are call sites when locations are enabled.

Calldiff is AST-based, not a full typechecker. Dynamic calls may not resolve. Do not present unresolved dynamic dispatch as complete evidence.
