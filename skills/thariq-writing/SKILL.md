---
name: thariq-writing
description: Write practical technical blog posts in the style of Thariq Shihipar's Claude Code essays. Use when the user asks to write, rewrite, outline, edit, or critique a blog-style post, essay, launch note, tutorial, or technical narrative with a direct thesis, concrete workflow pain, agent/tooling examples, practical tradeoffs, and copy-pasteable patterns. Do not use for HTML artifact generation unless the user explicitly asks for an artifact.
---

# Thariq Writing

Use this skill to write blog-style technical posts, not HTML artifacts. The output should feel like a practical engineer explaining a workflow discovery that changed how they work.

## Core Shape

Every post should answer:

1. What default behavior is quietly failing?
2. What did I try instead?
3. Why does the replacement work better?
4. Where does it break down?
5. What can the reader try today?

If the user gives only a topic, infer the most specific claim you can. If there is no usable claim, ask for the workflow, audience, and one real example before drafting.

## Writing Workflow

1. **Extract the claim.** Reduce the topic to one sentence that could be argued with. "HTML is better for agent outputs than Markdown when humans need to inspect the result" is a claim. "HTML artifacts" is a topic.
2. **Name the lived pain.** Start from a concrete frustration: unreadable specs, brittle prompts, hard-to-review diffs, lost context, confusing tools.
3. **Show the turn.** Explain the practical change that made the workflow better. Make it small enough to try.
4. **Give examples.** Include 3-5 real use cases, prompt snippets, before/after sketches, or mini-scenarios.
5. **Add tradeoffs.** Include the strongest reason not to use the pattern. This is what keeps the post credible.
6. **End with a first step.** Give the reader a prompt, checklist, or experiment they can run immediately.

## Default Structure

Use this structure unless the user's topic calls for a different shape:

```markdown
# [Specific claim, not a vague topic]

[Opening: the old default worked until the work changed.]

[Pain: the concrete workflow failure.]

[Turn: the replacement pattern.]

## Why this works

[3-5 short subsections, each with a practical example.]

## How to try it

[Copy-paste prompt, checklist, or small workflow.]

## Where it does not work

[Tradeoffs, limits, failure modes.]

## The pattern

[One concise closing principle.]
```

Headings should carry the argument forward. Prefer "The spec is not the deliverable anymore" over "Background".

## Voice

- Write in first person when describing discovered practice: "I started..." or "I found..." is allowed.
- Use plain words and concrete nouns.
- Keep paragraphs short: 2-4 sentences.
- Use examples more than claims.
- Make the reader feel the workflow, not just understand the concept.
- Use confident but bounded language: "I use this when..." beats "Everyone should..."
- Include one sentence that names the surprising implication.
- Prefer "try this" over "best practices".

## Avoid

- Do not turn the post into a generic tutorial.
- Do not write a listicle unless the user asks for one.
- Do not use hype openings like "AI is changing everything."
- Do not pretend the pattern is universal.
- Do not bury the thesis after a long setup.
- Do not mention Thariq in the final post unless the user explicitly wants a homage or analysis.
- Do not default to HTML output. This skill is about essay style.

## Reference

For a deeper breakdown of the style, read `references/style-anatomy.md`.
