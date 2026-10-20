# Share the proof

## Local mode

For uncommitted or pre-PR work, validate and render the proof locally:

```bash
"$PROVE_IT" validate --dir "$PROOF_DIR"
"$PROVE_IT" render --dir "$PROOF_DIR"
```

Return the paths to `proof.md` and its useful media. Keep the run directory. Say that nothing was published. Do not ask for a commit or pull request, and do not call `publish`.

`render` writes `proof.template.md` with `{{media:NAME}}` placeholders, and `proof.md` with those placeholders replaced by relative paths. Open `proof.md` to see the media locally.

## PR mode

The capture SHA is fixed when `init` starts. A later PR commit does not cancel the run.

## Comment rules

- `## QA`, then one sentence that names the tested commit and the base.
- At most one autoplaying GIF is visible. Other media goes into `<details>`.
- A Mermaid flow stays inline as a code block in `<details>`. It is not an image.
- Cards are at most 1600px wide.
- Every card comes from a capture file. `validate` fails when a card has no capture or no base and change SHA.
- Query counts are the claim. Latency is direction only.

## Comment shape

Keep the visible comment as small as the result allows:

```markdown
## QA

Tested on `abc1234`.

- The reviewer shows up in the queue after save.
- A fresh read returns `reviewerId=reviewer-test`.

[video or screenshots]

<details>
<summary>What I ran</summary>
...
</details>
```

For a visual-only change, one observation plus before/after screenshots may be enough. For a backend-only change, include the generated backend check visual and its runtime receipt.

Do not add headings such as `Demo`, `Backend`, `Runtime evidence`, `Path I checked`, or `Observed`. Do not repeat a fact in both visible prose and a visible receipt. Commands and receipts belong under `What I ran`.

When the PR moves after capture, say so in one or two plain sentences and still post the result:

```text
Tested on abc1234. The PR is now def5678.
I didn't rerun the latest head. review-row.tsx changed afterward.
```

## Upload

```bash
"$PROVE_IT" publish --dir "$PROOF_DIR"
```

Before the upload, `publish` replaces each `{{media:NAME}}` with the local path. `gh pr comment --attach` then replaces the path with the uploaded URL. If any placeholder is left, `publish` fails and posts nothing.

To see the final body without a post or an upload:

```bash
"$PROVE_IT" publish --dir "$PROOF_DIR" --dry-run
```

It prints the body with fake URLs and writes `comment.dry-run.md`. It also works for a local run.

`publish` checks the recorded capture SHA, not the live `HEAD` of the shared checkout. It checks for a clean tree only in the checkout where the commands ran: the pinned worktree, or the shared checkout while it is still at the capture SHA. The error names each dirty file. Add generated files to `ignore_dirty` ([configuration.md](configuration.md)).

GitHub returns HTTP 500 for SVG attachments. `publish` refuses to post SVG media and names the files. Convert each file to PNG first. A backend visual from an older run is made again as PNG.

The helper uses `gh pr comment --body-file ... --attach ...`. Each invocation creates one comment, verifies that GitHub replaced local media paths, refreshes the commit sentence if the PR moved during upload, and deletes the temp directory.

CI is separate. Do not poll or wait for it.

Use `publish --keep` only while debugging. Remove a retained run with:

```bash
"$PROVE_IT" cleanup --dir "$PROOF_DIR"
```
