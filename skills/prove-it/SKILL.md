---
name: prove-it
description: Human-invoked verification for an existing pull request. Use only when the user explicitly invokes /prove-it, says to prove/verify a PR, or asks to attach screenshots, video, or backend proof to an existing PR. Never invoke automatically while creating, opening, or updating a PR. Uses agent-browser for frontend evidence and GitHub CLI `gh pr edit --attach` to publish reviewer-facing proof.
license: MIT
metadata:
  version: "1.1.0"
  display-name: "Prove It"
  compatibility: Designed for Claude Code. Requires git, gh, and Python 3.10+. Frontend proof requires agent-browser. `gh pr edit --attach` is required to upload images/video.
---

# Prove It

Human-invoked proof for an **already-existing pull request**.

Do nothing unless the human explicitly asks for this skill. Do not run it as part of PR creation and do not wire it into a create-PR hook.

The goal is to give a reviewer compact evidence that the important behavior in the PR actually works:

```text
claim -> expected observation -> cheapest direct check -> evidence -> verdict
```

Frontend evidence uses `agent-browser`. Backend evidence uses the narrowest useful command, test, HTTP assertion, database check, or log assertion. The durable output is the PR body plus GitHub-hosted image/video attachments. Local artifacts are temporary.

## Invocation

Typical human invocations:

```text
/prove-it
/prove-it 123
/prove-it https://github.com/owner/repo/pull/123
```

With no argument, target the PR for the current branch. With an argument, target that PR.

The PR must already exist. `prove-it` never runs `gh pr create`.

## Storage lifecycle

By default proof files live under the operating system temp directory:

```text
$TMPDIR/prove-it-pr-<number>-<sha>-*/
```

Never store normal proof runs under `.git`, the worktree, or the source branch.

On successful GitHub upload, delete the temporary proof directory immediately. `scripts/prove-it publish` does this automatically. `--keep` is debugging-only. New runs also prune abandoned Prove It temp directories older than 24 hours.

## Fast defaults

Use the smallest credible evidence set:

- At most 3 observable claims.
- At most 3 targeted backend commands.
- At most 1 browser flow.
- At most 2 screenshots.
- At most 1 short video, under 30 seconds, recorded only for interaction changes.
- No full suite merely for proof.
- No browser for backend-only changes.
- No HAR, trace, profiler, full-page capture, or visual diff unless the claim specifically needs it.
- Never record exploration, retries, login setup, dependency installation, or waiting.
- Never use production data, real customer data, or secrets.

Read [references/proof-policy.md](references/proof-policy.md) before expanding beyond these limits.

## 1. Resolve and bind to the PR

Set the helper path:

```bash
PROVE_IT="<absolute-path-to-this-skill>/scripts/prove-it"
```

Check dependencies once:

```bash
"$PROVE_IT" doctor
```

Initialize against the existing PR:

```bash
PR="${ARGUMENTS:-current}"
PROOF_DIR="$("$PROVE_IT" init --repo . --pr "$PR" --mode fast)"
```

`init --pr` resolves the PR with `gh pr view`, records its number/repository/head SHA/base branch, and refuses to continue unless:

- local `HEAD` exactly matches the PR head SHA on GitHub
- the worktree is clean
- the PR base is available locally

This prevents a screenshot or test from being attached to a different revision than the reviewer is looking at.

Read [references/pr-targeting.md](references/pr-targeting.md) for target rules.

## 2. Inspect the PR diff and choose 1–3 claims

The init manifest contains the PR-bound diff classification. Inspect the actual diff as well.

Use this default proof shape:

| Change | Default proof |
|---|---|
| Docs/config/refactor with no changed behavior | No runtime proof; attach a concise note only if useful |
| Library/backend behavior | One targeted test/script/request/state assertion |
| Static visual change | One final-state screenshot |
| Interactive UI behavior | One deterministic browser flow + final screenshot; short video if it improves review |
| Mixed frontend/backend | One direct backend assertion + one browser flow |
| Security/data boundary | Positive + negative direct assertions; browser only for a distinct visible claim |

Write claims about reviewer-visible behavior, not implementation details.

Good:

- “Saving a review persists the selected reviewer.”
- “Reloading the queue shows the saved reviewer.”
- “A user from another organization receives 403.”

Bad:

- “The resolver was refactored.”
- “Tests pass.”
- “The page works.”

Add claims:

```bash
"$PROVE_IT" claim --dir "$PROOF_DIR" \
  --text "<observable behavior>" \
  --expected "<specific result>" \
  --method test
```

## 3. Prove backend claims directly

Prefer the cheapest direct assertion that proves the claim.

