# Post one QA comment

The capture SHA is fixed when `init` starts. A later PR commit does not cancel the run.

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

For a visual-only change, one observation plus before/after screenshots may be enough. For a backend-only change, omit media.

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

The helper uses `gh pr comment --body-file ... --attach ...`. Each invocation creates one comment, verifies that GitHub replaced local media paths, refreshes the commit sentence if the PR moved during upload, and deletes the temp directory.

CI is separate. Do not poll or wait for it.

Use `publish --keep` only while debugging. Remove a retained run with:

```bash
"$PROVE_IT" cleanup --dir "$PROOF_DIR"
```
