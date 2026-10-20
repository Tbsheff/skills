# Browser checks

Use `agent-browser` for behavior a reviewer can see. The result must let the reviewer see the changed behavior, not only a test result or a mounted fixture. Do not wait for CI or restart a good recording because the remote PR head changed.

Use the real app route when it exists. A component fixture is a fallback for a component with no reachable route, not a shortcut around app startup, auth, or state setup.

## Base and change media

For a click, a flow of several steps, a layout change, or a new state, capture both sides with one scenario. See [scenario.md](scenario.md). Start with `scripts/media/draft.py`, which reads the diff and proposes the scenario.

```bash
"$PROVE_IT" media --dir "$PROOF_DIR" --scenario "$PROOF_DIR/scenario.json" --kind ui --proves
```

The base side runs from a cached git worktree. The change side runs from the working tree. Both sides run at the same time, in two browser sessions. By default the tool makes only the cards that the comment shows, and the details cards that the scenario asks for. `--all-media` makes all of them. The tool makes:

| File | Where it goes |
|---|---|
| `action.gif` | Visible. The one autoplaying GIF: the flow on the change side with a visible cursor. The anchor step plays at 0.5x speed. |
| `twin.mp4` | Visible. The same flow on base and change, side by side, lined up on the anchor step. |
| `storyboard.png` | In `<details>`. One keyframe for each step. Made for `steps` and for `click.storyboard`. |
| `states.png`, `viewports.png`, `diff-boxes.png` | In `<details>`. Made when the scenario has `states`, `viewports`, or a `followup` ref. |
| `wipe.gif` | In `<details>`. Made only with `--all-media` or `"media": ["wipe.gif"]`. |
| `before.png`, `after.png` | Inputs only. Not in the comment. |

With `--proves`, set `expect_text`. The text must show on the change page after the flow starts, and must be absent on the base page and on the change page before the first step.

Each card is at most 1600px wide and names both SHAs and its capture file. Read every PNG. For a GIF or MP4, extract frames and look at them:

```bash
ffmpeg -i "$PROOF_DIR/media/ui/action.gif" -vf "select='not(mod(n\,8))'" -fps_mode passthrough /tmp/f%02d.png
```

The tool forces `AGENT_BROWSER_ENGINE=chrome`. It finds Chrome from `AGENT_BROWSER_EXECUTABLE_PATH`, then from the usual install path for the platform. Use `steps` for fill, click, select, press, and navigation. Use `auth` for a page behind login. Use the manual steps below only for a flow that `steps` cannot do: drag, hover, upload, or a second tab.

## Login

Never put a user name, password, token, or cookie in a scenario. The tool refuses an `auth` block with such keys. Save a login one time, outside the repo:

```bash
"$PROVE_IT" auth login myapp --url http://localhost:3000/login --until-url /dashboard
```

A person logs in in the browser window. When the URL contains `--until-url` (or the page shows `--until-text`, or you press Enter in a terminal), the tool saves cookies and storage to `~/.config/prove-it/auth/myapp.json` (directory 700, file 600). A scenario uses it with `"auth": {"name": "myapp"}`. Each run loads a private copy into both browsers before the first page and deletes it at the end. Cookies for `localhost` also go to `127.0.0.1`, and local storage goes to the ports of the run. Session storage does not carry over. The manifest and the recording data mask auth-looking values (tokens, cookies, session ids, JWTs, URL passwords), password fields, and `text_env` values. Screenshots show what the page shows, so use a test account and `redact_selectors`.

## Speed

