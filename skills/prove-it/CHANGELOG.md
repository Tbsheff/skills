# Changelog

## 2.2.1

- UI `--proves` passes only when `expect_text` shows on change after the flow, and does not show on base or on change before the flow. A failed base step gives `not_proven`, unless the step has `"base": {"may_fail": true}`. `text_may_show_before` allows text that was already on the page.
- Backend `--proves` needs real assertion failures on base. The tool reads unittest, pytest, vitest, and jest summaries. A timeout, exit 126, 127, or 128+, an import or collection error, or zero tests on base gives `not_proven` with the reason. The card says "did not run".
- No output shows a `fill` value, and errors hide the command arguments. A password target or a token-like literal needs `text_env`.
- Servers stop at the end of a run by default. `serve.keep` or `PROVE_IT_KEEP_SERVERS=1` keeps a base server. Before a stop, the tool checks the PID's start time, command, and process group, so a reused PID is never killed. Kept servers stop after 4 hours.
- Each cache use runs `git clean -ffdx` except the dependency dirs, then `setup` again. Schema files (for example `schema.prisma`) are part of the cache key.
- The tool refuses a `node_modules` link in a package workspace. `draft` proposes `pnpm install --frozen-lockfile --offline` there.
- `scenario` and `media` refuse any `TODO` placeholder in any string, not only a `todo` list.
- `draft` uses the merge base when `--base` is missing, warns when the base is not an ancestor of `HEAD`, and takes `--dir`. `media` warns when `refs.base` is not the merge base.
- With `init --pin`, the pinned change tree gets the same `setup` from the user's checkout.

## 2.2.0

- UI media runs a flow of steps: `goto`, `click`, `fill`, `press`, `select`, `wait_text`, `wait_ms`, and `expect_text`. A target is a CSS selector or a role and name. The single `click` form still works. The storyboard has one keyframe for each step. The verdict rule does not change.
- The base worktree stays in `~/.cache/prove-it/worktrees/`, with its dependencies, keyed by SHA, lockfiles, and setup. It keeps 3 for each repo and locks each one while a run uses it. A base server stays up and the next run uses it after a health check. `scripts/media/shared/wtcache.py list|stop|clear`. `media --no-cache` turns it off.
- `reuse_url` and `reuse_check` use a dev server that you run for the change side.
- Base and change capture at the same time in two browser sessions. Cards render in parallel, and the video crop runs on smaller frames. The gallery demo went from 158 s to 24-35 s.
- `media` makes only the cards that the comment shows and the details cards that the scenario asks for. `media --all-media` makes all of them. The `media` output has `timings`, `media_skipped`, and `checkouts`.
- Added `prove-it auth login NAME --url URL`. It saves a login outside the repo (mode 600). A scenario uses it with `"auth": {"name": "NAME"}`. The tool refuses credentials in a scenario and masks auth-looking values in the media data. `redact_selectors` blurs private text.
- Added `prove-it draft --base REF`. It reads the diff and proposes a scenario: routes, API handlers, tests, and the dev command and port. `scenario` and `media` refuse a scenario that still has `todo` items.
- The recording scale comes from the real video size. agent-browser can record at CSS size.
- Removed `browser.record_fps` from the example config. No tool read it.

## 2.1.0

- The scan no longer marks every path with a `public/` folder as `frontend`. A `public/` or `static/` folder is `frontend` for static files, or when it is an asset root such as `apps/web/public/`. A code file in a deeper `public/` folder, such as `apps/*/lib/core/<context>/public/*.ts`, is `backend`.
- Added the `classify` config key. It maps a path glob to a kind and overrides the scan.
- Commands that change the manifest now hold a file lock. Parallel `run`, `add`, and `claim` commands on one proof directory no longer lose claims or evidence.
- Added `init --pin`. It makes a detached worktree of the capture SHA at `$PROOF_DIR/checkout`. `run` and `media` run there. `publish` and `cleanup` remove it. The shared checkout is not changed.
- `run` refuses to start when its checkout is not at the capture SHA. Each receipt records the `HEAD` it ran at, and `validate` fails when that is not the capture SHA.
- `publish` checks the recorded capture SHA, not the live `HEAD` of the shared checkout.
- `visualize` writes a PNG (ImageMagick, rsvg-convert, or agent-browser). `publish` refuses SVG media, because GitHub returns HTTP 500 for SVG attachments. An older SVG backend visual is made again as PNG.
- `run --command` runs in bash with globs off, so `*.pkl` stays literal. Add `--glob` to expand globs.
- Added the `ignore_dirty` config key for generated files. The clean-tree errors name each dirty file.
- `run` writes a partial receipt while the command runs. A killed run keeps its output. On SIGTERM, `run` stops the command group and records a failed check.
- `validate_skill.py` accepts a skill directory as a positional argument and prints a clear usage.

## 2.0.0

