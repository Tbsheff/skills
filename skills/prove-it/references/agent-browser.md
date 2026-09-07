# Frontend proof with agent-browser

## Fast workflow

1. Reuse the project’s running dev server.
2. Use one worktree-scoped named session.
3. Navigate directly to the changed route.
4. Explore without recording.
5. Reset to a deterministic starting state.
6. Clear console and page-error history.
7. Record only the meaningful action and result.
8. Capture one final-state screenshot.
9. Read diagnostics once and close the session.

## Session

```bash
export AGENT_BROWSER_SESSION="$(agent-browser session id --scope worktree --prefix prove-it)"
```

A named session prevents concurrent agents from taking over each other’s tabs. Use `--restore` only when the project has configured safe, test-only authenticated state.

## Exploration

```bash
agent-browser open "http://127.0.0.1:3000/changed-route"
agent-browser set viewport 1440 900
agent-browser snapshot -i -c
```

Snapshot refs are invalid after navigation, form submission, or rerender. Resnapshot after a page-changing action. Prefer semantic locators in the final replay when the label/role is stable:

```bash
agent-browser find role button click --name "Save"
agent-browser wait --text "Saved"
```

Use expected-state waits instead of fixed sleeps:

```bash
agent-browser wait --url "**/reviews/*"
agent-browser wait --text "Reviewer saved"
agent-browser wait --load networkidle
```

## Screenshot-only proof

Use for static layout, copy, styling, visibility, or a final state that does not need an interaction narrative:

```bash
agent-browser wait --text "Expected heading"
agent-browser screenshot "$PROOF_DIR/frontend/final.png"
```

Do not take a full-page screenshot unless the claim spans the full page. A normal viewport is faster and easier to review.

## Interaction proof

Explore first. Return to the starting state. Then:

```bash
agent-browser console --clear >/dev/null
agent-browser errors --clear >/dev/null
agent-browser record start "$PROOF_DIR/frontend/demo.webm" --fps 12
agent-browser find role button click --name "Save"
agent-browser wait --text "Saved"
agent-browser screenshot "$PROOF_DIR/frontend/final.png"
agent-browser record stop
```

Twelve FPS is enough for ordinary forms and saves; use a higher rate only for animation or drag/drop behavior. Keep the recording under 30 seconds.

## Network evidence

Do not capture HAR by default. For a claim about request method, payload, response, caching, retries, or failed requests:

```bash
agent-browser network har start --content none
# deterministic action
agent-browser network requests --filter api
agent-browser network har stop "$PROOF_DIR/frontend/network.har"
```

Prefer `network request <requestId>` for one relevant request over a full HAR. Never embed secrets or PHI in captured request bodies.

## Diagnostics

```bash
agent-browser console > "$PROOF_DIR/frontend/console.txt"
agent-browser errors > "$PROOF_DIR/frontend/errors.txt"
```

Clear them before replay so old development noise is not attributed to the proof. “No console errors” is a supporting check, not usually a standalone product claim.

## Authentication

Use project-provided test auth, a safe restored session, or agent-browser’s credential vault. Do not type passwords in commands. Do not capture login, MFA, or tokens in video/screenshots.

## Failed replay

Stop recording. Mark the claim failed or not proven. Fix the selector only when the UI changed but the expected behavior remains correct; do not weaken the expected result to make the replay pass.

## Batch a known replay

After exploration has established stable semantic locators, one `batch` call can reduce repeated CLI/daemon round trips:

```bash
agent-browser batch \
  '["console","--clear"]' \
  '["errors","--clear"]' \
  "[\"record\",\"start\",\"$PROOF_DIR/frontend/demo.webm\",\"--fps\",\"12\"]" \
  '["find","role","button","click","--name","Save"]' \
  '["wait","--text","Saved"]' \
  "[\"screenshot\",\"$PROOF_DIR/frontend/final.png\"]" \
  '["record","stop"]'
```

Batch only the deterministic replay. Do not batch discovery that depends on reading a fresh snapshot, and do not retry a failed batch as though it passed. Debug it unbatched, reset state, then make a clean proof replay.
