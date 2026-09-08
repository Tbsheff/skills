# Prove It

A human-invoked Claude Code and Codex skill that leaves a short QA comment on an existing GitHub pull request.

```text
/prove-it
/prove-it 123
/prove-it https://github.com/owner/repo/pull/123
```

The default comment is deliberately small:

```markdown
## QA

Tested on `abc1234`.

- The changed behavior did what the reviewer cares about.

[real video or screenshots when useful]

<details><summary>What I ran</summary>...</details>
```


For a UI-facing change, it requires a visual claim and uses the real app path when that path is reachable. Tests can support that proof but cannot replace the screenshot or video. For backend-only work, it generates a compact diagram from the recorded behavior, code path, and observed result while keeping the runtime receipt as the proof. It does not rewrite the PR description, emit checklists, generate a proof dashboard, or wait for CI. If the PR moves while the check is running, the comment still gets posted and says which commit the media came from.

## Storage

Runs use `$TMPDIR/prove-it-pr-*`. Successful uploads delete the directory. Nothing is stored in `.git` or committed to the branch.

## Install

Install it globally for Codex and Claude Code:

```bash
npx skills add Tbsheff/skills --skill prove-it --global --agent codex claude-code --yes
```

Claude Code uses `disable-model-invocation: true` and `context: fork`. Codex uses `agents/openai.yaml` to keep the skill explicit-only.

## Requirements

- Python 3.10+
- git
- GitHub CLI with `gh pr comment --attach`
- `agent-browser` for frontend checks
- `ffprobe` only for video-duration checks

The helper has no Python package dependencies.

## Check

```bash
scripts/prove-it doctor
python3 scripts/validate_skill.py --self-test
```