- Added `prove-it media`. It runs one scenario on the base (a temporary git worktree) and on the change (the working tree), then registers the media as evidence. It never switches branches or stashes.
- Added the UI media tools: a click GIF with a visible cursor, a base/change twin video, a wipe, keyframes, states, viewports, and change boxes.
- Added the backend media tools: red/green tests, API diff, database row, query count and latency, probe table, and a Mermaid request flow from the server trace log.
- Added `prove-it scenario` to check a scenario after the project config merge and the base/change resolution.
- Added `references/scenario.md`. A scenario reads `app.start`, `browser.viewport`, and area routes and tests from the project config when it does not set them.
- `render` now writes `proof.template.md` with `{{media:NAME}}` placeholders and a local `proof.md` with relative paths.
- `publish` fails when a placeholder is left. `publish --dry-run` prints the final body with fake URLs and posts nothing.
- `validate` now fails for more than one visible GIF, media wider than 1600px, or a card with no capture file or no base and change SHA.
- The comment names the base commit when media ran on both sides.
- `--proves` for backend needs tests that fail on base and pass on change. Tests that pass on both sides give `not_proven`, and the card title shows the real result.
- `--proves` for UI needs `expect_text` on the change page after the click, and absent on base or before the click.
- Servers run in their own process group with output in a log file. A failed start shows the last 20 lines of the log. Every exit path stops the servers and removes the base worktree. A timeout or Ctrl-C gives the tools time to clean up.
- Added `setup` (link, copy, command) for the base worktree, a `python` key with venv detection, `ready_timeout`, and test and probe timeouts.
- Every capture is redacted before a card is drawn.
- A media claim needs claim text. `validate` fails on empty claim text. Base and change on the same clean commit now fail at once. Media names get a counter on a collision.
- `doctor` now checks agent-browser 0.38+ with `record`, Chrome, ffmpeg, and ImageMagick. Media tools force `AGENT_BROWSER_ENGINE=chrome`.

## 1.10.0

- Made the skill available for model invocation in Claude Code and Codex.
- Added a local proof path for dirty worktrees and branches with no pull request.
- Labeled local Markdown and backend visuals as proof of working-tree changes.
- Kept pull request publishing strict: it still needs a clean worktree whose `HEAD` matches the pull request head.
- Replaced the pre-PR stop with local `validate` and `render` output.

## 1.9.0

- Replaced the fixed three-column backend flow chart with full-width check cards that grow with their content.
- Added visible status words so backend results do not rely on color alone.
- Added optional input/result rows for validation rules and other example-driven checks.
- Shortened code labels in the visual while keeping exact linked paths under `What I ran`.
- Removed repeated observation bullets when the backend visual is present.
- Moved the first backend scope note above the visual.

## 1.8.0

- Required every UI-facing proof run to include a browser, screenshot, or video claim.
- Made the real app route the default visual target and limited component fixtures to components with no reachable route.
- Blocked text-only passed proof for frontend and mixed changes while allowing an honest `not_proven` visual claim when the app cannot run.
- Clarified that an interactive demo must show the state before the action, the action, and the result.
- Added an evidence-backed backend diagram that maps each checked behavior through its code path to the observed result.
- Made publishing generate the backend diagram when a backend-only run does not already include one.

## 1.7.0

- Reduced the visible comment to `## QA`, one commit sentence, up to three observations, real media, and at most one important caveat.
- Removed visible `Demo`, `Backend`, and `Path I checked` sections.
- Moved backend receipts, review paths, code anchors, diagnostics, and extra notes under `What I ran`.
- Stopped repeating runtime values in both the observation bullets and a separate backend section.
- Simplified moving-head language while keeping proof tied to the captured SHA.

## 1.6.0

- Rewrote the visible PR comment to sound like a developer QA note instead of a status report.
- Removed GitHub status callouts, evidence inventories, freshness labels, runtime-evidence tables, repeated media captions, and repeated expected/observed prose.
- Frontend comments now lead with plain observations and real media; backend checks show concrete values or responses.
- Collapsed technical output under a single `What I ran` section.

## 1.5.0

- Added one opening GitHub callout that combines verdict, captured/current SHA, up to three concrete observations, and evidence inventory.
- Replaced top-level raw receipt blocks with a compact two-column runtime-evidence table.
- Changed multi-layer review paths into a short arrow flow when they fit on one line.
- Removed the separate observed section and moved raw commands, assertions, output, code anchors, and diagnostics into one disclosure.
- Kept point-in-time SHA refresh inside the opening callout when the PR advances during upload.
- Fixed upload-time head refresh so it preserves the rendered verdict instead of reverting the callout to `No runtime proof`.

## 1.4.0

- Changed publishing from PR-description edits to one new `gh pr comment --attach` receipt per invocation.
- Removed the generated proof-map SVG and top-level claim counts.
- Made frontend comments lead with real video or screenshots.
- Added compact backend receipts with observed values, assertions, and bounded output excerpts.
- Added a causal `What happened` section for full-stack flows.
- Moved commands, code anchors, and diagnostics into one collapsed section.
- Added exact-comment verification and relationship refresh when the PR moves during upload.

## 1.3.0

- Replaced the claim-status table with visual-first PR output.
- Embedded videos as GitHub inline players instead of ordinary links.
- Rendered all screenshots inline, including before/after pairs.
- Added optional diagram evidence and an automatically generated SVG proof map.
- Moved commands, code anchors, notes, and warnings into collapsed details.
- Added presentation roles for primary, before, after, final, and detail media.
- Required passed browser claims to include screenshot or video evidence.

## 1.2.0

- Added `disable-model-invocation: true`; only a human can run `/prove-it`.
- Added `context: fork` so the task does not fill the main conversation context.
- Cut `SKILL.md` from 300 lines to a small router with on-demand references.
- Replaced placeholder paths with `${CLAUDE_SKILL_DIR}`.
- Changed head movement from a publish blocker to a labeled point-in-time relationship.
- Added claim code references and an optional five-step review path.
- Removed the default HTML report and generated attachment shell script.
- Reduced abandoned temp-run cleanup from 24 hours to one hour.
- Removed developer evaluation files and examples from the release package.

## 1.1.0

- Made the skill human-invoked and existing-PR only.
- Moved proof files to `$TMPDIR` and added GitHub attachment upload and cleanup.