- **Worktree cache.** The base worktree stays in `~/.cache/prove-it/worktrees/<repo>/` with its dependency dirs (`node_modules`, `.venv`, `.pnpm-store`, `.turbo`, `setup.keep`). Each use runs `git clean -ffdx` except those dirs, then `setup` again, so generated code matches the SHA. The key is the lockfiles, schema files (such as `schema.prisma`), and `setup`. The tool keeps 3 worktrees for each repo, removes older ones with `git worktree remove` and `prune`, and locks each one while a run uses it. Your checkout does not change. Off: `"cache": false`, `build.py --no-cache`, or `PROVE_IT_NO_CACHE=1`.
- **Kept servers.** Servers stop at the end of each run. With `"serve": {"keep": true}` or `PROVE_IT_KEEP_SERVERS=1`, a base server stays up and the next run for the same SHA uses it after a health check. Do not keep a server for a flow that writes data. It stops after 30 idle minutes or 4 hours. The tool checks the start time and command of the PID before it stops one. When you kept servers, run `python3 "$SKILL_DIR/scripts/media/shared/wtcache.py" stop` at the end. `list` and `clear` show or remove the cache.
- **Your server.** `"reuse_url": "http://localhost:3000"` uses the dev server that you run for the change side. With `"reuse_check": {"path": "/api/version", "marker": "{short_sha}"}` the tool checks the response for the marker, and starts its own server if it is not there. Without a check, the manifest has a caveat.
- **Fewer cards.** The default is the cards that the comment shows, plus each details card that the scenario asks for. `"media": ["wipe.gif"]` adds cards. `--all-media`, `"all_media": true`, or `PROVE_IT_ALL_MEDIA=1` makes all. The manifest has `media_skipped` and the time of each phase in `timings`.

## One session

```bash
export AGENT_BROWSER_SESSION="$(agent-browser session id --scope worktree --prefix prove-it)"
agent-browser open "http://127.0.0.1:3000/changed-route"
agent-browser set viewport 1440 900
```

Reuse the running app and safe test auth. Do not record login, MFA, installation, server startup, or exploration. To save a login one time, use `"$PROVE_IT" auth login NAME --url URL` (see [Login](#login)), then load it with `agent-browser state load ~/.config/prove-it/auth/NAME.json` on `about:blank` before you open the app.

## Explore, reset, replay

```bash
agent-browser snapshot -i -c
agent-browser find role button click --name "Save"
agent-browser wait --text "Saved"
```

Find stable roles, labels, text, or test IDs. Set up safe test data, complete the flow once, then reset to a known starting state before capture.

## Interaction

```bash
agent-browser console --clear >/dev/null
agent-browser errors --clear >/dev/null
agent-browser record start "$PROOF_DIR/frontend/demo.webm"
agent-browser find role button click --name "Save"
agent-browser wait --text "Saved"
agent-browser screenshot "$PROOF_DIR/frontend/final.png"
agent-browser record stop

"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type video --path "$PROOF_DIR/frontend/demo.webm" \
  --label "Save flow" --role primary \
  --observed "Saving updates the visible state." --proves

"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type screenshot --path "$PROOF_DIR/frontend/final.png" \
  --label "Saved state" --role final
```

`record start` records at 30 fps. agent-browser 0.38.1 accepts `--fps N` (1 to 60) after the path. If your build rejects the flag, leave it out. Do not use a low value such as 12: the motion becomes jumpy. The video can be smaller than the viewport times the device scale (for example 1280x800 for a 1280x800 viewport at 2x), so measure the video size before you crop it.

Keep the recording short. It must show the state before the action, the action itself, and the result. The comment already states what happened, so do not write a second caption that repeats it.

## Static change

Use one final screenshot for a visible result with enough context. Use a before/after pair at the same viewport when the comparison matters:

```bash
"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type screenshot --path /tmp/before.png --label "Before" --role before

"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type screenshot --path /tmp/after.png --label "After" --role after \
  --observed "The action is now visible beside the title." --proves
```

Do not use full-page screenshots unless the claim spans the page. Use `screenshot --annotate` only when one control needs a pointer.

## Optional diagram

A small diagram may follow the real check when it makes a data flow or architecture change easier to understand:

```bash
"$PROVE_IT" add --dir "$PROOF_DIR" --claim C1 \
  --type diagram --path /tmp/flow.svg --label "Request flow" --role detail
```

A diagram cannot use `--proves`.

## Diagnostics and safety

Collect console and page errors once after replay. Keep them under `What I ran`. Do not upload raw HAR files or broad logs. Inspect every frame for credentials, PHI, customer data, and private messages before publishing.
