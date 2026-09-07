---
name: typed-call-stack-planning
description: Creates executable implementation plans for multi-file code changes using typed pseudocode, boundary maps, current/target call stacks, explicit non-goals, tests, and live handoffs. Use before implementing features/refactors where design seams, interfaces, adapters, or call flow matter.
metadata:
  version: "0.1.0"
  planning_style: "typed-pseudocode + boundaries + call-stacks"
  compatibility: Pi / Agent Skills compatible; no external tools required.
---

# Typed Call-Stack Planning

## Purpose

Use this skill to turn an implementation request into durable, executable context before and during coding.

The plan should look more like typed pseudocode than prose. Prefer contracts, interfaces, function signatures, composition maps, and call stacks over vague paragraphs. The goal is for a fresh agent or engineer to know exactly what to edit, why each boundary exists, and which runtime path proves the work is complete.

## When to use

Use this skill when any of these are true:

- The change spans multiple files, packages, layers, or services.
- Correctness depends on module boundaries, adapters, seams, dependency injection, or ownership.
- The task crosses an entrypoint boundary such as CLI -> service, UI -> API, job -> worker, handler -> domain, or test -> fixture.
- The runtime call flow is hard to hold in working memory.
- The user asks for a plan, handoff, implementation strategy, architecture review, call graph, call stack, seams, or typed pseudocode.
- The agent may be tempted to add broad refactors or extra functionality.

For a one-line or obviously local edit, keep the planning lightweight: write a tiny target stack and proceed.

## Core rules

1. Read the relevant code before drafting the plan.
2. Represent the plan as typed contracts and runtime paths, not generic prose.
3. Include current and target call stacks when possible.
4. Make boundaries explicit and preserve them during implementation.
5. Add explicit non-goals so the agent does not expand scope.
6. Implement one vertical slice at a time.
7. Keep the plan or handoff updated as facts change.
8. Do not add functionality, broad refactors, packages, APIs, tests, or behavior outside the plan unless the user asks or the plan is deliberately updated first.

## Default context files

Prefer durable repo-local context files when the task is not trivial:

```text
llm/context/<YYYY-MM-DD>-<slug>-plan.md
llm/context/<YYYY-MM-DD>-<slug>-handoff.md
```

If the repository already uses a different convention, follow the existing convention.

## Workflow

### 1. Inspect before planning

Before writing the plan, inspect enough code to identify:

- entrypoints;
- existing call stacks;
- public APIs and internal interfaces;
- adapters and IO boundaries;
- data structures and error types;
- tests, fixtures, and commands;
- constraints from `AGENTS.md`, existing context files, README files, or nearby docs.

When something is not yet known, write `Unknown` and list the exact file or command needed to resolve it. Do not invent facts.

### 2. Produce a typed implementation plan

Use the project language when possible. For TypeScript, use interfaces/types. For Rust, use traits/enums/structs. For Go, use interfaces/structs. For Python, use Protocols/dataclasses/TypedDicts when helpful.

Use this plan shape:

~~~md
# Plan: <task>

## Goal

<One short paragraph describing the user-visible outcome.>

## Non-goals

- <Behavior/refactor explicitly out of scope.>
- <Files/layers not to touch unless the plan changes.>
- Do not add functionality not listed in this plan.

## Current state

- `<file>`: <what exists now>
- `<function/type>`: <current responsibility>
- Constraint: <known constraint from code/docs/user>

## Target contracts

```ts
// Pseudocode. Adapt this to the project language.
interface ExampleInput {
  /* fields that matter at the boundary */
}

interface ExampleOutput {
  /* result shape expected by callers */
}

type BoundaryResult =
  | { ok: true; value: ExampleOutput }
  | { ok: false; error: KnownError };

interface BoundaryPort {
  execute(input: ExampleInput): Promise<BoundaryResult>;
}
```

## Boundary / composition map

```text
[entrypoint] <CLI / route / job / event handler>
  -> [adapter] <config/env/request parsing>
  -> [domain] <pure decision or orchestration>
  -> [io] <filesystem/process/network/db>
  -> [reporting] <response/result formatting>
```

## Current call stack

```text
[entrypoint] file:function()
  -> [adapter] file:function()
  -> [domain] file:function()
  -> [io] file:function()
```

## Target call stack

```text
[entrypoint] file:function()
  -> [adapter] file:function()
  -> [domain] file:newOrChangedFunction()
  -> [branch]
      -> [io] file:happyPathFunction()
      -> [fallback] file:fallbackFunction()
  -> [reporting] file:function()
```

## Error / fallback stacks

```text
[failure condition]
[entrypoint] file:function()
  -> [domain] file:function()
  -> [error] file:normalizeKnownFailure()
  -> [reporting] file:formatFailureForCaller()
```

## Implementation steps

1. `<file>`
   - Change: <specific edit>
   - Boundary touched: <entrypoint | adapter | domain | io | reporting | test>
   - Acceptance check: <how to know this step works>

2. `<file>`
   - Change: <specific edit>
   - Boundary touched: <...>
   - Acceptance check: <...>

