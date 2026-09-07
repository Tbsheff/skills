# Writing

## Answer first

The first block answers the reader's question: the plan's approach, the current status, the decision, the system model, the review verdict, the research conclusion, the incident impact, or the handoff state.

## Budgets the engine enforces

| Limit | Rule |
| --- | --- |
| Any single field | 45 words |
| `summary.answer` | 45 words |
| Whole artifact | about 4,500 words |
| Metrics | 6 pass the schema, more than 5 warns; treat 5 as the limit |

Validation warns past these. A field that runs long is a field a reader skips. Split it or cut it.

## Plain, not polished

Write like a note to a colleague who is short on time.

- Short sentences. Common words. One idea per sentence.
- Do not restate the title or subtitle in the summary. Say the next true thing instead.
- Write sentences, not label fragments. "Target: 0 auth checks in controllers" is a metric. It is not a summary.
- Leave a field empty when there is nothing real to say. The renderer drops the section. That is better than filler.
- Do not repeat yourself across fields. The engine drops an optional sentence it has already shown, so a duplicated list item or note disappears. Required fields always render, so repeating one shows the reader the same sentence twice and raises `content.duplicate-lead`. It compares 15 lead fields - `objective`, `current_state`, `approach`, `decision`, `context`, `purpose`, `scope`, `question`, `answer`, `method`, `impact`, `root_cause`, `resolution`, `mental_model`, `risk_summary` - against the title, the subtitle, the summary, and each other, and only on an exact match. A paraphrase passes the gate and still wastes the reader's time. Write the next true thing instead.
- Keep metrics to the one or two numbers that change what the reader does. No number means no metric.
- Do not describe the document. No "this artifact", "this section covers", "as shown below".
- Do not reassure. Delete "robust", "comprehensive", "carefully", "ensures", "seamless", and their friends.
- Read it back. A sentence that could appear in any project belongs in no project.

## Plain engineering prose

- Repeat the correct technical noun instead of rotating synonyms.
- State mechanisms and consequences.
- Replace "significantly faster" with the measured delta or the test that will establish it.
- Replace "monitor closely" with a threshold, signal, owner, and response.
- Keep honest hedges such as "not yet measured" or "based on posted logs through this date."
- Avoid hype, slogans, invented framework names, and conclusion-shaped headings that add no information.

## Colour is the engine's job

The engine colours the artifact from the state you record. A `severity`, a `status`, a `verdict`, or a milestone `status` becomes a chip, a rule, or a heading dot. Record honest state and the page marks itself.

No field sets colour. A metric is a label and a value; the engine styles it the same way every time.

Ask for colour nowhere else in the contract. Do not describe something as urgent in prose when the correct move is to set its severity.

## Lists and tables

A list is not analysis by itself. After a dense list or table, make the implication clear in the following sentence. Keep repeated items parallel enough to compare, but do not force every item into identical length.

## Risks and findings

Name what fails, under which condition, and with what effect.

Weak:

> Scalability risk.

Useful:

> When a vendor returns 500, the worker retries without a cap; one poisoned job can hold the queue for the rest of the organization.

## Closure

State what would change the current answer. This lets a reader stop safely instead of reading the entire artifact looking for a hidden exception.
