# Changelog

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
