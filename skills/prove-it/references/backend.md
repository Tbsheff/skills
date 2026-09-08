# Backend checks

For backend-only work, record the value, response, state change, or trace that matters. Then generate a small behavior diagram from those recorded facts:

```bash
"$PROVE_IT" visualize --dir "$PROOF_DIR"
```

The diagram shows `behavior checked → code path → observed result` for up to three claims. It uses the claim text, code references, capture SHA, and observed values already in the manifest. The command, API call, or state check remains the proof. Do not replace it with the diagram.

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

The visible comment shows the concrete value. The command, assertions, and bounded output stay under `What I ran`.

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

## Jobs and queues

Match the check to the claim. An enqueue response only proves the job was queued. If the claim is about completion, check worker consumption and resulting state.

## Authorization

When a boundary changed, check both sides when practical:

1. Allowed actor succeeds.
2. Denied actor gets the intended response.
3. A denied mutation leaves state unchanged.

## Failure

Keep failed checks. Say what happened. Do not replace them with a weaker passing check.
