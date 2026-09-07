# Papercuts and fixes

| Papercut found | Why it mattered | Optimization made |
|---|---|---|
| Server-rendered UI in a Python file was classified as backend-only. | Path/extension heuristics would skip the browser for FastAPI, Flask, Rails, PHP, and similar templates embedded in code. | Scan added diff lines for a conservative combination of HTML elements and browser/server-rendering signals. The FastAPI fixture now selects `mixed`. |
| Normal Python startup cost about 0.6 seconds per helper call in the sandbox. | Small proofs spent more time loading site packages than checking behavior. | The executable launcher uses `python3 -S`; the helper has no third-party imports. End-to-end orchestration fell 62–87%. |
| The first PR projection printed an entire inline test program in the evidence table. | It made the proof harder to scan than the implementation itself. | The table now shows a human evidence label. Exact commands stay in the manifest/log and are truncated in a collapsible detail. |
| Supporting console and page-error files cluttered the main table. | “Browser console, Page errors” competed with the actual screenshot/video. | Supporting diagnostics moved to details and empty files render as “no output” / “none.” |
| Static UI could easily trigger unnecessary video. | Video startup, encoding, upload, and review all cost more than a screenshot. | The classifier has an explicit screenshot mode, and policy forbids video unless temporal interaction matters. |
| Re-running proof could append duplicate verification blocks or overwrite a human-authored `## Proof` section. | PR bodies would accumulate stale evidence or lose reviewer context. | `compose` now replaces only a marker-delimited `## Prove It` block and preserves all human-authored sections. |
| An invalid explicit base silently fell through to another available branch. | A plausible report could be generated from the wrong diff. | Explicit, environment, and configured base refs now fail closed when missing. |
| A custom header loaded from an environment variable appeared in the HTTP evidence log. | Generic header names cannot be safely redacted by token-name heuristics. | Environment-backed headers are always represented as `[FROM_ENV:VARIABLE]`; their values are never written. |
| Imported evidence could be changed after registration. | A reviewer report could no longer correspond to the recorded bytes. | Every file records SHA-256; strict validation detects missing or modified evidence. |
| Worktree-local artifact directories risked dirtying the branch. | The proof mechanism should not create implementation changes. | Default output moved under the repository’s git directory: `.git/.../prove-it`. |
| Recording exploration would produce slow, noisy “agent thinking” videos. | Reviewers need a deterministic demonstration, not retries and selector discovery. | The skill separates unrecorded exploration from one clean replay; recording starts only after the page is ready. |
| Media publication originally appeared to require committing binaries. | Screenshots/video would bloat feature branches and repository history. | The publishing path uses current `gh pr edit --attach` and fails explicitly when attachment support is unavailable. |
| Shell arguments could expose authorization values. | Process lists and shell history may retain secrets even when logs are redacted. | The HTTP helper supports `--header-env HEADER=ENV_VAR`; the skill prefers vault/session auth for browsers. |

## Remaining environment-specific papercuts

- Exact `agent-browser` runtime behavior still needs one smoke test in the target Claude environment.
- Authentication restore behavior must be configured per repository; no generic skill can safely infer production credentials.
- GitHub attachment rewriting requires a sufficiently recent `gh`; `doctor` reports support and the workflow has no binary-commit fallback.
- Windows was not exercised. The core Python helper is portable, but the convenience launcher and generated attachment array are POSIX shell/Bash oriented.

## Human-invoked PR lifecycle changes (v1.1)

| Papercut | Why it matters | Optimization |
|---|---|---|
| Skill was discoverable during PR creation. | Proof should be a deliberate reviewer action, not latency added to every PR. | Frontmatter and workflow now explicitly require human invocation and an already-existing PR; all create-PR integration was removed. |
| Default artifacts lived under `.git/prove-it`. | Videos/screenshots can accumulate indefinitely and consume local disk. | Default runs now use `$TMPDIR/prove-it-pr-*`; successful publication deletes the run, and runs older than 24h are pruned on later invocations. |
| Proof was conceptually coupled to `gh pr create`. | The user wants to prove an existing PR after deciding the evidence is useful. | `init --pr` binds to an existing PR and `publish` exclusively uses `gh pr edit --attach`; `prove-it` never creates PRs. |
| A PR could advance while proof was being captured. | Reviewers could see evidence for an older commit. | Init and publish both bind to the exact `headRefOid`; publication fails if GitHub or local HEAD changes. |
| Local uncommitted changes could leak into browser/runtime proof. | Evidence might represent code not present in the PR. | PR-bound runs require a clean worktree at init and again at publish. |
| Replacing any `## Proof` section could overwrite human-authored content. | The skill should not own arbitrary PR prose. | Generated content is wrapped in `<!-- prove-it:start/end -->` and only that block is replaced on reruns. |
| Successful helper output printed temp paths that were immediately deleted. | Claude could surface confusing dead paths to the human. | `publish` suppresses internal render/compose paths and returns the PR URL and compact publish result only. |
