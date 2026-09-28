# Scenario file

A scenario tells `prove-it media` what to run on the base side and on the change side. Write one scenario for each run. Put it in `$PROOF_DIR/scenario.json`. Use what you learned about the repo: routes, selectors, the test command, and the requests.

```bash
"$PROVE_IT" scenario --dir "$PROOF_DIR" --scenario "$PROOF_DIR/scenario.json"
"$PROVE_IT" media --dir "$PROOF_DIR" --scenario "$PROOF_DIR/scenario.json" --proves
```

`scenario` prints the scenario after the config merge and the base/change resolution. It does not capture. Run it first to find mistakes fast.

## Base and change

- **Change** is always the working tree. In PR mode, that is the PR head.
- **Base** is a git worktree from the worktree cache. The tool keeps it for the next run. See [browser.md](browser.md#speed).
- The tool never switches branches and never stashes in your checkout.

The base ref comes from the first item that applies:

1. `media --base REF`
2. `refs.base` in the scenario
3. PR mode: the merge base with the PR base branch
4. Local mode with a dirty tree: `HEAD`
5. Local mode with a clean tree: the merge base, or `HEAD~1` if the merge base is `HEAD`

If you set `refs.change`, it must point at `HEAD`. Otherwise the tool stops. The tool also stops when base is `HEAD` and the tree is clean, because then nothing changed.

## Shape

```json
{
  "name": "Settings > Profile: save feedback",
  "claim": "Clicking Save shows a spinner, then a Saved toast",
  "refs": {"base": "origin/main"},
  "ui": {
    "serve": {"cmd": "pnpm dev --port {port}", "ready_path": "/api/health"},
    "path": "/settings/profile", "viewport": [1280, 800], "context": ".card",
    "click": {"change_selector": "#save", "base_selector": "button.save", "label": "Click Save",
              "claim": "Clicking Save shows a spinner, then a Saved toast", "expect_text": ["Saved"]}
  },
  "backend": {
    "tests": {"command": "python3 -m unittest -v", "copy_from_change": ["tests"]},
    "server": {"command": ["{python}", "-m", "app.server"], "env": {"PORT": "{port}", "DB_PATH": "{db}"}, "ready_path": "/health"},
    "api": {"method": "GET", "path": "/orders?customer=c_1001", "redact_keys": ["email"]}
  }
}
```

A scenario can have `ui`, `backend`, or both. The older flat form (UI or backend keys at the top level) also works.

## Draft a scenario

Do not write the first scenario by hand. `"$PROVE_IT" draft --base REF --out "$PROOF_DIR/scenario.json"` reads the diff. It proposes the changed routes (Next.js app and pages routers), API handlers, changed tests, and the dev command and port. Each guess is in `todo`. Do each item, then remove it; `scenario` and `media` refuse a scenario with `todo` items or any `TODO` placeholder. Without `--base` it uses the merge base with the default branch, and it warns when a base is not an ancestor of `HEAD`. The draft reads only.

## UI keys

| Key | Meaning |
|---|---|
| `serve` | `{"static": "DIR"}`, or `{"cmd": "... {port} ...", "ready_path": "/", "ready_timeout": 60, "env": {}}`. Base and change run at the same time, so a command needs `{port}`. |
| `path` | The page to open. |
| `viewport`, `scale` | CSS viewport and device scale. Default `[1280, 800]` at 2x. |
| `context` | The element that holds the change. The crop keeps it whole. |
| `steps` | A list of actions for a flow with more than one step. See [Steps](#steps). |
| `click.change_selector`, `click.base_selector` | The one element to click (use `click` or `steps`), and the base element if it is different. |
| `click.label`, `click.claim` | Short label and the sentence the GIF proves. `label` and `claim` at the `ui` level do the same for `steps`. |
| `click.expect_text`, `expect_text` | Text that must be on the page after the flow. With `--proves`, this sets the claim status. |
| `click.storyboard` | Keyframes: `Name@seconds-from-click` or `Name@settle`. |
| `states`, `viewports` | `{"param": "state", "values": [...]}`: each value on the change side. `{"sizes": [[1280, 800], [375, 812]], "focus": "#save", "height_css": 300}`. |
| `setup` | Prepares the base worktree. See [Real apps](#real-apps). |
| `auth` | A saved login: `{"name": "NAME"}`. See [browser.md](browser.md#login). |
| `reuse_url`, `reuse_check`, `cache`, `media`, `all_media` | Speed options. See [browser.md](browser.md#speed). |
| `redact_selectors`, `host` | CSS selectors to blur in every capture. The host in page URLs (default `127.0.0.1`). |
| `refs.followup`, `followup` | Optional commit on top of the change, with a `title` and a `legend` for the change boxes. |

## Steps

Use `steps` for a flow with more than one action. The recording shows all steps, the cursor moves to each target, and the storyboard has one keyframe for each step.

```json
"steps": [
  {"fill": {"label": "First name"}, "text": "Sam", "base": {"fill": "input"}},
  {"click": {"role": "button", "name": "Save"}},
  {"wait_text": "Saved", "timeout_ms": 3000}
],
"expect_text": ["Saved"]
```

| Step | Meaning |
|---|---|
| `goto` | Open a path on the same server. |
| `click`, `fill` + `text`, `select` + `value` | Act on a TARGET. No output shows a `fill` value. A password target or a token-like value needs `"text_env": "VAR"`. |
| `press` | Press a key, for example `"Enter"`. Add `"target"` to focus an element first. |
| `wait_text`, `wait_ms` | Wait for text (default 5000 ms) or for a time. These do not set the verdict. |
| `expect_text` | Wait for text (default 3000 ms) and use it for the verdict. |

A TARGET is a CSS selector, or `{"role": "button", "name": "Save"}`, `{"label": "Email"}`, `{"text": "Delete"}`, `{"placeholder": "Search"}`, or `{"testid": "save"}`. The name is the `aria-label`, the `<label>` text, or the visible text. Keys on any step: `label` (the caption), `anchor: true` (the step that plays slowly and lines up the twin video; default: the last click), and `base` (keys that replace this step on the base side). A failed step stops the change side. A failed base step makes the claim `not_proven`, unless the step has `"base": {"may_fail": true}` (for a new element that base does not have).

## Backend keys

Each block is optional. A missing block skips its capture and its card.

| Block | Keys | Card |
|---|---|---|
| `tests` | `command` (string or list), `copy_from_change`, `timeout` (default 300 s) | `red-green.png` |
| `seed` | `command`, run before each server start | none |
| `server` | `command`, `env`, `ready_path`, `ready_timeout` (default 60 s), `trace_log`, `ignore_trace_paths`, `query_count_header`, `server_ms_header` | needed by `api`, `db_action`, `perf` |
| `api` | `method`, `path`, `body`, `redact_keys`, `keep_headers` | `api-diff.png` |
| `db_action` | `database: "sqlite"`, `request`, `read_sql` (one row) | `db-state.png` |
| `perf` | `method`, `path`, `warmup`, `samples` | `numbers.png` |
| `probe` | `module`, `function`, `inputs` (Python only) | `behavior-table.png` |
| `comment` | `cards`: up to 3 PNG names to show. Other cards go into `<details>`. | none |
| `setup`, `python`, `redact_keys` | See [Real apps](#real-apps). Keys in `redact_keys` are masked in every capture. | none |

Placeholders in commands and env: `{python}`, `{port}`, `{db}`, `{trace}`, `{workdir}`. A trace log gives the Mermaid request flow. The server appends one JSON line per request to `trace_log`, for example `{"method": "GET", "path": "/orders", "handler": "list_orders", "status": 200, "ms": 0.8, "queries": ["SELECT ..."]}`.

## Real apps

The base worktree starts as a clean checkout. It has no `node_modules`, `.venv`, `.env`, or build cache. Use `setup` to prepare it. The worktree cache keeps the result, so a slow install runs one time for each lockfile:

| Key | Meaning |
|---|---|
| `setup.link_from_change` | Paths to symlink from the working tree, for example `.env`, or `node_modules` outside a package workspace. In a workspace the tool refuses a `node_modules` link (it points base at change packages); install with `setup.command`. |
| `setup.copy_from_change` | Paths to copy. Use this when the base must not change the working tree's files. |
| `setup.command`, `setup.keep` | A command that runs in the base worktree before any server or test, for example `pnpm install --frozen-lockfile --offline && pnpm prisma generate`. It runs on each use, after `git clean -ffdx`, which keeps only `node_modules`, `.venv`, `venv`, `.pnpm-store`, `.turbo`, and the dirs in `setup.keep`. |
| `python` | The interpreter for `{python}`. Default: `.venv/bin/python` or `venv/bin/python` in the repo, if it exists. |

Paths must stay inside the repo. The tool never replaces a file that exists in the base worktree. With `init --pin`, the pinned change tree gets the same links, copies, and command. Next.js: `"ui": {"setup": {"link_from_change": ["node_modules", ".env.local"]}, "serve": {"cmd": "pnpm next dev --port {port}", "ready_timeout": 120}}`. FastAPI: `"backend": {"setup": {"link_from_change": [".env"]}, "server": {"command": "{python} -m uvicorn app.main:app --port {port}", "ready_path": "/health"}}`.

Server output goes to `media/backend/logs/` and `media/ui/work/wt/`. A kept base server writes to `~/.cache/prove-it/worktrees/<repo>/<id>.server.log`. When a server does not start, the error shows the last 20 lines of its log.

## Project config merge

The scenario wins. When a key is missing, the tool reads the project config ([configuration.md](configuration.md)):

| Scenario key | Config source |
|---|---|
| `ui.serve` | `app.start` (must contain `{port}`), with the path of `app.ready` as `ready_path` |
| `ui.viewport` | `browser.viewport` |
| `ui.path` | `route` of the first `areas` entry that matches a changed file |
| `backend.tests` | `targeted_test` of that area |

Do not copy config values into the scenario. Add only what is new for this run.

## Output

`media` writes to `$PROOF_DIR/media/ui/` and `$PROOF_DIR/media/backend/`. Each card names both SHAs and the capture file it came from. `media` registers the media as evidence on one claim (`--claim C1`, or a new claim). A second run of the same kind replaces the media of that kind.

`--proves` sets the claim status from the run's own check. The claim needs `claim` text.
- UI: `expect_text` must be on the change page after the flow starts, not on the base page after the flow, and not on the change page before the first step (`"text_may_show_before": true` allows only the last one, when the claim is not that the flow makes the text show). Otherwise the claim is `failed` or `not_proven`.
- Backend: the tests must fail on base and pass on change. Tests that pass on both sides give `not_proven`. The card title shows the real result.

Without a check, read the media and set the status with `status`. `--reuse` registers media that is already in `$PROOF_DIR/media/KIND` without a new capture.

## Limits

- `db_action` reads SQLite only.
- Query counts and handler time come from response headers. The app must send them.
- Steps run in one tab: no drag, hover, upload, or second tab. Use the manual steps in [browser.md](browser.md) for those.
- The red/green card lists test rows for `unittest -v` only. Other runners show their last lines.
- Latency numbers are direction only. Query counts are the claim.