## Tests / checks

```bash
<repo-specific command>
```

## Completion criteria

- [ ] Target contracts exist or their equivalent is implemented.
- [ ] Target happy-path call stack is implemented.
- [ ] Target error/fallback stacks are implemented or explicitly not applicable.
- [ ] Boundaries match the boundary map.
- [ ] Tests/checks pass, or failures are documented with exact output.
- [ ] No extra functionality was added.
~~~

### 3. Treat call stacks as first-class design artifacts

For each important flow, include the current stack and the target stack when possible.

Call stack rules:

- Use real file and function names whenever known.
- Mark each frame with a role: `[entrypoint]`, `[adapter]`, `[domain]`, `[io]`, `[reporting]`, `[test]`, `[error]`, or `[fallback]`.
- Show branch points explicitly.
- Include error/fallback paths if they affect design or tests.
- Keep stacks implementation-oriented: a coder should be able to walk the stack and know where to edit next.

Example:

```text
Happy path:
[entrypoint] packages/cli/src/run.ts:run()
  -> [adapter] packages/cli/src/config.ts:readProjectConfig()
  -> [domain] packages/core/src/plan.ts:createExecutionPlan()
  -> [io] packages/core/src/process.ts:executeLocalProcess()
  -> [reporting] packages/cli/src/output.ts:formatResult()

Fallback path:
[domain] packages/core/src/plan.ts:createExecutionPlan()
  -> [fallback] packages/core/src/fallback.ts:executeFallbackStrategy()
  -> [reporting] packages/cli/src/output.ts:formatResult()
```

### 4. Preserve boundaries during implementation

Add a `Boundaries` section whenever the task crosses layers.

Example:

```md
## Boundaries

- CLI owns argument parsing, process exit codes, and user-facing output.
- Domain code owns decisions, state transitions, and strategy selection.
- IO adapters own filesystem, process, network, and database effects.
- Tests should observe public behavior first and internals only when needed.
```

Do not collapse boundaries for convenience. If the code contradicts the plan, stop and update the plan with the discovered constraint before continuing.

### 5. Implement the plan in vertical slices

Before editing code, restate the next slice in 3-7 bullets:

```md
## Next implementation slice

- Edit `<file>` to introduce `<type/function>`.
- Wire `<caller>` to `<callee>` without changing behavior.
- Add/update `<test>` for `<observable behavior>`.
- Run `<command>`.
```

Then implement only that slice.

Hard guardrail:

> Do not add extra functionality, broad refactors, packages, APIs, tests, or behavior outside the current plan unless the user asks or the plan is updated first.

### 6. Keep the plan live

After each meaningful phase, update the plan or handoff with:

- completed steps;
- changed files and functions;
- discovered constraints;
- call stack changes;
- passing/failing checks;
- exact next action.

If a mistake or recurring preference should become a durable rule, suggest an `AGENTS.md` entry, but do not edit global/project rules unless asked.

## Handoff template

Use this when ending a session, handing off to another agent, or pausing mid-task.

~~~md
# Handoff: <task>

## Done

- <completed work with files/functions>

## Current state

- <what compiles/runs>
- <what remains broken, unknown, or unverified>

## Important contracts

```ts
<final important interface/type snippets or language equivalent>
```

## Implemented call stacks

```text
<final happy-path stack>
<final error/fallback stack if relevant>
```

## Files changed

- `<file>`: <summary>

## Commands already run

```bash
<command>
# result: <pass/fail + short exact output>
```

## Next steps

1. <exact next action>
2. <exact next action>
3. <exact next action>

## Do not do

- <scope guardrails>
- Do not add functionality outside the approved plan.
~~~

## Prompt snippets

Ask for a plan only:

```text
Use the typed-call-stack-planning skill. Read the relevant code and create a plan in llm/context/. Make the plan mostly typed pseudocode: interfaces, boundaries, composition, current/target call stacks, files/functions, tests, and explicit non-goals. Do not implement yet.
```

Ask to implement from a plan:

```text
Use the typed-call-stack-planning skill. Read llm/context/<plan>.md, summarize the target stack briefly, then implement only the listed steps in vertical slices. Do not add extra functionality. Update the plan or handoff as you complete work.
```

Ask to repair or re-ground a stale plan:

```text
Use the typed-call-stack-planning skill. Compare the plan to the current code. Identify mismatches, update the current and target call stacks, and rewrite the next implementation slice before coding.
```

Ask for a handoff:

```text
Use the typed-call-stack-planning skill. Write a handoff with what changed, tests run, files modified, open issues, final call stacks, and the next exact todos.
```

## Quality bar

The plan is ready only when a fresh agent can answer these questions without reading the whole chat:

- Which files and functions change?
- Which types, interfaces, traits, structs, or protocols are the contracts?
- Which boundary owns each responsibility?
- What calls what in the current flow?
- What should call what in the target flow?
- Which error or fallback paths matter?
- Which tests or commands prove completion?
- What is explicitly out of scope?
