# Prove It

A Claude Code and Codex skill that creates focused runtime proof for changed code. It can run before a commit or pull request. When the work is already on a pull request, it can leave the same proof as a short QA comment.

```text
/prove-it
/prove-it 123
/prove-it https://github.com/owner/repo/pull/123
```

The model can also invoke Prove It after it changes code or when runtime proof would make a result easier to check.

The default proof is deliberately small:

```markdown
## QA

Tested on `abc1234`.

- The changed behavior did what the reviewer cares about.

[real video or screenshots when useful]

<details><summary>What I ran</summary>...</details>
```


For a UI-facing change, it requires a visual claim and uses the real app path when that path is reachable. Tests can support that proof but cannot replace the screenshot or video. For backend-only work, it generates a compact check summary with visible status labels, complete observed results, and optional input/result rows. The runtime receipt remains the proof.

With a scenario file, Prove It runs the change on both sides: the base commit in a temporary git worktree, and the change in the working tree. It makes pictures and short videos from those runs: a click GIF, a base/change video, test, API, database, and query-count cards, and a Mermaid request flow. Every card names both commits and the capture file it came from. See [references/scenario.md](references/scenario.md).

When other sessions share the checkout, `init --pin` runs every command in a pinned worktree of the tested commit, so a branch switch cannot change the result.

On a dirty worktree or a branch with no pull request, Prove It renders `proof.md` and its media locally. It does not stop to ask for a commit or pull request. On a clean pull request branch, it posts the proof as a comment. It never creates a pull request, rewrites its description, emits checklists, or waits for CI.

## Storage

Runs use `$TMPDIR/prove-it-pr-*`, with `local` in the name for local runs. Successful uploads delete the directory. Local proof stays in its temp directory so it can be opened. Nothing is stored in `.git` or committed to the branch.

## Install

Install it globally for Codex and Claude Code:

```bash
npx skills add Tbsheff/skills --skill prove-it --global --agent codex claude-code --yes
```

Claude Code and Codex can invoke the skill from its description. `context: fork` keeps the proof work out of the main conversation context.

## Requirements

- Python 3.10+
- git
- GitHub CLI with `gh pr comment --attach`
- `agent-browser` 0.38 or later, with Chrome, for frontend checks
- `ffmpeg` and ImageMagick 7 (`magick`) for base/change media and the backend PNG visual
- `ffprobe` only for video-duration checks

The helper has no Python package dependencies.

## Check

```bash
scripts/prove-it doctor
python3 scripts/validate_skill.py --self-test
scripts/prove-it publish --dir "$PROOF_DIR" --dry-run
```