Focused test/example:

```bash
"$PROVE_IT" run --dir "$PROOF_DIR" --claim C1 \
  --kind test --label "Reviewer persistence" --proves \
  -- pnpm vitest run path/to/relevant.test.ts -t "persists reviewer"
```

Local API example:

```bash
"$PROVE_IT" http --dir "$PROOF_DIR" --claim C1 \
  --label "Create review API" \
  --url "http://127.0.0.1:3000/api/reviews" \
  --method POST \
  --header "Content-Type: application/json" \
  --data '{"reviewerId":"reviewer-test"}' \
  --expect-status 201 \
  --expect-json 'reviewerId="reviewer-test"' \
  --proves
```

Use `--proves` only when the assertions actually establish the claim. Read [references/backend-evidence.md](references/backend-evidence.md) for auth, DB, queue, and failure-path patterns.

## 4. Prove frontend claims with agent-browser

Read [references/agent-browser.md](references/agent-browser.md).

Use one named browser session for the run. Reuse the running dev server and safe test auth when available.

Explore without recording:

```bash
export AGENT_BROWSER_SESSION="$(agent-browser session id --scope worktree --prefix prove-it)"
agent-browser open "<local changed route>"
agent-browser set viewport 1440 900
agent-browser snapshot -i -c
```

Clear stale diagnostics before the clean replay:

```bash
agent-browser console --clear >/dev/null
agent-browser errors --clear >/dev/null
```

For static UI proof, capture only the useful final state:

```bash
agent-browser wait --text "<expected state>"
agent-browser screenshot "$PROOF_DIR/frontend/final.png"
```

For an interaction, record only the deterministic demonstration:

```bash
agent-browser record start "$PROOF_DIR/frontend/demo.webm" --fps 12
# minimum deterministic actions
agent-browser wait --text "<expected state>"
agent-browser screenshot "$PROOF_DIR/frontend/final.png"
agent-browser record stop
```

Then capture diagnostics once:

```bash
agent-browser console > "$PROOF_DIR/frontend/console.txt"
agent-browser errors > "$PROOF_DIR/frontend/errors.txt"
```

Register media with the claim:

```bash
"$PROVE_IT" add --dir "$PROOF_DIR" --claim C2 \
  --type screenshot --path "$PROOF_DIR/frontend/final.png" \
  --label "Queue after save" \
  --observed "The saved reviewer is visible after reload." --proves
```

If the flow fails, record the failure honestly. Do not substitute a different happy path.

## 5. Render and inspect

```bash
"$PROVE_IT" validate --dir "$PROOF_DIR"
"$PROVE_IT" render --dir "$PROOF_DIR"
```

Transient outputs include:

```text
manifest.json       canonical claim/evidence record
proof.md            reviewer-facing PR section
report.html         local inspection report
attachments.json    media selected for upload
frontend/*          screenshots/video/diagnostics
backend/*           command/API evidence
```

Check screenshots/video for sensitive information before publishing.

## 6. Attach proof to the existing PR

Publish with:

```bash
"$PROVE_IT" publish --dir "$PROOF_DIR"
```

`publish`:

1. re-resolves the bound PR with `gh pr view`
2. verifies the PR head SHA and local `HEAD` are still the SHA that was proven
3. verifies the worktree is still clean
4. renders/replaces its marker-delimited `## Prove It` section
5. runs `gh pr edit <number> --body-file ... --attach ...`
6. verifies local media references were rewritten to GitHub-hosted attachments
7. deletes the temporary proof directory on success

The GitHub PR is the durable artifact. The repository is not modified and proof binaries are never committed.

Use `--keep` only when debugging the skill itself:

```bash
"$PROVE_IT" publish --dir "$PROOF_DIR" --keep
```

Read [references/publishing.md](references/publishing.md) for the exact GitHub CLI behavior.

## 7. Failure behavior

If proof fails, say so and still attach it when that is useful to the reviewer. Failed proof is evidence too.

Do **not** publish when:

- the PR head changed after proof started
- local `HEAD` differs from the PR head
- the worktree became dirty
- evidence hashes do not match
- media is missing
- secret scanning finds likely credentials
- installed `gh` lacks `pr edit --attach`

If publication fails, the temporary directory is left in `$TMPDIR` so the upload can be retried. Delete it explicitly when done:

```bash
"$PROVE_IT" cleanup --dir "$PROOF_DIR"
```

Abandoned runs older than 24 hours are pruned on a later invocation.

## Done

Report only:

- the PR URL
- how many claims passed/failed/not-proven
- what reviewer-facing media was attached

Do not keep a duplicate local proof archive after successful upload.
