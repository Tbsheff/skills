---
name: prove-it
description: Prove changed code with focused runtime checks and visual artifacts. Use after changing code, before shipping, or when asked to verify behavior. Work locally on uncommitted changes or publish to an existing GitHub pull request.
context: fork
argument-hint: "[PR number or URL]"
license: MIT
compatibility: Claude Code and Codex. Requires git, gh, and Python 3.10+. Frontend proof requires agent-browser 0.38+ and Chrome. Base/change media requires ffmpeg and ImageMagick 7. Media upload requires gh pr comment --attach.
metadata:
  version: "2.2.1"
---

# Prove it

Prove changed behavior locally or in one PR comment. Never create a PR.

## Rules

- Choose local mode when the worktree is dirty or the branch has no pull request. Start at once. Do not ask for a commit or PR first.
- Choose PR mode only when local `HEAD` matches the PR head and the worktree is clean.
- Freeze that commit as the capture SHA. Do not wait for CI.
- If another session can move the checkout, add `--pin` to `init`. Commands then run in a pinned worktree, `$PROOF_DIR/checkout`.
- If the PR advances during capture, finish the run and say which commit you tested.
- Check no more than three observable behaviors unless the human asks.
- Write like a developer, not a status report.
- Use `## QA`, one commit sentence, 1-3 short observations, real media, and one important caveat if needed.
- Do not show claim counts, evidence lists, checklists, proof maps, or repeated text.
- Put commands, output, code links, and diagnostics under one `What I ran` disclosure.
- Every UI change needs a visual claim and real-app screenshot or video when reachable. Tests cannot replace it.
- Use a fixture only when the real flow cannot run. Mark blocked visual claims `not_proven` and give the cause.
- Backend checks need the summary plus the real command, request, or state receipt.
- Use the cheapest check that proves the behavior. Do not rerun CI.
- Use `agent-browser` only for visible behavior. Explore first, then record one clean take.
- Show base and change with `prove-it media` when you can. Never type evidence by hand.
- Media shows real data: use seed data, never a production session.
- Never publish secrets, PHI, customer data, raw HAR files, or broad logs.
- Keep files in `$TMPDIR`. Delete them after GitHub confirms the comment.

## Run

```bash
SKILL_DIR="${CLAUDE_SKILL_DIR:-${CODEX_HOME:-$HOME/.codex}/skills/prove-it}"
PROVE_IT="$SKILL_DIR/scripts/prove-it"
```

Select the mode before `init`:

```bash
# Local mode: dirty worktree, no PR, or proof before shipping.
PROOF_DIR="$("$PROVE_IT" init --repo . --working-tree)"

# PR mode: clean worktree, existing PR, and local HEAD matches its head.
PR="${ARGUMENTS:-current}"
PROOF_DIR="$("$PROVE_IT" init --repo . --pr "$PR")"
```

If PR lookup fails, use local mode.

### 1. Plan

Read [references/planning.md](references/planning.md). Choose one to three behaviors.

Read `change.recommended_proof` in `$PROOF_DIR/manifest.json`. For `browser`, `screenshot`, or `mixed`, create a visual claim before running tests.

### 2. Check it

Use `media` for a UI flow or backend change on both commits; else use the reference steps. Draft a [scenario](references/scenario.md), clear its `todo`, check, capture:

```bash
"$PROVE_IT" draft --dir "$PROOF_DIR" --out "$PROOF_DIR/scenario.json"
"$PROVE_IT" scenario --dir "$PROOF_DIR" --scenario "$PROOF_DIR/scenario.json"
"$PROVE_IT" media --dir "$PROOF_DIR" --scenario "$PROOF_DIR/scenario.json" --proves
```

For backend, API, persistence, worker, or authorization behavior, read [references/backend.md](references/backend.md).

For visible UI behavior, read [references/browser.md](references/browser.md).

Mark anything not established as `not_proven`. Do not weaken a claim to get a pass.

For example-driven behavior, record cases with `"$PROVE_IT" example`. After backend checks without media, run `"$PROVE_IT" visualize --dir "$PROOF_DIR"`. `publish` makes it if it is missing.

### 3. Share the result

Read [references/publishing.md](references/publishing.md).

In PR mode, run:

```bash
"$PROVE_IT" validate --dir "$PROOF_DIR"
"$PROVE_IT" publish --dir "$PROOF_DIR"
```

`publish` posts one new comment, checks the media, and removes the temp directory. `--dry-run` posts nothing.

In local mode, run:

```bash
"$PROVE_IT" validate --dir "$PROOF_DIR"
"$PROVE_IT" render --dir "$PROOF_DIR"
```

Keep the local run directory. Do not publish it.

## Return

In PR mode, report the comment URL, tested commit, and media. Do not repeat the comment.

In local mode, report the tested commit, tree state, `proof.md` and media paths, and that nothing was published.

For repo startup, routes, tests, or safe auth, read [references/configuration.md](references/configuration.md). Run `"$PROVE_IT" doctor` only when a dependency or upload fails.
