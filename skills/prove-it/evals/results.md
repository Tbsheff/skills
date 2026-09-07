# Evaluation results

## 1. `sindresorhus/escape-string-regexp`

Synthetic change: add a helper that escapes a complete JavaScript regex literal, including `/`.

- Diff: one root JavaScript file, +4 lines.
- Classification: `library`, normal risk.
- Recommendation: backend.
- Claims: 1.
- Evidence: one focused Node assertion.
- Browser launched: no.
- Strict validation: passed with no warnings.
- Final wall time: 0.46 seconds.

Reviewer output remained compact: the evidence table names the focused assertion and keeps the long inline Node program truncated in a details block. The exact command and output remain in the local manifest/log.

## 2. `h5bp/html5-boilerplate`

Synthetic change: replace the default page content with a styled reviewer-proof hero.

- Diff: HTML and CSS, +13/−7 lines.
- Classification: `frontend`, normal risk.
- Recommendation: screenshot.
- Claims: 1.
- Evidence: one 1440×900 screenshot, empty console log, empty page-error log.
- Video recorded: no.
- Strict validation: passed with no warnings.
- Final wall time: 1.25 seconds.

This case confirmed the static fast path does not record a video merely because a browser is available.

## 3. `fastapi/fastapi`

Synthetic change: add `/api/status` and an HTML page interaction that fetches and displays the status.

- Diff: one Python file containing backend and embedded frontend changes, +17/−2 lines.
- Classification: `backend` + `frontend`, medium risk.
- Recommendation: mixed.
- Claims: 2.
- Backend evidence: direct local HTTP 200 assertion with `status=ready`.
- Frontend evidence: final-state screenshot, three-second VP9 WebM, empty console log, empty page-error log.
- Strict validation: passed with no warnings.
- Final wall time: 3.78 seconds.

The first classifier pass labeled this backend-only because the UI lived inside a Python string. Added-line content heuristics now recognize server-rendered HTML/JavaScript without reading every source file.

## Artifact integrity

All generated evidence paths remained under the run directory. SHA-256 validation passed. An automated tamper test modified a registered screenshot and correctly caused validation to fail until the original bytes were restored.
