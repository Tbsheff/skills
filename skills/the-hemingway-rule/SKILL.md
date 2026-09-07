---
name: the-hemingway-rule
description: Use when writing implementation plans, audits, explanations, proposals, or any prose meant for a human reader. Governs writing style, structure, clarity, and decision-surfacing. Invoke whenever the output is more than a code diff.
---

# The Hemingway Rule

Every sentence must do one of three things: explain what is broken, explain why it matters, or tell the reader what to do about it. If a sentence does none of these, delete it.

## Voice

- Write like you are explaining it to a smart colleague over coffee.
- Use plain English. If a technical term is unavoidable, define it once in a parenthetical.
- Prefer active voice and concrete subjects. "The frontend reads stale state" beats "stale state is being consumed by the rendering layer."
- Do not use words to sound precise when they obscure meaning. "Mode-aware helper" means nothing. "A function that checks whether we're in demo or live mode" means everything.
- Do not narrate your own reasoning. Never write "This matters because…", "It is worth noting…", "An important distinction here…", or "I checked the code paths and found…". State the finding. The reader will figure out why you told them.
- Do not soften facts with hedges. If the cost reads $0, the slider *looks* broken. Say that. Do not write "gives the wrong impression."
- Trust the reader's short-term memory. If you already explained what "these" refers to, do not re-specify.

## Structure

### Lead with the punchline

The reader should know what's broken and what to do within three sentences. Details come after.

Bad:
> #### Current cost flow
> ```
> config/llm_pricing.yaml → token_tracker.py → llm-pricing.ts → Simulation.tsx
> ```
> The UI is using the frontend static estimator, not the backend token estimate endpoint.

Good:
> **The cost estimate is stuck at $0 because demo mode never loads the real provider name.** The frontend falls back to "ollama" (which is free), so the math returns zero. Fix: load the provider from the demo cache on boot.

### One heading per decision

Organize by problem, not by "audit findings" vs "implementation plan." Each problem gets:

1. **What's broken** — one to three sentences.
2. **Why** — root cause, briefly. One or two file paths, only if the reader needs to open them.
3. **What to do** — concrete steps. "Update X to do Y" not "consider updating X."
4. **Watch out** — anything non-obvious. Skip if there is nothing surprising.

### File paths are evidence, not decoration

Only mention a file when the reader needs to open it. Six files in a list means zero get opened. One file with a reason means one gets opened.

### Show code when it beats prose

Do not paste routine code that restates the paragraph above it. But when one line of real code proves the point faster than two sentences of description, show the code:

> ```python
> recent_interactions = json.dumps(interactions)[:recent_char_limit]
> ```
> That single line is the whole problem — raw dump, character-truncated.

The reader believes you instantly. No explanation needed.

## Length

**30-second rule.** A busy reader should understand the entire plan by skimming. That means:

- Top of document: 3–5 bullet summary.
- Each section: one screen max (~20 lines of prose).
- If a section is longer, split it into sub-problems.

**Kill the filler.** "This is smaller, lower risk, and already has a failing regression test" → "Fix this first — there's already a failing test." "That creates drift risk" → "The frontend and backend estimates will eventually disagree."

**Say it once.** Top summary + detailed sections. Or detailed sections + bottom recap (only if 5+ sections). Never all three.

## Decisions

Surface choices explicitly. Use a callout:

> **Decision needed:** Should the backend estimate endpoint replace the frontend static math entirely, or should demo-static keep the frontend path since it can't call the backend?

Do not bury decisions inside prose. Do not put all watchouts in a separate megalist — attach each one to the section where the implementer will read it while doing the work.

### Do not template your decisions

If every section ends with the same "Option A (small fix) / Option B (bigger fix) / I recommend A" cadence, vary the framing. Sometimes the answer is obvious — just state it. Sometimes the tradeoff is speed vs. UX fidelity — frame it that way. Sometimes there is genuinely no choice and the section only needs a recommendation. Forcing an A/B choice on every problem makes the document feel like a form, not analysis.

## Sentence rhythm

Vary length. Three medium sentences in a row put the reader to sleep.

Bad (every sentence ~20 words, same structure):
> The badge is rendered in Simulation.tsx with the frontend helper. That helper needs the provider and model name. In demo-static, AppContext loads the cached session but does not load the provider. The app then falls back to ollama, which is priced at zero.

Good:
> The cost badge calls a pricing helper that needs the provider name. Demo-static never loads it. So the app defaults to "ollama" — free — and the math returns $0.

Long, short, long. The short one lands.

## Flow diagrams

Use a diagram only when branching or sequencing is genuinely hard to follow in prose. A three-way branch earns its space. A linear sequence that the paragraph already described does not.

Good:
> ```text
> live        → backend estimate API
> demo        → backend estimate API (cached data)
> demo-static → frontend static helper (no backend)
> ```

Bad: any diagram that restates the preceding paragraph.

## Tests

One line per test case. Name behaviors, not files. `test_persona_name_handling.py` tells the reader nothing. "majority-wins extraction rejects cultural terms" tells them everything.

> Tests: demo-static cost is non-zero after boot; cost updates when the slider moves; provider comes from demo cache, not defaults.

## Banned words

| Instead of | Write |
|---|---|
| hydrate | load |
| source of truth | the one place this value lives |
| cross-cutting | touches several files |
| mode-aware | checks which mode we're in |
| drift risk | the two values will eventually disagree |
| containment fix | small fix |
| invasive change | bigger change, touches more files |
| side effects | breaks other things |
| surface (verb) | show / expose / call out |
| leverage / utilize | use |
| facilitate | help |
| architecting | designing |
| orthogonal | unrelated |
| non-trivial | hard / complicated |
| grounded by / grounding | backed by / uses X for context |
| material (adjective) | real / significant |
| plumbing | routine wiring / the code work |
| acceptance item | requirement / thing to verify |

If you would not say it out loud to a person, use the word you would actually say.

## The checklist

You can use this handy checklist to audit your own writing: 

- [ ] Can a reader skim the first three lines and know what's broken and what to do?
- [ ] Is every file path mentioned because the reader needs to open it?
- [ ] Is every code block showing something the prose didn't already explain?
- [ ] Are decisions called out explicitly, not buried?
- [ ] Is the total length under 2 pages per problem?
- [ ] Did you use the simplest possible word for every concept?
- [ ] Would you be comfortable reading this aloud to someone? If it sounds stilted, rewrite it.