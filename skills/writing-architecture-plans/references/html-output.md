# HTML Output Mode

HTML is a first-class architecture output.

Produce one standalone HTML file with no required external dependencies.

Do not merely wrap Markdown in `<article>`.

## Page shape

```text
header
  title
  status
  one-line decision

nav
  overview
  code shape
  contracts
  correctness
  rollout

main
  decision
  end-to-end flow
  ownership
  naming
  proposed file tree
  call stacks
  call-flow diff
  API contracts
  state
  data model
  pseudocode
  failure map
  rollout
  invariants
```

## Visual priorities

Use:

```text
ASCII / CallDiff
pseudocode
API contracts
file trees / call stacks
tables
prose
```

Keep prose width narrower than diagram/code width.

Use system sans-serif for prose and monospace for code-shaped material.

## Syntax highlighting

Support at least:

```text
ts / tsx
json
sql
prisma
bash
diff
yaml
text
```

Highlight syntax for readability, not decoration.

For correctness-sensitive pseudocode, allow line emphasis and short annotations such as:

```text
atomic boundary
precondition
becomes claimable
```

## Semantic callouts

Use a small vocabulary:

```text
DECISION
INVARIANT
WARNING
BREAKING
NEW
CHANGED
REMOVE
```

Color must never be the only signal.

## CallDiff

Call-flow diffs are a first-class primitive.

Use:

```text
+   added      blue
-   removed    magenta
↳   moved      amber
    unchanged  muted neutral
```

Use structured rows when status is available. Keep `+`, `-`, and `↳` visible.

Read `call-flow-diff.md` for the full primitive and tokens.

## ASCII diagrams

Keep ASCII diagrams as ASCII unless the user explicitly asks for graphical SVG/canvas diagrams.

ASCII is portable, copyable, diffable, and Markdown-friendly.

## API contracts

Render service calls as horizontal request/response blocks on wide screens and stack them on mobile.

Keep the route, direction, request, and response visible together.

## Naming

Show a visible naming ledger with nouns, verbs, and functions.

Show meaningful renames in a compact current/proposed/why table.

## File tree

Place the proposed file tree near the top of implementation detail.

Annotate important entries when useful:

```text
publish-review-packet.ts   # new
ingest-patient.ts          # remove
```

## Pseudocode

Use monospace syntax-like formatting.

Label it `Pseudocode` so nobody confuses it with copy-paste implementation.

## Color semantics

Reserve colors by meaning:

```text
blue       boundary / decision / added call
magenta    removed call
amber      moved call / gap (with explicit label)
green      valid / committed / invariant
red        blocked / failed
neutral    unchanged context
```

Do not give every section a different color.

## CSS direction

Prefer an internal technical-document look:

- 1100–1300px page width;
- 720–800px prose width;
- clear section separators;
- subtle borders;
- no gradients;
- no glassmorphism;
- no marketing hero treatment;
- readable print output.

JavaScript is optional. Useful features are section navigation, collapse/expand, copy code, and theme toggle.

The document must remain readable without JavaScript.
