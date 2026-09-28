#!/usr/bin/env python3
"""Render backend proof cards from the JSON files written by capture.py.

Usage:
    python3 render.py --captures DIR/captures --out DIR [--no-shots]

Every value on every card comes from a capture file. This script only filters,
lays out, and colors. Card chrome (title, BASE/CHANGE pills, source + capture-time
footer, SHA stamp) comes from ../shared/house.py; cards are 800px CSS shot at 2x.
Cards are skipped when their capture file is missing, so a scenario can use a subset.
It also writes media-manifest.json, which prove.py reads to register evidence.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
import house  # noqa: E402
from house import esc, pill, side_label  # noqa: E402

TXN = ("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")
WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE")
PLURALS = {"query": "queries", "statement": "statements"}
ARRAY_PREVIEW = 2
FALLBACK_LINES = 12


def plural(n, word):
    return f"{n} {word if n == 1 else PLURALS.get(word, word + 's')}"


def shas(meta):
    change = meta["change"]["short"] + ("+dirty" if meta["change"].get("dirty") else "")
    return meta["base"]["short"], change


def card(meta, title, sub, body, source, extra_css=""):
    base, change = shas(meta)
    return house.card(title, sub, body, base=base, change=change, source=source,
                      captured_at=meta["captured_at"], extra_css=extra_css)


VERBOSE_LINE = re.compile(r"^(?P<indent>\s*)(?P<name>test\w+) \((?P<qual>[\w.]+)\)(?: \((?P<sub>.*?)\))? \.\.\. ?(?P<status>ok|FAIL|ERROR|skipped.*)?$")
FAILURE_HEAD = re.compile(r"^(FAIL|ERROR): (test\w+) \([\w.]+\)(?: \((.*?)\))?$")


def parse_unittest(text):
    lines = text.splitlines()
    rows = [m.groupdict() for m in map(VERBOSE_LINE.match, lines) if m]
    reasons = {}
    for i, line in enumerate(lines):
        m = FAILURE_HEAD.match(line)
        if not m:
            continue
        last_exc = None
        for nxt in lines[i + 1:]:
            if nxt.startswith("======") or nxt.startswith("Ran "):
                break
            if re.match(r"^[A-Za-z_][\w.]*(Error|Exception)\b", nxt):
                last_exc = nxt
        reasons[(m.group(2), m.group(3))] = last_exc
    summary = [l for l in lines if l.startswith("Ran ") or re.match(r"^(OK|FAILED)\b", l)]
    return rows, reasons, summary, len(lines)


TERM_CSS = """
.term { border-radius: 9px; overflow: hidden; border: 1px solid #1e293b; margin-bottom: 12px; background: #0b1220; }
.term-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 12px; background: #111a2e; border-bottom: 1px solid #1e293b; }
.term-head .prompt { font: 11.5px/1.35 var(--mono); color: #cbd5e1; }
.term-head .prompt b { color: #fff; font-weight: 600; }
.term-body { padding: 8px 12px 10px; font: 11.5px/1.6 var(--mono); color: #e2e8f0; }
.ln { white-space: pre; overflow: hidden; text-overflow: ellipsis; }
.ln .st { display: inline-block; width: 48px; font-weight: 700; }
.ln .cls { color: #64748b; }
.st.ok, .ln.ok { color: #4ade80; } .st.bad, .ln.bad { color: #f87171; } .st.dim { color: #64748b; }
.ln.why { color: #fca5a5; padding-left: 48px; }
.ln.sum.dim { color: #94a3b8; margin-top: 6px; }
.term-foot { padding: 5px 12px; font-size: 10.5px; color: #64748b; border-top: 1px solid #1e293b; }
"""


def terminal(side, meta, run):
    rows, reasons, summary, total_lines = parse_unittest(run["stdout"] + run["stderr"])
    out = []
    for r in rows:
        status = r["status"] or ""
        cls = {"ok": "ok", "FAIL": "bad", "ERROR": "bad"}.get(status, "dim")
        label = r["name"] + (f"  [{r['sub']}]" if r["sub"] else "")
        indent = "  " if r["indent"] else ""
        out.append(f'<div class="ln"><span class="st {cls}">{esc(status or "…")}</span>{esc(indent)}'
                   f'<span class="cls">{esc(r["qual"].split(".")[-2])}.</span>{esc(label)}</div>')
        reason = reasons.get((r["name"], r["sub"]))
        if reason:
            out.append(f'<div class="ln why">{esc(indent)}↳ {esc(reason)}</div>')
    if not rows:
        summary = [l for l in (run["stdout"] + run["stderr"]).splitlines() if l.strip()][-FALLBACK_LINES:]
    for line in summary:
        cls = "ok" if line.startswith("OK") else ("bad" if line.startswith("FAILED") else "dim")
        out.append(f'<div class="ln sum {cls}">{esc(line)}</div>')
    copied = run.get("copied_from_change") or []
    extra = f"   # {', '.join(copied)}/ copied from {meta['change']['short']}" if copied else ""
    state = color(run)
    verdict = (pill("add", f"exit {run['exit_code']} · PASS") if state == "green"
               else pill("del", f"exit {run['exit_code']} · FAIL") if state == "red"
               else pill("del", f"exit {run['exit_code']} · DID NOT RUN"))
    return f"""<div class="term">
<div class="term-head"><span class="prompt"><b>{side} {esc(meta[side]['short'])}</b> $ {esc(run['command'])}{esc(extra)}</span>{verdict}</div>
<div class="term-body">{''.join(out)}</div>
<div class="term-foot">{len(out)} of {total_lines} output lines shown: {"status lines, the last exception line per failure, summary" if rows else "the last lines"} · {run['duration_s']:.2f}s</div>
</div>"""


def card_red_green(c):
    meta, tests = c["meta"], c["tests"]
    body = terminal("base", meta, tests["base"]) + terminal("change", meta, tests["change"])
    sub = (f"The change's tests run on the base code, then on the change. "
           f"Base: {esc(meta['base']['subject'])}. Change: {esc(meta['change']['subject'])}.")
    return card(meta, tests_title(tests), sub, body, "captures/tests.json", TERM_CSS)


NOT_RUN_EXITS = {124: "timed out", 126: "command not executable", 127: "command not found"}
PYTEST_NOT_RUN = {2: "interrupted or collection error", 3: "internal error", 4: "usage error", 5: "no tests collected"}


def _num(pattern_, text):
    m = re.search(pattern_, text)
    return int(m.group(1)) if m else None


def test_counts(run):
    """What the runner reported: {"ran", "failed", "errors", "why_not_run"}. None where it did not say.

    Knows unittest, pytest, vitest, and jest summaries. why_not_run is set when the run
    did not execute tests (timeout, missing command, collection or import error, zero tests).
    """
    text = f"{run.get('stdout', '')}\n{run.get('stderr', '')}"
    code = run.get("exit_code")
    out = {"ran": None, "failed": None, "errors": 0, "why_not_run": None}
    if run.get("timed_out") or code in NOT_RUN_EXITS or (isinstance(code, int) and (code >= 128 or code < 0)):
        out["why_not_run"] = NOT_RUN_EXITS.get(code, "timed out" if run.get("timed_out") else f"killed (exit {code})")
        return out
    ran = _num(r"\bRan (\d+) tests? in", text)
    if ran is not None:
        out["ran"] = ran
        out["failed"] = _num(r"FAILED \((?:[^)]*?)failures=(\d+)", text) or 0
        out["errors"] = _num(r"FAILED \((?:[^)]*?)errors=(\d+)", text) or 0
    elif re.search(r"=+ .*\b(passed|failed|error|errors|no tests ran)\b.* in [\d.]+s", text):
        failed = _num(r"(\d+) failed", text) or 0
        passed = _num(r"(\d+) passed", text) or 0
        out.update(ran=failed + passed, failed=failed, errors=_num(r"(\d+) errors?\b", text) or 0)
        if code in PYTEST_NOT_RUN:
            out["why_not_run"] = f"pytest: {PYTEST_NOT_RUN[code]}"
    elif re.search(r"^\s*Tests\s+.*\(\d+\)", text, re.M):
        line = re.search(r"^\s*Tests\s+(.*)$", text, re.M).group(1)
        out.update(ran=_num(r"\((\d+)\)", line), failed=_num(r"(\d+) failed", line) or 0)
    elif re.search(r"^Tests:\s", text, re.M):
        line = re.search(r"^Tests:\s+(.*)$", text, re.M).group(1)
        out.update(ran=_num(r"(\d+) total", line), failed=_num(r"(\d+) failed", line) or 0)
    if out["why_not_run"] is None:
        if out["ran"] == 0 or re.search(r"No test files found|no tests ran|NO TESTS RAN", text, re.I):
            out["why_not_run"] = "no tests ran"
        elif code != 0 and not out["failed"]:
            out["why_not_run"] = ("the runner reported errors, not assertion failures (for example an import error)"
                                  if out["errors"] or out["ran"] is not None or re.search(r"Error|error", text)
                                  else "the runner reported no failed test")
    return out


def color(run):
    if run["exit_code"] == 0:
        return "green"
    return "red" if test_counts(run)["why_not_run"] is None else "did not run"


def tests_title(tests):
    base, change = color(tests["base"]), color(tests["change"])
    if base == change:
        return f"Tests: {base} on both commits"
    return f"Tests: {base} on base, {change} on change"


def tests_verdict(tests):
    """(passed, reason). Proof needs assertion failures on base and a clean pass on change."""
    change, base = tests["change"], tests["base"]
    if change["exit_code"] != 0:
        return False, "The tests fail on the change."
    if test_counts(change)["why_not_run"] == "no tests ran":
        return None, "No tests ran on the change."
    if base["exit_code"] == 0:
        return None, "The tests pass on base too, so they do not isolate this change."
    why = test_counts(base)["why_not_run"]
    if why:
        return None, f"The tests did not run on base ({why}), so the base failure proves nothing about this change."
    return True, ""


def pattern(path):
    return re.sub(r"\[\d+\]", "[]", path)


def flatten(value, path=""):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out.update(flatten(v, f"{path}.{k}" if path else k))
        return out or {path: {}}
    if isinstance(value, list):
        out = {}
        for i, v in enumerate(value):
            out.update(flatten(v, f"{path}[{i}]"))
        return out or {path: []}
    return {path: value}


def type_name(v):
    return {str: "string", int: "int", float: "float", bool: "bool", type(None): "null"}.get(type(v), type(v).__name__)


def diff_bodies(base_body, change_body):
    """Compare key paths with array indices folded, so 40 identical rows count once."""
    fb, fc = flatten(base_body), flatten(change_body)
    pb, pc = {}, {}
    for p, v in fb.items():
        pb.setdefault(pattern(p), v)
    for p, v in fc.items():
        pc.setdefault(pattern(p), v)
    removed = [p for p in pb if p not in pc]
    added = [p for p in pc if p not in pb]
    renamed = []
    for r in list(removed):
        parent, key = r.rsplit(".", 1) if "." in r else ("", r)
        for a in list(added):
            aparent, akey = a.rsplit(".", 1) if "." in a else ("", a)
            if parent == aparent and (akey.startswith(key + "_") or key.startswith(akey + "_")):
                renamed.append((r, a, type_name(pb[r]), type_name(pc[a])))
                removed.remove(r)
                added.remove(a)
                break
    changed_types = [p for p in pb if p in pc and type_name(pb[p]) != type_name(pc[p])]
    changed_values = {p for p in fb if p in fc and fb[p] != fc[p]}
    return {"removed": removed, "added": added, "renamed": renamed, "retyped": changed_types, "changed_paths": changed_values}


def json_lines(value, marks, path="", indent=0, key=None, trailing="", preview=ARRAY_PREVIEW):
    pad = "  " * indent
    prefix = f'<span class="k">"{esc(key)}"</span>: ' if key is not None else ""
    lines = []
    if isinstance(value, dict):
        lines.append(("", f"{pad}{prefix}{{"))
        items = list(value.items())
        for n, (k, v) in enumerate(items):
            lines += json_lines(v, marks, f"{path}.{k}" if path else k, indent + 1, k, "," if n < len(items) - 1 else "", preview)
        lines.append(("", f"{pad}}}{trailing}"))
    elif isinstance(value, list):
        lines.append(("", f"{pad}{prefix}["))
        same_shape = all(isinstance(v, dict) and v.keys() == value[0].keys() for v in value) if value else False
        shown = value[:preview] if same_shape and len(value) > preview + 1 else value
        for n, v in enumerate(shown):
            last = n == len(shown) - 1 and len(shown) == len(value)
            lines += json_lines(v, marks, f"{path}[{n}]", indent + 1, None, "" if last else ",", preview)
        if len(shown) < len(value):
            lines.append(("more", f'{pad}  <span class="more">… {len(value) - len(shown)} more items, same keys</span>'))
        lines.append(("", f"{pad}]{trailing}"))
    else:
        lit = json.dumps(value)
        cls = "s" if isinstance(value, str) else ("n" if isinstance(value, (int, float)) and not isinstance(value, bool) else "l")
        lines.append((marks(path), f'{pad}{prefix}<span class="{cls}">{esc(lit)}</span>{trailing}'))
    return lines


JSON_CSS = """
.code { font: 11px/1.55 var(--mono); padding: 6px 0; }
.code .row { display: flex; white-space: pre; padding-right: 10px; }
.code .gut { width: 20px; flex: none; text-align: center; color: var(--faint); }
.code .row.add { background: var(--add-bg); } .code .row.add .gut { color: var(--add-ink); font-weight: 700; }
.code .row.del { background: var(--del-bg); } .code .row.del .gut { color: var(--del-ink); font-weight: 700; }
.code .row.chg { background: var(--chg-bg); } .code .row.chg .gut { color: var(--chg-ink); font-weight: 700; }
.code .k { color: #334155; } .code .s { color: #0f766e; } .code .n { color: #1d4ed8; } .code .l { color: #7c3aed; }
.code .more { color: var(--muted); font-style: italic; }
.hdrs { font: 11px/1.55 var(--mono); color: var(--muted); padding: 6px 12px; border-bottom: 1px dashed var(--line); }
.hdrs .row { white-space: pre; } .hdrs .row.chg { background: var(--chg-bg); color: var(--chg-ink); margin: 0 -12px; padding: 0 12px; }
.legend { display: flex; gap: 6px; flex-wrap: wrap; margin: -4px 0 12px; }
.grid2 { align-items: start; }
"""


def code_block(lines):
    gut = {"add": "+", "del": "−", "chg": "~", "": "", "more": ""}
    return '<div class="code">' + "".join(
        f'<div class="row {m if m != "more" else ""}"><span class="gut">{gut[m]}</span><span>{text}</span></div>' for m, text in lines
    ) + "</div>"


def card_api_diff(c):
    meta, api = c["meta"], c["api"]
    d = diff_bodies(api["base"]["body"], api["change"]["body"])
    base_marks = {p: "del" for p in d["removed"]} | {r[0]: "chg" for r in d["renamed"]} | {p: "chg" for p in d["retyped"]}
    change_marks = {p: "add" for p in d["added"]} | {r[1]: "chg" for r in d["renamed"]} | {p: "chg" for p in d["retyped"]}
    panels = []
    for side, marks in (("base", base_marks), ("change", change_marks)):
        rec, other = api[side], api["change" if side == "base" else "base"]
        hdr_rows = [f'<div class="row">HTTP {rec["status"]}</div>'] + [
            f'<div class="row{" chg" if other["headers"].get(k) != v else ""}">{esc(k)}: {esc(v)}</div>'
            for k, v in rec["headers"].items()]
        lines = json_lines(rec["body"], lambda p, m=marks: m.get(pattern(p)) or ("chg" if p in d["changed_paths"] else ""))
        panels.append(f'<div class="panel"><div class="panel-head">{side_label(side, meta[side]["short"])}'
                      f'<span>{esc(rec["request"]["method"])} {esc(rec["request"]["path"])}</span></div>'
                      f'<div class="hdrs">{"".join(hdr_rows)}</div>{code_block(lines)}</div>')
    short = lambda p: p.split(".")[-1]
    legend = [pill("chg", f"~ {short(r)} → {short(a)} ({tb} → {tc})") for r, a, tb, tc in d["renamed"]]
    legend += [pill("chg", f"~ {short(p)} type changed") for p in d["retyped"]]
    if d["changed_paths"]:
        legend.append(pill("chg", f"~ {plural(len(d['changed_paths']), 'value')} changed"))
    legend += [pill("add", f"+ {short(p)}") for p in d["added"]]
    legend += [pill("del", f"− {short(p)}") for p in d["removed"]]
    if api["base"]["redacted_keys"]:
        legend.append(pill("neutral", "redacted: " + ", ".join(api["base"]["redacted_keys"])))
    body = f"<div class='legend'>{''.join(legend)}</div><div class='grid2'>{''.join(panels)}</div>"
    req = api["base"]["request"]
    sub = (f"<code>{esc(req['method'])} {esc(req['path'])}</code> sent once to a fresh server on each commit. "
           f"Marks come from a key-path diff of the raw bodies; list items with the same keys are shown twice, then counted.")
    return card(meta, "API response: base vs change", sub, body, "captures/api.json", JSON_CSS)


DB_CSS = """
.dbside { margin-bottom: 12px; }
.dbside .panel-head { flex-wrap: wrap; }
.resp { font: 11px/1.4 var(--mono); color: var(--muted); }
table.rows { width: 100%; border-collapse: collapse; table-layout: fixed; font: 11.5px/1.35 var(--mono); }
table.rows th { text-align: left; font: 600 10px/1 var(--sans); letter-spacing: 0.04em; color: var(--muted); padding: 8px 8px; border-bottom: 1px solid var(--line); }
table.rows td { padding: 8px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
table.rows tr:last-child td { border-bottom: 0; }
table.rows td.when { font: 600 10px/1 var(--sans); color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
table.rows td.hit { background: var(--chg-bg); color: var(--chg-ink); font-weight: 600; }
table.rows .null { color: var(--faint); font-style: italic; }
"""


def cell(v):
    return '<span class="null">NULL</span>' if v is None else esc(v)


WHEN_COL = "\0when"


def column_widths(records):
    cols = list(records[0]["before"].keys())
    longest = {k: max(4, len(k), *(len(str(r[w].get(k))) for r in records for w in ("before", "after"))) + 2 for k in cols}
    longest[WHEN_COL] = 8
    total = sum(longest.values())
    return cols, {k: v / total * 100 for k, v in longest.items()}


def card_db_state(c):
    meta, db = c["meta"], c["db"]
    cols, widths = column_widths([db["base"], db["change"]])
    colgroup = f'<colgroup><col style="width:{widths[WHEN_COL]:.1f}%">' + "".join(f'<col style="width:{widths[k]:.1f}%">' for k in cols) + "</colgroup>"
    blocks = []
    for side in ("base", "change"):
        rec = db[side]
        diff_cols = [k for k in cols if rec["before"][k] != rec["after"].get(k)]
        verdict = pill("chg", f"{plural(len(diff_cols), 'cell')} changed: {', '.join(diff_cols)}") if diff_cols else pill("del", "0 cells changed · no write")
        head = "".join(f"<th>{esc(k)}</th>" for k in cols)
        before = "".join(f'<td>{cell(rec["before"][k])}</td>' for k in cols)
        after = "".join(f'<td class="{"hit" if k in diff_cols else ""}">{cell(rec["after"].get(k))}</td>' for k in cols)
        resp = json.dumps(rec["response"]["body"], separators=(", ", ": "))
        blocks.append(f"""<div class="panel dbside"><div class="panel-head">{side_label(side, meta[side]['short'])}{verdict}</div>
<div class="panel-head"><span class="resp">{esc(rec['action']['method'])} {esc(rec['action']['path'])} → {rec['response']['status']} {esc(resp)}</span></div>
<table class="rows">{colgroup}<tr><th></th>{head}</tr><tr><td class="when">before</td>{before}</tr><tr><td class="when">after</td>{after}</tr></table></div>""")
    sub = (f"Row read from SQLite with <code>{esc(db['base']['read_with'])}</code> before and after the call, "
           f"on a freshly seeded database per commit. Highlighted cells changed.")
    return card(meta, "Database row: before vs after the call", sub, "".join(blocks), "captures/db.json", DB_CSS)


BEH_CSS = """
table.beh { width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed; font: 12px/1.4 var(--mono); border: 1px solid var(--line); border-radius: 9px; overflow: hidden; }
table.beh th.side { color: var(--muted); }
table.beh th { text-align: left; padding: 9px 12px; background: var(--panel); border-bottom: 1px solid var(--line); }
table.beh td { padding: 7px 12px; border-bottom: 1px solid var(--line); }
table.beh tr:last-child td { border-bottom: 0; }
table.beh tr.diff td { background: #fffbeb; }
table.beh tr.diff td.mark { color: var(--chg-ink); font-weight: 700; }
table.beh td.mark { text-align: center; color: var(--faint); font-family: var(--sans); }
table.beh .err { color: var(--del-ink); }
table.beh .none { color: var(--faint); }
table.beh .ws { background: #e0e7ff; border-radius: 2px; }
.legend { display: flex; gap: 6px; margin: -4px 0 12px; }
"""


def show_input(value):
    lit = esc(json.dumps(value))
    return re.sub(r"(?<=&quot;)( +)|( +)(?=&quot;)", lambda m: f'<span class="ws">{"·" * len(m.group(0))}</span>', lit)


def show_result(r):
    if not r["ok"]:
        return f'<span class="err">raises {esc(r["error"])}</span>'
    if r["value"] is None:
        return '<span class="none">None</span>'
    return esc(json.dumps(r["value"]))


def card_behavior(c):
    meta, beh = c["meta"], c["behavior"]
    rows, diffs = [], 0
    for b, ch in zip(beh["base"]["results"], beh["change"]["results"]):
        differs = (b["ok"], b.get("value"), b.get("error")) != (ch["ok"], ch.get("value"), ch.get("error"))
        diffs += differs
        rows.append(f'<tr class="{"diff" if differs else ""}"><td class="mark">{"≠" if differs else "="}</td>'
                    f'<td>{show_input(b["input"])}</td><td>{show_result(b)}</td><td>{show_result(ch)}</td></tr>')
    head = ('<colgroup><col style="width:36px"><col style="width:130px"><col><col style="width:200px"></colgroup>'
            f'<tr><th></th><th class="side">input</th><th>{side_label("base", meta["base"]["short"])}</th>'
            f'<th>{side_label("change", meta["change"]["short"])}</th></tr>')
    legend = f'<div class="legend">{pill("chg", f"{diffs} of {len(rows)} inputs changed")}{pill("neutral", f"{len(rows) - diffs} unchanged")}</div>'
    fn = f"{beh['base']['module']}.{beh['base']['function']}"
    sub = (f"Each input passed to <code>{esc(fn)}</code> in a separate Python process per commit. "
           f"Cells show the return value or the exception raised. <span class='ws'>·</span> marks a space.")
    return card(meta, f"{beh['base']['function']}: base vs change", sub,
                f"{legend}<table class='beh'>{head}{''.join(rows)}</table>", "captures/behavior.json", BEH_CSS)


NUM_CSS = """
.metric { display: grid; grid-template-columns: 150px 1fr; gap: 6px 14px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--line); }
.metric .name { font-size: 13px; font-weight: 600; grid-row: span 2; }
.metric .name small { display: block; font-weight: 400; color: var(--muted); font-size: 11px; margin-top: 2px; }
.bar { display: flex; align-items: center; gap: 8px; }
.bar .tag { width: 52px; font: 600 10px/1 var(--sans); letter-spacing: 0.03em; text-transform: uppercase; }
.bar .tag.base { color: var(--base); } .bar .tag.change { color: var(--change); }
.bar .track { flex: 1; height: 18px; }
.bar .fill { height: 100%; border-radius: 3px; min-width: 3px; }
.bar .fill.base { background: var(--base-fill); } .bar .fill.change { background: var(--change-fill); }
.bar .val { width: 70px; font: 600 12px/1 var(--mono); text-align: right; }
.bar .dcol { width: 46px; text-align: right; font: 600 12px/1 var(--mono); }
.good { color: var(--add-ink); } .bad { color: var(--del-ink); }
table.more { width: 100%; border-collapse: collapse; font: 11px/1.4 var(--mono); color: var(--muted); margin-top: 10px; }
table.more th { text-align: left; font: 600 10px/1 var(--sans); letter-spacing: 0.04em; text-transform: uppercase; padding: 6px 8px; border-bottom: 1px solid var(--line); }
table.more td { padding: 5px 8px; }
"""


def metric_block(name, hint, b, ch, fmt):
    top = max(b, ch) or 1
    delta = (ch - b) / b * 100 if b else 0
    bars = "".join(
        f'<div class="bar"><span class="tag {side}">{side}</span><div class="track"><div class="fill {side}" style="width:{v / top * 100:.1f}%"></div></div>'
        f'<span class="val">{fmt.format(v)}</span><span class="dcol {"good" if delta <= 0 else "bad"}">{f"{delta:+.0f}%" if side == "change" else ""}</span></div>'
        for side, v in (("base", b), ("change", ch)))
    return f'<div class="metric"><div class="name">{esc(name)}<small>{esc(hint)}</small></div>{bars}</div>'


def card_numbers(c):
    meta, perf = c["meta"], c["perf"]
    s, req = perf["summary"], perf["request"]
    blocks = []
    if "query_count" in s["base"]:
        blocks.append(metric_block("Queries per request", f"{perf['headers']['query_count']} header", s["base"]["query_count"], s["change"]["query_count"], "{:.0f}"))
    blocks.append(metric_block("Latency p50", "client round trip, loopback", s["base"]["client_ms"]["p50"], s["change"]["client_ms"]["p50"], "{:.2f} ms"))
    extra_rows = [("client p95", s["base"]["client_ms"]["p95"], s["change"]["client_ms"]["p95"])]
    if "server_ms" in s["base"]:
        extra_rows += [("handler p50", s["base"]["server_ms"]["p50"], s["change"]["server_ms"]["p50"]),
                       ("handler p95", s["base"]["server_ms"]["p95"], s["change"]["server_ms"]["p95"])]
    more = ("<table class='more'><tr><th>secondary</th><th>base</th><th>change</th></tr>" +
            "".join(f"<tr><td>{esc(n)}</td><td>{b:.2f} ms</td><td>{ch:.2f} ms</td></tr>" for n, b, ch in extra_rows) + "</table>")
    note = ('<div class="house-note">One laptop, loopback HTTP, SQLite. The query count is exact. '
            'Milliseconds are small and move between runs, so read latency as direction only.</div>')
    sub = (f"<code>{esc(req['method'])} {esc(req['path'])}</code>: {s['base']['n']} measured requests per commit after "
           f"{perf['warmup']} warmup, sent alternately to base and change.")
    return card(meta, "Numbers: query count and latency", sub, "".join(blocks) + more + note, "captures/perf.json", NUM_CSS)


def verb(sql):
    return sql.split()[0].upper()


def query_shape(sql):
    return re.sub(r"'[^']*'|\b\d+\b", "?", sql)


def mermaid_text(text, limit=70):
    text = re.sub(r"^SELECT (?!\*).*? FROM ", "SELECT … FROM ", text).replace(";", ",").replace("#", "")
    if len(text) <= limit:
        return text
    head = text[: limit * 3 // 5].rsplit(" ", 1)[0]
    tail = text[-(limit - len(head) - 3):]
    return f"{head} … {tail.split(' ', 1)[1] if ' ' in tail else tail}"


def call_facts(call):
    data_q = [q for q in call["queries"] if verb(q) not in TXN]
    return {"queries": len(data_q), "txn": len(call["queries"]) - len(data_q),
            "writes": sum(verb(q) in WRITES for q in data_q)}


def runs(queries):
    """Group consecutive statements with the same shape: [(shape_example, count)]."""
    out = []
    for q in queries:
        if out and query_shape(out[-1][0]) == query_shape(q):
            out[-1][1] += 1
        else:
            out.append([q, 1])
    return out


def call_summary(call):
    f = call_facts(call)
    txn = f" + {f['txn']} transaction control" if f["txn"] else ""
    return f"{plural(f['queries'], 'query')}{txn}, {call['ms']:.2f} ms"


def build_mermaid(c):
    meta, flow = c["meta"], c["flow"]
    lines = ["sequenceDiagram", "    participant C as Client", "    participant H as Handler", "    participant DB as Database"]
    colors = {"base": "rgb(241, 245, 249)", "change": "rgb(238, 242, 255)"}
    for side in ("base", "change"):
        lines += [f"    rect {colors[side]}", f"    Note over C,DB: {side} {meta[side]['short']}"]
        for call in flow[side]:
            lines += [f"    C->>H: {call['method']} {mermaid_text(call['path'])}", f"    Note right of H: {call['handler']}"]
            for q, n in runs(call["queries"]):
                if verb(q) in TXN:
                    lines.append(f"    H-->>DB: {verb(q)} (transaction control, not counted)")
                elif n > 1:
                    lines += [f"    loop {n} times, one per row", f"    H->>DB: {mermaid_text(query_shape(q))}", "    end"]
                else:
                    lines.append(f"    H->>DB: {mermaid_text(q)}")
            if call["method"] != "GET" and not call_facts(call)["writes"]:
                lines.append("    Note over H,DB: no INSERT, UPDATE or DELETE ran")
            lines.append(f"    H-->>C: {call['status']} ({call_summary(call)})")
        lines.append("    end")
    return "\n".join(lines) + "\n"


def build_flow_note(c):
    meta, flow = c["meta"], c["flow"]
    out = [f"# Flow note: {meta['base']['short']} → {meta['change']['short']}", "",
           "Generated from the trace log the server wrote during `capture.py` (one line per request, one entry per SQL "
           "statement). Consecutive statements with the same shape are drawn once inside a `loop`. BEGIN/COMMIT are drawn "
           "as dashed arrows and are not counted as queries, which matches the query-count header.", ""]
    for side in ("base", "change"):
        for call in flow[side]:
            f = call_facts(call)
            loops = [f"{n}x `{mermaid_text(query_shape(q))}`" for q, n in runs(call["queries"]) if n > 1]
            out.append(f"- **{side} {meta[side]['short']}** `{call['method']} {call['path']}` → {call['status']}: "
                       f"{call_summary(call)}, {plural(f['writes'], 'write')}" + (f"; repeated: {', '.join(loops)}" if loops else ""))
    return "\n".join(out) + "\n"


CARDS = [
    ("red-green", "tests", card_red_green),
    ("api-diff", "api", card_api_diff),
    ("db-state", "db", card_db_state),
    ("behavior-table", "behavior", card_behavior),
    ("numbers", "perf", card_numbers),
]


CARD_ALT = {
    "red-green.png": ("tests", "The change's tests, run on base and on change."),
    "api-diff.png": ("api", "One redacted API response from each commit, fields marked added, removed, renamed or changed."),
    "db-state.png": ("db", "One database row before and after the scenario action, on both commits."),
    "behavior-table.png": ("behavior", "Probe function output for each scenario input on both commits."),
    "numbers.png": ("perf", "Query count and latency for the scenario perf request."),
}


def test_summary(run):
    lines = (run["stdout"] + run["stderr"]).splitlines()
    return next((l for l in reversed(lines) if re.match(r"^(OK|FAILED)\b", l)), f"exit {run['exit_code']}")


def and_join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def fact_clauses(c):
    clauses = []
    if "perf" in c and "query_count" in c["perf"]["summary"]["base"]:
        s, req = c["perf"]["summary"], c["perf"]["request"]
        clauses.append(f"`{req['method']} {req['path']}` runs {s['change']['query_count']} queries instead of {s['base']['query_count']}")
    if "api" in c:
        d = diff_bodies(c["api"]["base"]["body"], c["api"]["change"]["body"])
        short = lambda p: p.split(".")[-1]
        parts = [f"renames `{short(r)}` ({tb}) to `{short(a)}` ({tc})" for r, a, tb, tc in d["renamed"]]
        parts += [f"adds `{short(p)}`" for p in d["added"]]
        parts += [f"drops `{short(p)}`" for p in d["removed"]]
        if parts:
            clauses.append("the response " + and_join(parts))
    if "db" in c:
        act = c["db"]["change"]["action"]
        changed = {side: [k for k, v in (c["db"][side]["before"] or {}).items() if v != (c["db"][side]["after"] or {}).get(k)]
                   for side in ("base", "change")}
        base_part = "writes nothing" if not changed["base"] else f"changes {', '.join(changed['base'])}"
        clauses.append(f"`{act['method']} {act['path']}` now writes {and_join([f'`{k}`' for k in changed['change']]) or 'nothing'} "
                       f"(base returned {c['db']['base']['response']['status']} but {base_part})")
    if "behavior" in c:
        b, ch = c["behavior"]["base"], c["behavior"]["change"]
        n = sum((x["ok"], x.get("value"), x.get("error")) != (y["ok"], y.get("value"), y.get("error")) for x, y in zip(b["results"], ch["results"]))
        clauses.append(f"`{b['function']}` gives a different result for {n} of {len(b['results'])} inputs")
    if "tests" in c and not clauses:
        t = c["tests"]
        clauses.append(f"the tests give {test_summary(t['base'])} on base and {test_summary(t['change'])} on change")
    return clauses


def caveat(c):
    if "perf" in c:
        s = c["perf"]["summary"]
        exact = " The query count is exact." if "query_count" in s["base"] else ""
        return (f"Latency comes from {s['base']['n']} loopback requests per commit on one machine "
                f"(p50 {s['base']['client_ms']['p50']:.2f} → {s['change']['client_ms']['p50']:.2f} ms), so treat it as direction only.{exact}")
    if "tests" in c and c["tests"]["base"].get("copied_from_change"):
        return "Base ran with the change's test files copied in, so base failures show the new expectations, not old coverage."
    return "All runs used seeded local data, not production data."


def media_manifest(c, out, rendered):
    meta = c["meta"]
    scenario = meta.get("scenario", {})
    visible = [f for f in scenario.get("comment", {}).get("cards", list(CARD_ALT)) if f in rendered][:3]
    artifacts = []
    for name, (source, alt) in CARD_ALT.items():
        if name in rendered:
            artifacts.append({"file": name, "title": alt, "what": alt, "type": "screenshot",
                              "placement": "inline" if name in visible else "details",
                              "source": f"captures/{source}.json"})
    if os.path.exists(os.path.join(out, "flow.mmd")):
        artifacts.append({"file": "flow.mmd", "title": "Request flow (from the server trace log)",
                          "what": "Mermaid sequence diagram built from the server trace log.", "type": "mermaid",
                          "placement": "details", "source": "captures/flow.json"})
    tests = c.get("tests")
    verdict = tests_verdict(tests) if tests else (None, "")
    change = meta["change"]
    result = {
        "kind": "backend",
        "scenario": meta.get("scenario_path", ""),
        "name": scenario.get("name", ""),
        "base": {"sha": meta["base"]["short"], "ref": meta["base"]["ref"], "subject": meta["base"]["subject"]},
        "change": {"sha": change["short"] + ("+dirty" if change.get("dirty") else ""), "ref": change["ref"],
                   "subject": change["subject"]},
        "captured_at": meta["captured_at"],
        "claim": scenario.get("claim") or scenario.get("description") or "",
        "observations": fact_clauses(c),
        "passed": verdict[0],
        "not_proven_reason": verdict[1],
        "caveat": " ".join(part for part in (verdict[1] if verdict[0] is None else "", caveat(c)) if part),
        "notes": [],
        "tests": {side: {"command": tests[side]["command"], "exit_code": tests[side]["exit_code"],
                         "summary": test_summary(tests[side]), "copied_from_change": tests[side]["copied_from_change"]}
                  for side in ("base", "change")} if tests else None,
        "artifacts": artifacts,
    }
    with open(os.path.join(out, "media-manifest.json"), "w") as f:
        json.dump(result, f, indent=2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-shots", action="store_true")
    args = ap.parse_args()
    captures = {}
    for name in os.listdir(args.captures):
        if name.endswith(".json"):
            with open(os.path.join(args.captures, name)) as f:
                captures[name[:-5]] = json.load(f)
    items = []
    for name, needs, fn in CARDS:
        if needs in captures:
            items.append((fn(captures), os.path.join(args.out, "html", f"{name}.html"), os.path.join(args.out, f"{name}.png")))
    if "flow" in captures:
        with open(os.path.join(args.out, "flow.mmd"), "w") as f:
            f.write(build_mermaid(captures))
        with open(os.path.join(args.out, "flow-note.md"), "w") as f:
            f.write(build_flow_note(captures))
    if args.no_shots:
        for html_string, html_path, _ in items:
            os.makedirs(os.path.dirname(html_path), exist_ok=True)
            with open(html_path, "w") as f:
                f.write(html_string)
    else:
        for png in house.write_and_shoot(items, session=f"backend-cards-{os.getpid()}"):
            print(f"  shot {os.path.relpath(png, args.out)}")
    media_manifest(captures, args.out, {os.path.basename(p) for _, _, p in items})
    print(f"rendered {len(items)} cards" + (", flow.mmd, flow-note.md" if "flow" in captures else ""))


if __name__ == "__main__":
    main()
