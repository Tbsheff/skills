# Markdown sync

HTML is the generated review surface. Markdown is the durable record when the conclusion must live in Git or remain easy to edit.

Default choices:

| Artifact | Durable Markdown |
| --- | --- |
| Accepted ADR | Required |
| Approved implementation plan | Usually required |
| Architecture mental model | Usually required |
| Progress report | Project-dependent |
| Review | Usually tied to the PR or issue instead |
| Research report | Required when findings will guide future work |
| Incident | Required |
| Handoff | Required while the work remains active |

Sync conclusions, decisions, owners, actions, source locations, and validation results. Do not duplicate generated layout or interaction markup.

Respect the repository’s existing paths and conventions. Do not rewrite unrelated documentation. When source-of-truth paths move, update known references in the same change.
