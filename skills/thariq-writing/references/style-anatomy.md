# Style Anatomy

Use this reference when drafting or critiquing a full post.

## Study Anchors

- Thariq Shihipar, "Using Claude Code: The unreasonable effectiveness of HTML" - https://claude.com/blog/using-claude-code-the-unreasonable-effectiveness-of-html
- Thariq Shihipar, "Lessons from building Claude Code: How we use skills" - https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- Thariq Shihipar, "Seeing like an agent" - https://claude.com/blog/seeing-like-an-agent
- Thariq Shihipar, "Using Claude Code: session management and 1M context" - https://claude.com/blog/using-claude-code-session-management-and-1m-context
- Thariq Shihipar, "A harness for every task" - https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code

## The Repeating Pattern

Thariq-style posts usually move through this arc:

```text
old default
  -> new pressure from agents or bigger workflows
  -> small practical replacement
  -> concrete examples
  -> limits and FAQ
  -> prompt or habit the reader can copy
```

The style works because the post is not selling an idea in the abstract. It is reporting a changed working habit.

## Opening Moves

Good openings:

- Start from a once-good default that no longer fits.
- Name the new constraint that broke it.
- Move quickly to the replacement pattern.

Bad openings:

- "In today's fast-paced world..."
- "As AI agents become more powerful..."
- A historical overview before the reader knows the claim.
- A definition of a familiar concept.

Useful opening template:

```markdown
[Old default] used to be the obvious choice for [task]. It still works for [small/simple case]. But once [new pressure] shows up, it starts failing in a specific way: [pain]. I have started using [replacement] instead.
```

## Section Patterns

Use these section types as building blocks.

### Why It Works

Explain the mechanism. Each subsection should pair an explanation with a real use case.

```markdown
### It keeps the reviewer in the loop

[Mechanism.] For example, [specific workflow]. The important part is [small operational detail].
```

### Example Prompts

When the topic involves agents or tools, include prompts people can paste.

```markdown
Try:

> [Prompt that creates the behavior.]

The key detail is [why that prompt works].
```

### FAQ Or Tradeoffs

Use this instead of a vague "Limitations" section. Make the objections real.

```markdown
### Is this slower?

Sometimes. [Pattern] costs more when [case]. I still use [old default] when [case].
```

## Sentence-Level Rules

- Make the subject concrete: "Markdown collapses the structure" beats "structure can be lost."
- Use "when" clauses to bound claims: "When the output is a spec someone needs to inspect..."
- Prefer operational verbs: read, inspect, share, edit, copy, verify, compare.
- Remove apology phrases: "just", "maybe", "I think", "it is worth noting".
- Keep the post curious, not triumphant. The tone is "this works surprisingly well," not "the old way is dead."

## Critique Checklist

Before finalizing, check:

- Does the title make a claim?
- Does the first screen explain the pain and replacement?
- Are there at least three concrete examples?
- Is there a copy-pasteable prompt, checklist, or first step?
- Is the strongest tradeoff included?
- Could a reader use the idea in the next hour?
- Did the draft avoid turning into generic AI commentary?

## Quick Rewrite Moves

If the draft feels generic:

1. Replace the first paragraph with a concrete scene.
2. Cut any definition the target reader already knows.
3. Add a "Try this" block.
4. Add the strongest reason the pattern might fail.
5. Rename headings so they state claims.

If the draft feels too promotional:

1. Add a "Where this does not work" section.
2. Replace superlatives with conditions.
3. Show one boring operational example.
4. Remove words like "revolutionary", "transform", "unlock", and "seamless".

If the draft feels too dry:

1. Add the moment the old workflow broke.
2. Add before/after examples.
3. Use one surprising line that names the implication.
