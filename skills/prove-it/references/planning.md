# Plan the check

Use the PR diff as the source of truth. Decide what another developer would actually want to see.

## Pick the artifact

| Change | Default |
|---|---|
| Interactive UI | One short real-app demo that shows the start, action, and result |
| Visual or layout change | Real before/after screenshots at the same viewport |
| Frontend plus backend | Real-app demo or screenshot plus one direct backend check |
| Backend or library only | Concrete runtime receipt plus the generated backend behavior diagram |
| Architecture-heavy change | Optional diagram after the real check |
| Docs, config, behavior-preserving refactor | No runtime check unless the human asks |

For `browser`, `screenshot`, or `mixed`, add a visual claim before any test claims. The proof is incomplete without that claim. A test can support the visual claim, but it cannot replace the screenshot or video.

Use the changed route in the real app with safe test data. Use a component fixture only when the component has no reachable app route, and say that the fixture proves rendering rather than the full flow. If the real UI cannot run, mark the visual claim `not_proven` with the concrete block.

For backend-only work, run `visualize` after the checks so the comment shows the behavior, code path, and observed result without turning command output into a screenshot.

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
