# Validation

## Contract gate

Run strict validation before rendering:

```bash
agent-artifacts validate contract.json --strict
```

Errors block rendering. Warnings identify content that may still be valid but needs explicit judgment.

## HTML gate

```bash
agent-artifacts check index.html --source contract.json --strict
```

This checks the document floor: self-contained HTML, viewport, answer-first marker, provenance, print rules, verification notice, unresolved placeholders, and optional source coverage.

## Browser gate

For substantive work:

```bash
agent-artifacts review index.html --source contract.json --out-dir review
```

Inspect both images. Confirm:

- no horizontal page overflow;
- title and answer are readable at phone width;
- diagrams and tables remain legible;
- status and severity do not rely on colour alone;
- controls work and have visible focus states;
- useful content remains when JavaScript is disabled;
- print/PDF does not strand headings or create mostly empty pages.

Mechanical checks prove that the artifact attempted the rule, not that the artifact communicates well. Read the rendered page.

`review` fails in three ways: it reports no Chromium, it raises a timeout traceback, or it leaves a `review/` directory missing `mobile.png` or `review.json`. Treat all three as the gate not running. Do not retry, and do not trust a lone `desktop.png` - confirm `review/review.json` exists before you claim the gate passed. `agent-artifacts doctor` reports whether a browser binary was found; it does not prove the browser can render, so a `doctor` line naming Chromium after a timeout still means the gate did not run. Keep the passing `check` result and say plainly in the delivery that the browser gate did not run. An artifact that passed validate, render, and check is deliverable without screenshots.
