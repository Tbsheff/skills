# Backend checks

## Base and change cards

When the backend can run on both sides, capture it with a scenario. See [scenario.md](scenario.md).

```bash
"$PROVE_IT" media --dir "$PROOF_DIR" --scenario "$PROOF_DIR/scenario.json" --kind backend --proves
```

The tool runs the tests, requests, database read, timing, and probe on a base worktree and on the working tree. It writes raw JSON to `media/backend/captures/`. Every card is drawn from that JSON: `red-green.png`, `api-diff.png`, `db-state.png`, `numbers.png`, `behavior-table.png`. A server trace log also gives a Mermaid request flow. The comment shows it inline under `<details>`.

The observations come from the captures. Do not retype a number. Query counts are the claim. Latency is direction only, and the comment says so.

With `--proves`, the claim passes only when the tests fail on base and pass on change. Tests that pass on both sides do not isolate the change, so the claim is `not_proven`. Every capture is redacted before a card is drawn.

Use the steps below when there is no scenario, or for a check that the scenario cannot express.

## Summary visual

For backend-only work, record the value, response, state change, or trace that matters. Then generate a small check summary from those recorded facts:

```bash
"$PROVE_IT" visualize --dir "$PROOF_DIR"
```

`visualize` writes a PNG, because GitHub does not accept SVG uploads. It needs ImageMagick 7 (`magick`) or agent-browser.

The visual shows one full-width card per claim. It uses a written status label, a short code label, and the complete observed result. It grows to fit the content and must not hide proof behind an ellipsis. Exact linked paths remain under `What I ran`.

For validation rules, parsers, authorization matrices, or any check where examples make the result clearer, add concise input/result rows after the real check:

```bash
"$PROVE_IT" example --dir "$PROOF_DIR" --claim C1 \
  --input 'M1850="Requires assistance"' \
  --observed 'INVALID_OPTION'

"$PROVE_IT" example --dir "$PROOF_DIR" --claim C1 \
  --input 'M1850="2"' \
  --observed 'Accepted'
```

An example row summarizes evidence already recorded by a command, request, or state check. It does not prove the claim or change its status. Use no more than the rows that help a reviewer see the boundary.

## Focused test or executable example

```bash
"$PROVE_IT" run --dir "$PROOF_DIR" --claim C1 \
  --kind test \
  --label "Reviewer persistence" \
  --expect-output "reviewerId=reviewer-test" \
  --observed "A fresh read returned reviewerId=reviewer-test." \
  --proves -- \
  pnpm vitest run src/server/reviews/create.test.ts -t "persists reviewer"
```

The visual shows the concrete value once. The command, assertions, full code links, and bounded output stay under `What I ran`.

Put the command after `--` as separate words. `run` then starts it with no shell, so a glob such as `*.pkl` stays literal. Use `--command` only when you need a pipe, a redirect, or `&&`. It runs in bash with globs off. Add `--glob` to let bash expand them.

`run` writes the output to `backend/<claim>-<label>.partial.txt` while the command runs. If the command is killed, the partial receipt stays, and `validate` warns that it did not finish. On SIGTERM, `run` stops the command, keeps the output, and marks the check failed.

`run` refuses to start when the checkout is not at the capture SHA. This occurs when another session changes the branch. Start the run with `init --pin` to run every command in `$PROOF_DIR/checkout`, a detached worktree at the capture SHA. Install dependencies in that worktree first, for example `pnpm install --offline`. `run --cwd` is relative to that worktree. `publish` and `cleanup` remove it.

Avoid a full suite unless the human asks. CI already covers broad builds, lint, type checks, and test suites.

## Local API check

Keep credentials in environment variables:

```bash
"$PROVE_IT" http --dir "$PROOF_DIR" --claim C1 \
  --label "Cross-org read" \
  --url "http://127.0.0.1:3000/api/reviews/test-id" \
  --header-env "Authorization=TEST_AUTH_HEADER" \
  --expect-status 403 \
  --observed "The other organization got 403 and nothing changed." \
  --proves
```

Use `--allow-remote` only for an authorized test environment. Never target production by default.

## State changes

Prefer a focused script that prints only what the reviewer needs:

```text
reviewerId before: null
reviewerId after: reviewer-test
```

The script should do:

```text
read before -> invoke action -> read after -> assert transition
```

Use local data or clearly marked test records.

Do not stop or remove shared services, such as a shared `docker compose` project. Stop only the containers and processes that this run started.

## Jobs and queues

Match the check to the claim. An enqueue response only proves the job was queued. If the claim is about completion, check worker consumption and resulting state.

## Authorization

When a boundary changed, check both sides when practical:

1. Allowed actor succeeds.
2. Denied actor gets the intended response.
3. A denied mutation leaves state unchanged.

## Failure

Keep failed checks. Say what happened. Do not replace them with a weaker passing check.
