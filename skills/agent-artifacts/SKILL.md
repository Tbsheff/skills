---
name: agent-artifacts
description: Create or update a substantial engineering deliverable as validated semantic JSON, then render it through the Agent Artifacts CLI or MCP into self-contained HTML plus optional durable Markdown. Covers eight kinds - implementation plan, progress report, ADR or design decision, architecture explainer, code or design review, research report, incident report or post-mortem, and engineering handoff. Use whenever the request is for a plan, RFC, design doc, status update, post-mortem, retro, architecture writeup, review verdict, or handoff that a colleague will read and act on - prefer this over hand-authored HTML or freeform Markdown for these eight, because the renderer enforces answer-first structure, provenance, print, and mobile layout that hand-written output silently drops. Do not use for short answers, ordinary notes, code-only replies, or one-off visual artifacts that fit none of the eight kinds.
---

# Agent Artifacts

The agent owns judgment and content. The artifact engine owns structure checks, layout, HTML, Markdown export, and browser verification.

```text
request + evidence
      ↓
semantic JSON contract
      ↓
validate
      ↓
deterministic HTML + optional Markdown
      ↓
check + browser review
```

Never ask the renderer to infer project facts. Never author a recurring artifact as arbitrary HTML.

## Route the request

Read `references/routing.md` when the artifact kind is not obvious.

Supported kinds:

| Kind | Reader needs to |
| --- | --- |
| `plan` | Execute a scoped change in an explicit order |
| `progress` | Understand current state, drift, blockers, and next moves |
| `adr` | Understand a decision, rejected alternatives, and consequences |
| `architecture` | Understand boundaries, ownership, flows, and failure modes |
| `review` | See the verdict and concrete findings first |
| `research` | Understand what the evidence establishes and what remains uncertain |
| `incident` | Understand impact, mechanism, timeline, recovery, and prevention |
| `handoff` | Resume work without replaying the full history |

Use ordinary Markdown instead when the answer is short, linear, or primarily maintained by hand.

## Default workflow

1. **Lock the reader outcome.** Infer the artifact kind, decision needed, scope, and what counts as complete. Ask at most one compact question only when missing information would materially change the artifact.
2. **Gather evidence.** Read the relevant code, docs, logs, commits, issue history, or user-provided material. Record the exact source locations and revisions that support important claims. Read `references/evidence.md`.
3. **Load only the relevant kind guidance.** Read the matching section in `references/artifact-kinds.md`, plus `references/writing.md`. Read `references/diagrams.md` when a mechanism or flow needs a figure. Read `references/code-shaped.md` before writing any implementation-facing artifact. Read `examples/<kind>.json` for a validated contract of that kind - read it for field shape and sentence length, not for which optional blocks to include and not for framing. All eight are one scenario under one title. The incident example is a refactor wearing a SEV-3, and its capitalised nouns are template tokens, not project names.
4. **Create semantic JSON.** Create the bundle directory first, then scaffold into it: `mkdir -p .agent-artifacts/<kind>/<slug> && agent-artifacts new <kind> <title> -o .agent-artifacts/<kind>/<slug>/contract.json`, or use the `artifacts_get_contract` MCP tool. Without `-o`, `new` writes `<slug>.<kind>.json` into the current directory. Use the same slug `new` would: the title, lowercased, with non-word runs collapsed to hyphens. Then `cd` into that directory; steps 5 through 7 run from there with bare filenames.

   Run `agent-artifacts schema <kind>` and read `required`, every `enum`, and every `maxLength` before you edit, including inside `$defs`, where `summary`, `source`, and `metric` live as `$ref`s, so the top-level property list shows none of their rules. `metrics[].label` is capped at 40 characters, far tighter than the 45-word budget in `references/writing.md`. Then:

   - **Delete every optional field, then add back only what you can cite.** The scaffold is a shape, not a draft. Every sentence in it is filler that passes all three gates unchanged.
   - **Keep every required field.** Eight to twelve per kind. A required field with nothing real to say means you are missing evidence, not that the field should go. `review.findings` is the one required array with no `minItems`: `"findings": []` passes validate, render, and check with zero warnings. Count your own findings.
   - **Replace every invented value.** `adr_id` and `incident_id` ship as `ADR-DRAFT` and `INC-DRAFT`; number a new record from the highest existing id in the project, or `ADR-001` when there is none. `progress.completion` ships as `35` and is worse: it is a required integer, any value 0-100 passes all three gates with zero warnings, and it renders as the largest number on the page. Derive it from something countable - milestones closed over milestones planned - and say what you counted in `summary.context`. If nothing is countable, say so there; a number you cannot defend is the most-read lie in the artifact.
   - **Read the finished contract top to bottom.** The gates cannot tell scaffold from evidence. Grepping for `Replace`, `Draft`, `TODO`, `TBD`, and `example` matches 3 or 4 fields out of the 31 to 84 a scaffold ships. It will not find `owner: "Project team"`, `next_steps[].owner: "Artifact engine owner"`, `files[].path: "src/agent_artifacts/engine.py"`, or `decisions[].reference: "research/architecture.md"` - this repository's own facts, all of which validate, render, and check clean.

   Fill semantic fields only. Do not add layout, colour, component, column, width, or position fields.
