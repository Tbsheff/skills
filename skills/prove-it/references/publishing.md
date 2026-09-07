# Publishing proof to an existing PR

`prove-it` never creates a pull request. The PR must exist before the skill is invoked.

## Durable versus temporary state

Temporary evidence lives under `$TMPDIR/prove-it-pr-*` while the run is active. The durable copy is stored by GitHub:

- text proof -> PR body
- screenshots/video -> GitHub user attachments uploaded by `gh pr edit --attach`

Nothing is committed to the feature branch and nothing is stored under `.git` by default.

## Publish command

The helper performs the complete publish transaction:

```bash
scripts/prove-it publish --dir "$PROOF_DIR"
```

Conceptually it runs:

```bash
cd "$PROOF_DIR"
gh pr edit <number> \
  --repo <owner/repo> \
  --body-file ./pr-body.md \
  --attach ./frontend/final.png \
  --attach ./frontend/demo.webm
```

The generated Markdown references attachments with local relative paths. GitHub CLI rewrites those references to GitHub-hosted URLs during upload.

## Existing PR body

`publish` fetches the current PR body with `gh pr view`. It replaces only its own `<!-- prove-it:start --> ... <!-- prove-it:end -->` block and preserves the rest of the PR description, including any human-authored `## Proof` section.

## Freshness gate

Immediately before `gh pr edit`, publication fails if:

- GitHub's current PR head SHA differs from the SHA recorded at init
- local `HEAD` differs from that SHA
- the local worktree is dirty
- evidence validation finds corruption, missing files, or likely secrets

A proof must describe the exact revision a reviewer sees.

## Cleanup

Successful publication deletes the temporary proof directory automatically.

Use:

```bash
scripts/prove-it publish --dir "$PROOF_DIR" --keep
```

only for debugging. If an upload fails, the temp directory remains so it can be retried; remove it with:

```bash
scripts/prove-it cleanup --dir "$PROOF_DIR"
```

New runs prune abandoned Prove It temp directories older than 24 hours.

## Permissions and CLI support

`gh pr edit --attach` requires a GitHub CLI version that supports attachment upload and GitHub permissions sufficient to edit the PR. `scripts/prove-it doctor` checks for the flag before a run is published.
