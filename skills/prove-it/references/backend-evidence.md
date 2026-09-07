# Backend evidence

## Targeted tests

Use the narrowest test selector that asserts the claim. Record the exact command, exit code, duration, and semantic assertion. Avoid the full suite.

Good:

```bash
pnpm vitest run src/server/reviews/create.test.ts -t "persists reviewer"
```

Weak:

```bash
pnpm test
```

The broad command may pass while giving reviewers no confidence about the changed behavior.

## Direct API assertions

Use the helper’s `http` command for local/dev endpoints. Assert status plus the smallest meaningful response property. For authorization, test both the allowed and denied actor when both are part of the change.

```bash
"$PROVE_IT" http --dir "$PROOF_DIR" --claim C1 \
  --label "Reject cross-org read" \
  --url "http://127.0.0.1:3000/api/reviews/test-id" \
  --header "Authorization: Bearer <test-token-from-safe-env>" \
  --expect-status 403 --proves
```

The helper redacts common token shapes in text output, but avoid placing secrets in arguments whenever possible.

## Database/state changes

Prefer a single script that performs:

```text
read before -> invoke action -> read after -> assert transition
```

The script should exit nonzero on mismatch and print only identifiers and fields necessary to establish the claim. Use temporary/local databases and deterministic test records.

## Asynchronous jobs

A successful enqueue does not prove successful processing. Depending on the claim, assert one of:

- queued job payload
- worker consumption
- durable resulting state
- idempotent replay
- explicit failure/dead-letter result

Capture the narrowest stage named by the claim.

## Authorization and tenant boundaries

For a boundary change, prove the actor, resource scope, request, and outcome. A single allowed request is not enough when the changed behavior is denial. Prefer:

1. same-tenant actor succeeds
2. cross-tenant actor receives the intended denial
3. no state changed for the denied request, when mutation is possible

## Commands that are not proof

The following are supporting checks unless their assertions directly encode the claim:

- build
- typecheck
- lint
- broad test suite
- process startup
- schema generation

CI already communicates these well. Keep them out of the reviewer-facing proof table unless directly relevant.
