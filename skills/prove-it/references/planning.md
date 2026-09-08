# Plan the check

Use the PR diff as the source of truth. Decide what another developer would actually want to see.

## Pick the artifact

| Change | Default |
|---|---|
| Interactive UI | One short demo; add a final screenshot only if it adds something |
| Visual or layout change | Before/after screenshots |
| Frontend plus backend | Demo or screenshot plus one direct backend check |
| Backend or library only | Concrete response, state change, trace, or command output |
| Architecture-heavy change | Optional diagram after the real check |
| Docs, config, behavior-preserving refactor | No runtime check unless the human asks |

Do not record a video when there is no meaningful sequence. Do not generate a dashboard that restates statuses.

## Choose behaviors

Use at most three. Write each as something a person can observe.

Good:

- Saving a review keeps the selected reviewer.
- Reloading the queue shows that reviewer.
- A user from another organization gets `403`.

Bad:

- The resolver was refactored.
- Tests pass.
- The page works.

```bash
"$PROVE_IT" claim --dir "$PROOF_DIR" \
  --text "Saving a review keeps the selected reviewer." \
  --expected "A fresh read returns reviewer-test." \
  --method test \
  --code "src/server/reviews/create-review.ts:42-91"
```

When recording the result, write the sentence you would actually leave on the PR:

```text
A fresh read returned reviewerId=reviewer-test.
```

Avoid "verified successfully", "evidence shows", and similar report language.

## Extra path detail

Only add `review-step` entries when the path will help someone debug or inspect the implementation. They are hidden under `What I ran`, not shown in the main comment.

## Caveats

Add a note only when the caveat changes how the result should be read:

- `I didn't test concurrent reviewer updates.`
- `I used a fake speech voice because the test browser had no system voices.`

One important caveat may stay visible. Extra notes are folded into `What I ran`.
