# Prove It

A **human-invoked** Claude Code skill that attaches concise runtime proof to an **existing GitHub pull request**.

It is intentionally not part of PR creation. The human runs it when they want proof:

```text
/prove-it
/prove-it 123
/prove-it https://github.com/owner/repo/pull/123
```

The skill:

- binds proof to the PR's current head SHA
- derives a few observable claims from the PR diff
- uses targeted commands/API checks for backend claims
- uses `agent-browser` for screenshots and short interaction videos
- updates the existing PR with `gh pr edit --attach`
- removes its temporary local artifacts after a successful upload

## Storage

Normal runs use `$TMPDIR/prove-it-pr-*`, never `.git` or the source branch. Successful publication deletes the temp directory immediately. Old abandoned temp runs are pruned after 24 hours.

The durable artifact is the PR body plus GitHub-hosted image/video attachments.

## Install

Copy this directory to:

```text
~/.claude/skills/prove-it/
```

or:

```text
.claude/skills/prove-it/
```

Do **not** add it to a create-PR hook.

## Requirements

- Python 3.10+
- git
- current GitHub CLI with `gh pr edit --attach`
- `agent-browser` for frontend proof
- `ffprobe` optional for video-duration validation

The helper has no Python package dependencies.

## Check

```bash
scripts/prove-it doctor
python3 scripts/validate_skill.py --self-test
```

See `SKILL.md` for the workflow and `TESTING.md` for evaluation notes.
