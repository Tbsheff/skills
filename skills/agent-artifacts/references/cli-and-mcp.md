# CLI and MCP

## CLI

From an installed package:

```bash
agent-artifacts kinds
agent-artifacts schema <kind>     # prints the full JSON Schema; read "required", every "enum", and every "maxLength"
agent-artifacts doctor            # reports whether Chromium is available for the browser gate
agent-artifacts new plan "Move authorization into session lookup" -o contract.json
agent-artifacts validate contract.json --strict
agent-artifacts render contract.json --strict -o index.html --markdown artifact.md
agent-artifacts check index.html --source contract.json --strict
agent-artifacts review index.html --source contract.json --out-dir review
```

From a source checkout or copied skill, use the wrapper:

```bash
python3 <skill-dir>/scripts/artifact.py kinds
```

The wrapper uses an installed `agent-artifacts` executable when available and otherwise finds the engine in the repository checkout.

## MCP

The stdio adapter exposes:

- `artifacts_list_kinds`
- `artifacts_get_contract`
- `artifacts_validate`
- `artifacts_render`
- `artifacts_render_file`
- `artifacts_check_html`
- `artifacts_screenshot`
- `artifacts_doctor`

Recommended order:

```text
artifacts_get_contract
→ author semantic JSON
→ artifacts_validate
→ artifacts_render
→ artifacts_check_html
→ artifacts_screenshot
```

The adapter supports the current stateless MCP protocol and initialize-based legacy clients. Every file operation is confined to `AGENT_ARTIFACTS_ROOT`; set it to the repository or workspace that may receive generated files.

Do not send a raw user request to the renderer. The skill and calling agent own research, classification, and judgment.

## Closed enums

Shared by all eight kinds:

`summary.confidence`: `high`, `medium`, `low`.
`source.kind`: `file`, `url`, `code`, `data`, `interview`, `observation`, `other`. A commit, log line, issue, or metric is `code`, `observation`, `other`, or `data`; put the real identifier in `location`.
`action.status`: `todo`, `doing`, `done`, `blocked`.
`question.status`: `open`, `answered`, `deferred`.
`file_tree.entries[].change`: `new`, `changed`, `moved`, `removed`, `unchanged`.
`call_stacks[].calls[].status`, `call_flow.calls[].status`: `same`, `added`, `removed`, `moved`.
`pseudocode[].language`: `ts`, `tsx`, `json`, `sql`, `prisma`, `bash`, `diff`, `yaml`, `python`, `text`.
`diagram.nodes[].status`: `neutral`, `current`, `new`, `external`, `risk`, `deprecated`.

Kind-specific:

`plan.milestones[].status`: `pending`, `active`, `done`, `blocked`.
`plan.risks[].likelihood`: `low`, `medium`, `high`. `plan.risks[].impact` adds `critical`.
`progress.overall_status`: `on-track`, `at-risk`, `blocked`, `complete`.
`adr.decision_status`: `proposed`, `accepted`, `deprecated`, `superseded`.
`adr.consequences[].type`: `positive`, `negative`, `neutral`.
`adr.reversibility.level`: `easy`, `medium`, `hard`.
`architecture.components[].status`: `current`, `new`, `external`, `deprecated`. No `risk` here; that value exists only on a diagram node.
`review.verdict`: `approve`, `request-changes`, `needs-discussion`, `informational`. The verdict is checked against the findings: `approve` alongside any `blocking` or `high` finding is an error, and `request-changes` with nothing above `medium` is a warning. Pick the verdict from the findings, not before them.
`review.findings[].severity`: `blocking`, `high`, `medium`, `low`, `note`.
`research.findings[].confidence`, `research.recommendations[].confidence`, `research.findings[].evidence[].confidence`: `high`, `medium`, `low`. Research is the only kind with a structured evidence object; `progress.completed[].evidence` and `review.findings[].evidence` are plain strings.
`incident.severity`: `SEV-1` through `SEV-4`.
`incident.incident_status`: `investigating`, `mitigated`, `resolved`, `monitoring`.

## Rejected literals

`content.placeholder` is an error, not a warning. It fires on `lorem ipsum`, `example text`, `insert text`, `insert content`, `TODO`, `TBD`, `FIXME`, `{{...}}`, and the generic-person names `user a`, `user b`, `user c`, anywhere in any string field except `pseudocode`, `api_contracts`, `call_stacks`, `call_flow`, `file_tree`, and `naming`, which are exempt. `validate` strips backtick-quoted spans before the match, so `` `TODO` `` passes it. `check` does not: the same pattern runs again over rendered text as `html.placeholder-copy`, and prose backticks are not rendered as code. Paraphrase instead - write "an unfinished-work marker", not the token - and always run `check`, because it catches placeholders `validate` let through.
