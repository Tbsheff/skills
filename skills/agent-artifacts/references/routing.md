# Routing

Choose the artifact kind by the reader’s next action, not by the source format.

| Signal | Kind |
| --- | --- |
| “How should we build/migrate/roll this out?” | `plan` |
| “Where are we, what changed, what is blocked?” | `progress` |
| “What did we choose and why not the alternatives?” | `adr` |
| “How does this system work or how should its boundaries change?” | `architecture` |
| “Is this safe/correct/ready, and what must change?” | `review` |
| “What did the investigation establish?” | `research` |
| “What failed, why, how was it restored, and how do we prevent recurrence?” | `incident` |
| “What does the next person need to continue?” | `handoff` |

## HTML or Markdown

Use the generated HTML review surface when the reader benefits from scanning, comparison, status, a diagram, a timeline, a risk table, or repeated artifact conventions.

Use ordinary Markdown when:

- the answer fits in a few paragraphs;
- the document is primarily edited by hand;
- no visual relationship or repeated artifact structure adds review value;
- the user asked for a plain text record only.

For accepted ADRs, durable plans, and architecture records, produce both: Markdown as source of truth and HTML as a generated review surface.

## Ambiguity

Infer first. Ask one compact question only when two kinds would lead to materially different contracts. Common combinations:

- A plan may include a small architecture diagram, but remains a `plan` when execution order is the reader’s main need.
- A review may recommend a plan, but remains a `review` when the verdict is the reader’s first need.
- Research may lead to an ADR; keep them separate when evidence collection and decision accountability need different records.
- A progress report may end with a handoff, but use `handoff` when another person or agent is expected to take over.
