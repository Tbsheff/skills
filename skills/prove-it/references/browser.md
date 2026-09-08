# Browser checks

Use `agent-browser` for behavior a reviewer can see. The result must let the reviewer see the changed behavior, not only a test result or a mounted fixture. Do not wait for CI or restart a good recording because the remote PR head changed.

Use the real app route when it exists. A component fixture is a fallback for a component with no reachable route, not a shortcut around app startup, auth, or state setup.

## One session

```bash
export AGENT_BROWSER_SESSION="$(agent-browser session id --scope worktree --prefix prove-it)"
agent-browser open "http://127.0.0.1:3000/changed-route"
agent-browser set viewport 1440 900
```

Reuse the running app and safe test auth. Do not record login, MFA, installation, server startup, or exploration.

## Explore, reset, replay

```bash
agent-browser snapshot -i -c
agent-browser find role button click --name "Save"
agent-browser wait --text "Saved"
```

Find stable roles, labels, text, or test IDs. Set up safe test data, complete the flow once, then reset to a known starting state before capture.

## Interaction

```bash
agent-browser console --clear >/dev/null
agent-browser errors --clear >/dev/null
agent-browser record start "$PROOF_DIR/frontend/demo.webm" --fps 12
agent-browser find role button click --name "Save"
agent-browser wait --text "Saved"
agent-browser screenshot "$PROOF_DIR/frontend/final.png"
agent-browser record stop

"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type video --path "$PROOF_DIR/frontend/demo.webm" \
  --label "Save flow" --role primary \
  --observed "Saving updates the visible state." --proves

"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type screenshot --path "$PROOF_DIR/frontend/final.png" \
  --label "Saved state" --role final
```

Keep the recording short. It must show the state before the action, the action itself, and the result. The comment already states what happened, so do not write a second caption that repeats it.

## Static change

Use one final screenshot for a visible result with enough context. Use a before/after pair at the same viewport when the comparison matters:

```bash
"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type screenshot --path /tmp/before.png --label "Before" --role before

"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type screenshot --path /tmp/after.png --label "After" --role after \
  --observed "The action is now visible beside the title." --proves
```

Do not use full-page screenshots unless the claim spans the page. Use `screenshot --annotate` only when one control needs a pointer.

## Optional diagram

A small diagram may follow the real check when it makes a data flow or architecture change easier to understand:

```bash
"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type diagram --path /tmp/flow.svg --label "Request flow" --role detail
```

A diagram cannot use `--proves`.

## Diagnostics and safety

Collect console and page errors once after replay. Keep them under `What I ran`. Do not upload raw HAR files or broad logs. Inspect every frame for credentials, PHI, customer data, and private messages before publishing.