5. **Validate before rendering.** Run `agent-artifacts validate <contract.json> --strict` or `artifacts_validate`. Fix every error. Resolve every warning. `render --strict` in step 6 raises before it writes, so one surviving warning exits 2 and leaves you with no HTML and no Markdown. If a warning names uncertainty you mean to keep, drop `--strict` from the render command and name the standing warning in the delivery. Read `references/workflow.md` for the semantic checks that strict validation applies beyond the schema.
6. **Render through the engine.** Run `agent-artifacts render contract.json --strict -o index.html --markdown artifact.md`, or `artifacts_render`. Without `-o`, render writes `contract.html`, and step 7 will not find `index.html`. The engine, not the model, creates the HTML.
7. **Verify the artifact.** Run `agent-artifacts check index.html --source contract.json --strict`. For substantive or user-facing work, run `agent-artifacts review index.html --source contract.json --out-dir review` and inspect desktop plus mobile output. Read `references/validation.md`.
8. **Sync durable conclusions.** Keep accepted decisions and lasting project state in Markdown or the project’s established source of truth. HTML is the review surface. Read `references/markdown-sync.md`.
9. **Deliver the result.** Return the HTML path first, then the durable Markdown path when one exists. Mention unresolved questions, degraded checks, or missing evidence plainly.

## Output location

Unless project rules say otherwise, write one artifact bundle:

```text
.agent-artifacts/<kind>/<slug>/
  contract.json   semantic source
  index.html      generated review surface
  artifact.md     durable or portable text representation
  review/
    desktop.png
    mobile.png
    review.json
```

Do not scatter generated files across the repository root.

## Updating an existing artifact

Most kinds are revisited: progress reports get refreshed, handoffs get amended, ADRs get superseded. Look for an existing bundle before creating one.

```bash
ls .agent-artifacts/<kind>/
```

When one exists, edit its `contract.json` in place and keep the slug. The slug is the artifact's identity. A second directory splits the history and leaves stale HTML that readers cannot tell apart from the current one. Set `updated` to today, leave `date` at the original creation date, and re-run validate, render, and check. The `review/` images regenerate; do not keep the old ones.

An ADR is the exception. A decision that changes is a new record, not an edit: create a new slug, set the old contract's `decision_status` to `superseded`, list the old ADR's id in the new contract's `supersedes`, and point each at the other through `related`. Set `decision_status`, not `status` - `status` is free text the gates ignore. An `accepted` ADR marks exactly one entry in `alternatives` with `"selected": true`; every other entry needs `rejected_because`.

## Content rules

Lead with the answer. Compare the two openings below.

Weak, because it restates the title and commits to nothing:

> This plan describes our approach to improving the authorization architecture and outlines the milestones required to deliver it.

Useful, because it states the change, the mechanism, and the cost:

> Authorization moves into session lookup, so a controller cannot forget it. Twelve controllers lose their inline checks; two of them authorize on a resource the session does not bind, and those need a decision before M3.

If a sentence could appear in another project's artifact unchanged, it carries no information. Delete it.

Four rules decide whether the artifact is worth reading:

- **Answer first.** `summary.answer` carries the approach, the verdict, the decision, the status, the impact, or the handoff state. Not a description of the document.
- **Code-shaped over prose.** Reach in this order: ASCII diagram, pseudocode, API contract, file tree, call stack, call-flow diff, table, prose. Prose is for why. An implementation-facing artifact that contains only prose has not done its job.
- **Name the mechanism.** "Scalability risk" is a category. "When the vendor returns 500 the worker retries without a cap, so one poisoned job holds the queue for the whole org" is a finding. Same test for every risk, failure mode, and review finding.
- **Empty beats filler.** The renderer drops an empty field. It renders a filler one. Leave it empty.

The rest follow from those four:

- Use ordinary nouns and concrete verbs. `process`, `handle`, `manage`, and `orchestrate` name nothing.
- Never invent a citation, file path, metric, date, or implementation state. When an action or question needs an owner and the project names none, write the role that must act (`whoever owns src/agent_artifacts/browser.py`), not a person or a team you made up. Top-level `owner` is optional; delete it rather than guess.

`references/writing.md` and `contracts/field-guide.md` carry the sentence-level rules.

## Tool boundary

Use the CLI when working locally in a repository. Use MCP when the host exposes the Agent Artifacts server or when a shared service should centralize the renderer.

The MCP server is intentionally thin. Call it with a completed semantic contract, not a raw request. Prefer:

```text
agent reasoning → artifacts_validate → artifacts_render → artifacts_check_html
```

Never use:

```text
raw user prompt → “make_plan” server-side agent
```

Read `references/cli-and-mcp.md` for exact commands and tool order.

## Completion standard

A completed artifact passes validate, render, and check; leads with the reader's answer; carries no scaffold sentence, placeholder, or presentation field, which the gates do not detect and you find by reading the contract back; and cites at least one real source. No gate opens a cited file: `sources[].location`, `sources[].revision`, `findings[].evidence`, and `metrics[].value` are free strings, so a line range past the end of a file and a commit that does not exist both render as confident provenance. Paste each location back into your shell before you deliver. `sources: []` raises `content.sources-missing` on architecture, research, review and incident, and passes on the other four - where it still means the artifact is unevidenced. `references/validation.md` lists what to look for in the rendered page.

When the engine is unavailable, deliver the semantic JSON contract and state that rendering and browser checks were not run. Do not replace the missing engine with improvised HTML.
