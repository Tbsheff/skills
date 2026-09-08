---
name: prove-it
description: Add a short human-readable QA comment to an existing GitHub pull request using agent-browser, focused runtime checks, and gh attachments.
disable-model-invocation: true
context: fork
argument-hint: "[PR number or URL]"
license: MIT
compatibility: Claude Code and Codex. Requires git, gh, and Python 3.10+. Frontend proof requires agent-browser. Media upload requires gh pr comment --attach.
metadata:
  version: "1.8.0"
---

# Prove it

Add one QA comment to an existing pull request. A human must invoke this skill. Never create a PR or run this from a PR-creation workflow.

## Rules

- At the start, local `HEAD` must match the PR head and the worktree must be clean.
- Freeze that commit as the capture SHA. Do not wait for CI.
- If the PR advances during capture, finish the run and say which commit you tested.
- Check no more than three observable behaviors unless the human asks for more.
- Write like a developer leaving a useful PR comment. No report voice or canned status language.
- Default visible shape: `## QA`, one commit sentence, 1-3 short observations, the real media, one important caveat if needed.
- Do not show claim counts, evidence inventories, backend sections, review-path sections, checklists, generated proof maps, or repeated explanations.
- Put commands, assertions, output, code links, diagnostics, and optional path details under one `What I ran` disclosure.
- Every UI-facing change must include a visual claim and show the real app with a screenshot or video when that path is reachable. Tests cannot replace this proof.
- Do not use a synthetic fixture when the changed flow can run in the real app. If the real path is blocked, mark the visual claim `not_proven` and say what blocked it.
- Backend-only checks must include the generated behavior diagram plus the real command, request, or state-change receipt. The receipt proves the result; the diagram makes the path easy to read.
- Use the cheapest check that establishes the behavior. Do not rerun broad CI work.
- Use `agent-browser` only for visible behavior. Explore first, then record one clean take.
- Never publish secrets, credentials, PHI, customer data, raw HAR files, or broad logs.
- Keep files in `$TMPDIR`. Delete them after GitHub confirms the comment and attachments.

## Run

```bash
SKILL_DIR="${CLAUDE_SKILL_DIR:-${CODEX_HOME:-$HOME/.codex}/skills/prove-it}"
PROVE_IT="$SKILL_DIR/scripts/prove-it"
PR="${ARGUMENTS:-current}"
PROOF_DIR="$("$PROVE_IT" init --repo . --pr "$PR")"
```

In Codex, set `PR` to the PR number or URL from the request when one was provided.

### 1. Plan

Read [references/planning.md](references/planning.md). Inspect the PR diff and choose one to three behaviors worth checking.

Read `change.recommended_proof` in `$PROOF_DIR/manifest.json`. For `browser`, `screenshot`, or `mixed`, create a visual claim before running tests.

### 2. Check it

For backend, API, persistence, worker, or authorization behavior, read [references/backend.md](references/backend.md).

For visible UI behavior, read [references/browser.md](references/browser.md). CI and remote PR movement do not block capture.

Mark anything not established as `not_proven`. Do not weaken a claim to get a pass.

After backend checks, run `"$PROVE_IT" visualize --dir "$PROOF_DIR"`. `publish` also generates the diagram for backend-only runs when it is missing.

### 3. Comment

Read [references/publishing.md](references/publishing.md), then run:

```bash
"$PROVE_IT" validate --dir "$PROOF_DIR"
"$PROVE_IT" publish --dir "$PROOF_DIR"
```

`publish` creates a new PR comment with `gh pr comment --attach`, checks the uploaded media, then removes the temp directory.

## Return

Report the comment URL, commit tested, and media attached. Do not repeat the comment in chat.

For repo-specific startup, routes, test commands, or safe auth, read [references/configuration.md](references/configuration.md). Run `"$PROVE_IT" doctor` only when a dependency or upload command fails.
