
## 1.1.0 — Human-invoked existing-PR workflow

- Changed activation semantics: `/prove-it` is explicit/human-invoked only and is never part of PR creation.
- Added existing-PR binding with `gh pr view` and exact PR head SHA validation.
- Changed default artifact storage from `.git/prove-it` to ephemeral `$TMPDIR/prove-it-pr-*` directories.
- Added automatic cleanup after successful publication and 24-hour abandoned-run pruning.
- Added `publish`, which updates the existing PR with `gh pr edit --body-file ... --attach ...`.
- Added `cleanup` for safe manual removal of failed/debug runs.
- Added stale-head and dirty-worktree publication guards.
- Added marker-delimited `## Prove It` blocks so human-authored PR sections are preserved.
- Added self-test coverage for temp storage, attachment rewriting, cleanup, stale PRs, and dirty worktrees.
