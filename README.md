# Personal Agent Skills

Agent skills created and maintained by Tyler Sheffield.

## Skills

- `abstraction-design-coach` — Design and simplify software abstractions.
- `agent-artifacts` — Build checked engineering artifacts from structured data.
- `prove-it` — Add visible proof to an existing pull request.
- `thariq-writing` — Write direct, practical technical posts.
- `the-hemingway-rule` — Keep plans, audits, and explanations concise.
- `thermo-nuclear-code-quality-review` — Run a strict maintainability review.
- `typed-call-stack-planning` — Plan multi-file work with typed call stacks.
- `writing-architecture-plans` — Write implementation-ready architecture plans and ADRs.

## Install as a Claude Code plugin

Add this repo as a plugin marketplace, then install the plugin:

```sh
claude plugin marketplace add Tbsheff/skills
claude plugin install tbsheff-skills@tbsheff
```

In Claude Code, skills show with the `tbsheff-skills:` prefix, for example `/tbsheff-skills:prove-it`.

To test local changes without installing:

```sh
claude --plugin-dir /path/to/skills
```

## Install with `npx skills`

List the available skills without installing them:

```sh
npx skills add Tbsheff/skills --list
```

Install all skills globally for Codex and Claude Code:

```sh
npx skills add Tbsheff/skills --skill '*' --global --agent codex --agent claude-code
```

Install one skill globally:

```sh
npx skills add Tbsheff/skills --skill typed-call-stack-planning --global --agent codex --agent claude-code
```

Omit `--global` to install into the current project.

Each folder follows the Agent Skills layout and has a `SKILL.md` entry point.
