# Testing and optimization

## What was exercised

The skill was run end to end against reconstructed local git fixtures based on current files fetched from three open-source repositories. A small synthetic feature commit was applied to each fixture so the expected behavior was known and the proof decision could be evaluated independently of an upstream PR description.

| Repository | Change shape | Expected proof | Result | Final wall time |
|---|---|---|---|---:|
| `sindresorhus/escape-string-regexp` | Library/API behavior | Targeted backend assertion; no browser | Passed | 0.46s |
| `h5bp/html5-boilerplate` | Static HTML/CSS | One screenshot; no video | Passed | 1.25s |
| `fastapi/fastapi` | API plus HTML/JavaScript in a Python response | Direct HTTP assertion plus one UI flow, screenshot, and short video | Passed | 3.78s |

The final manifests passed strict validation with no integrity, budget, or secret findings. The mixed run generated a valid 1440×900 VP9 WebM at 12 FPS with a three-second duration.

Detailed machine-readable results and generated proof artifacts are in `evals/`.

## Runtime caveat

The evaluation sandbox could not download or install the exact `agent-browser` binary because outbound package/GitHub downloads were unavailable. The current `agent-browser` command contract was checked against the official v0.36.0 source and command reference. Browser interaction, semantic assertions, screenshots, console/page-error collection, and WebM generation were exercised with a Playwright compatibility harness over Chromium.

A Chromium administrator policy in this sandbox also blocked URL navigation. The browser harness therefore rendered the fetched open-source markup directly. In the FastAPI case, the actual local `/api/status` endpoint was exercised separately through Uvicorn and the helper’s HTTP assertion; the browser-side fetch was fulfilled by the harness to test the interaction artifact. This is not a substitute for one final smoke run with the installed `agent-browser` CLI in the target Claude environment.

GitHub CLI was not installed in the sandbox with credentials to a writable test PR. Publication behavior is therefore covered with a fake `gh` executable in self-tests, while the real `gh pr edit --attach` flag and attachment-rewrite contract were checked against the current official GitHub CLI manual.

## Optimization passes

Initial orchestration used normal Python startup for every helper action. In this environment that incurred roughly 0.58–0.62 seconds per invocation before useful work. Because `prove.py` uses only the standard library, the packaged `scripts/prove-it` launcher runs `python3 -S`, skipping site-package initialization.

| Case | Initial | Final | Reduction | Speedup |
|---|---:|---:|---:|---:|
| Backend-only | 3.60s | 0.46s | 87.3% | 7.9× |
| Static UI | 5.51s | 1.25s | 77.4% | 4.4× |
| Mixed API/UI | 10.05s | 3.78s | 62.4% | 2.7× |

The remaining mixed-case time was dominated by actual browser rendering and video encoding rather than manifest bookkeeping.

## Automated checks

Run:

```bash
scripts/prove-it doctor
python3 scripts/validate_skill.py --self-test
```

The self-test covers:

- backend diff classification
- focused command evidence
- local HTTP and JSON assertions
- environment-backed sensitive headers
- secret redaction
- screenshot metadata and hashing
- evidence tamper detection
- strict claim validation
- PR Proof-section replacement without duplication
- invalid explicit base failure
- docs-only no-proof rendering
- generated attachment metadata
- internal Markdown-link and package-structure validation

## v1.1 human-invoked PR lifecycle

The human-invoked flow adds automated coverage for the lifecycle requested for real PR review:

- resolves an existing PR through a simulated `gh pr view`
- requires local HEAD to match the PR head SHA
- rejects dirty working trees for PR-bound proof
- creates the default run outside `.git` in the OS temp directory
- publishes with the `gh pr edit --body-file ... --attach ...` command shape
- verifies media references are rewritten to GitHub-hosted attachment URLs
- removes the temporary proof directory after successful publication

The test uses a fake `gh` executable because GitHub credentials and a writable test PR are intentionally not required for package self-tests. The actual attachment flag and rewrite semantics were checked against the current official GitHub CLI manual before packaging v1.1.
