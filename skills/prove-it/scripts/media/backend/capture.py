#!/usr/bin/env python3
"""Run a backend scenario against a base commit and a change commit and save raw captures.

Usage:
    python3 capture.py --scenario SCENARIO.json --repo REPO --base REF --out DIR/captures

The change side is the working checkout of --repo (HEAD plus any uncommitted edits).
The base side is a temporary `git worktree` at --base. Everything app-specific
(test command, seed, server command, requests, DB read, probe function and inputs)
comes from the scenario file; see references/scenario.md. Renderers only read the
JSON written here.
"""
import argparse
import json
import os
import platform
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
import procs
import redact as scrubber
import wtcache

DEFAULT_TEST_TIMEOUT_S = 300
DEFAULT_PROBE_TIMEOUT_S = 60
PYTHON = sys.executable

PROBE = r"""
import importlib, json, sys
spec = json.loads(sys.argv[1])
fn = getattr(importlib.import_module(spec["module"]), spec["function"])
out = []
for value in spec["inputs"]:
    try:
        out.append({"input": value, "ok": True, "value": fn(value)})
    except Exception as exc:
        out.append({"input": value, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
print(json.dumps(out))
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()


def commit_info(repo, ref):
    sha = git(repo, "rev-parse", ref)
    return {"ref": ref, "sha": sha, "short": sha[:7], "subject": git(repo, "log", "-1", "--format=%s", sha)}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fill(value, slots):
    if isinstance(value, list):
        return [fill(v, slots) for v in value]
    for k, v in slots.items():
        value = value.replace("{" + k + "}", str(v))
    return value


def child_env(extra=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.update(extra or {})
    return env


class Server:
    def __init__(self, tree, spec, slots, log_path):
        self.port = free_port()
        slots = dict(slots, port=self.port)
        env = {k: fill(v, slots) for k, v in spec.get("env", {}).items() if slots.get("trace") or "{trace}" not in v}
        self.log_path = log_path
        self.proc = procs.start(fill(spec["command"], slots), tree, child_env(env), log_path)
        self.base_url = f"http://127.0.0.1:{self.port}"
        try:
            procs.wait_url(self.base_url + spec.get("ready_path", "/"), self.proc, log_path,
                           spec.get("ready_timeout", procs.DEFAULT_READY_TIMEOUT_S))
        except BaseException:
            self.stop()
            raise

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req = urllib.request.Request(self.base_url + path, method=method, data=data, headers=headers)
        start = time.perf_counter()
        try:
            resp = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as err:
            resp = err
        raw = resp.read()
        client_ms = (time.perf_counter() - start) * 1000
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw.decode(errors="replace")
        return {"status": resp.status, "headers": dict(resp.headers.items()), "body": parsed, "client_ms": client_ms}

    def stop(self):
        procs.stop(self.proc)


def redact(value, keys, seen):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in keys:
                out[k] = "<redacted>"
                seen.add(k)
            else:
                out[k] = redact(v, keys, seen)
        return out
    if isinstance(value, list):
        return [redact(v, keys, seen) for v in value]
    return value


def read_sqlite(db_path, sql):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(sql).fetchone()
    conn.close()
    return dict(row) if row else None


def seed(tree, scenario, slots):
    if "seed" in scenario:
        spec = scenario["seed"]
        proc = subprocess.run(fill(spec["command"], slots), cwd=tree, capture_output=True, text=True, env=child_env(),
                              timeout=spec.get("timeout", DEFAULT_PROBE_TIMEOUT_S))
        if proc.returncode:
            raise RuntimeError(f"seed failed in {tree} ({proc.returncode}):\n{(proc.stdout + proc.stderr)[-2000:]}")


def capture_tests(tree, spec, slots, copy_from=None):
    copied = []
    if copy_from:
        for rel in spec.get("copy_from_change", []):
            src, dst = os.path.join(copy_from, rel), os.path.join(tree, rel)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy(src, dst)
            copied.append(rel)
    cmd = fill(spec["command"], slots)
    timeout = spec.get("timeout", DEFAULT_TEST_TIMEOUT_S)
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=tree, capture_output=True, text=True, env=child_env(), timeout=timeout)
        code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except (FileNotFoundError, PermissionError) as exc:
        code, stdout, stderr = 127 if isinstance(exc, FileNotFoundError) else 126, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        code = 124
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = f"timed out after {timeout}s"
    shown = " ".join("python3" if c == PYTHON else c for c in cmd)
    return {"command": shown, "exit_code": code, "duration_s": round(time.perf_counter() - start, 3),
            "stdout": stdout, "stderr": stderr, "copied_from_change": copied, "timed_out": code == 124}


def capture_probe(tree, spec):
    proc = subprocess.run([PYTHON, "-c", PROBE, json.dumps(spec)], cwd=tree, capture_output=True, text=True,
                          env=child_env(), timeout=spec.get("timeout", DEFAULT_PROBE_TIMEOUT_S))
    if proc.returncode:
        raise RuntimeError(f"probe failed in {tree} ({proc.returncode}):\n{proc.stderr[-2000:]}")
    return {"module": spec["module"], "function": spec["function"], "results": json.loads(proc.stdout)}


def capture_http_and_db(tree, scenario, workdir, log_path):
    slots = {"python": PYTHON, "workdir": workdir, "db": os.path.join(workdir, "db.sqlite"),
             "trace": os.path.join(workdir, "trace.jsonl")}
    seed(tree, scenario, slots)
    server_spec = scenario["server"]
    server = Server(tree, server_spec, slots, log_path)
    api_rec = db_rec = None
    try:
        if "api" in scenario:
            a = scenario["api"]
            seen = set()
            r = server.request(a["method"], a["path"], a.get("body"))
            api_rec = {"request": {"method": a["method"], "path": a["path"]}, "status": r["status"],
                       "headers": {k: r["headers"].get(k) for k in a.get("keep_headers", [])},
                       "body": redact(r["body"], set(a.get("redact_keys", [])), seen), "redacted_keys": sorted(seen)}
        if "db_action" in scenario:
            d = scenario["db_action"]
            before = read_sqlite(slots["db"], d["read_sql"])
            req = d["request"]
            r = server.request(req["method"], req["path"], req.get("body"))
            after = read_sqlite(slots["db"], d["read_sql"])
            db_rec = {"action": {"method": req["method"], "path": req["path"]},
                      "response": {"status": r["status"], "body": r["body"]},
                      "read_with": d["read_sql"], "before": before, "after": after}
    finally:
        server.stop()
    flow = []
    trace_path = fill(server_spec.get("trace_log", ""), slots)
    if trace_path and os.path.exists(trace_path):
        ignore = set(server_spec.get("ignore_trace_paths", []))
        with open(trace_path) as f:
            flow = [t for t in map(json.loads, filter(str.strip, f)) if t["path"].split("?")[0] not in ignore]
    return api_rec, db_rec, flow


def percentile(values, pct):
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def stats(values):
    return {"p50": percentile(values, 50), "p95": percentile(values, 95), "mean": statistics.mean(values)}


def capture_perf(trees, scenario, workdir, log_dir):
    p, server_spec = scenario["perf"], scenario["server"]
    qc_h, ms_h = server_spec.get("query_count_header"), server_spec.get("server_ms_header")
    servers = {}
    try:
        for side, tree in trees.items():
            slots = {"python": PYTHON, "workdir": workdir, "db": os.path.join(workdir, f"perf-{side}.sqlite"), "trace": ""}
            seed(tree, scenario, slots)
            servers[side] = Server(tree, server_spec, slots, os.path.join(log_dir, f"server-perf-{side}.log"))
        samples = {side: [] for side in trees}
        for i in range(p["warmup"] + p["samples"]):
            for side, server in servers.items():
                r = server.request(p["method"], p["path"], p.get("body"))
                if i >= p["warmup"]:
                    s = {"client_ms": r["client_ms"]}
                    if qc_h and qc_h in r["headers"]:
                        s["query_count"] = int(r["headers"][qc_h])
                    if ms_h and ms_h in r["headers"]:
                        s["server_ms"] = float(r["headers"][ms_h])
                    samples[side].append(s)
    finally:
        for server in servers.values():
            server.stop()
    summary = {}
    for side, ss in samples.items():
        summary[side] = {"n": len(ss), "client_ms": stats([s["client_ms"] for s in ss])}
        if all("query_count" in s for s in ss):
            counts = sorted({s["query_count"] for s in ss})
            summary[side]["query_count"] = counts[0] if len(counts) == 1 else counts
        if all("server_ms" in s for s in ss):
            summary[side]["server_ms"] = stats([s["server_ms"] for s in ss])
    return {"request": {"method": p["method"], "path": p["path"]}, "warmup": p["warmup"], "interleaved": True,
            "headers": {"query_count": qc_h, "server_ms": ms_h}, "summary": summary, "samples": samples}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--repo", default=None, help="git repo (default: the scenario file's directory)")
    ap.add_argument("--base", default="HEAD~1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--logs", default=None, help="server, seed and setup logs (default: OUT/../logs)")
    ap.add_argument("--no-cache", action="store_true", help="temporary base worktree instead of the worktree cache")
    args = ap.parse_args()
    procs.install_sigterm()
    global PYTHON
    with open(args.scenario) as f:
        scenario = json.load(f)
    PYTHON = scenario.get("python") or sys.executable
    log_dir = os.path.abspath(args.logs or os.path.join(os.path.dirname(os.path.abspath(args.out)), "logs"))
    os.makedirs(log_dir, exist_ok=True)
    repo = os.path.abspath(args.repo or os.path.dirname(os.path.abspath(args.scenario)))
    os.makedirs(args.out, exist_ok=True)
    for stale in os.listdir(args.out):
        if stale.endswith(".json"):
            os.remove(os.path.join(args.out, stale))

    base = commit_info(repo, args.base)
    change = commit_info(repo, "HEAD")
    change["dirty"] = bool(git(repo, "status", "--porcelain"))
    tmp = tempfile.mkdtemp(prefix="backend-capture-")
    base_tree = os.path.join(tmp, "base")
    entry = None
    results = {}
    try:
        setup_log = os.path.join(log_dir, "setup-base.log")
        source = scenario.get("origin_repo") or repo
        if os.path.realpath(source) != os.path.realpath(repo):
            procs.prepare_base(repo, source, scenario.get("setup"), os.path.join(log_dir, "setup-change.log"),
                               child_env())
        if wtcache.enabled(scenario, args.no_cache):
            entry, status = wtcache.acquire(repo, base["sha"], scenario.get("setup"), source, setup_log, child_env())
            base_tree = entry.path
            base["checkout"] = f"cache_{status}"
        else:
            git(repo, "worktree", "add", "--detach", base_tree, base["sha"])
            procs.prepare_base(base_tree, source, scenario.get("setup"), setup_log, child_env())
            base["checkout"] = "temp"
        trees = {"base": base_tree, "change": repo}
        if "tests" in scenario:
            slots = {"python": PYTHON}
            results["tests"] = {"change": capture_tests(repo, scenario["tests"], slots),
                                "base": capture_tests(base_tree, scenario["tests"], slots, copy_from=repo)}
        if "server" in scenario:
            for side, tree in trees.items():
                side_dir = os.path.join(tmp, f"run-{side}")
                os.makedirs(side_dir)
                api, db_rec, flow = capture_http_and_db(tree, scenario, side_dir,
                                                        os.path.join(log_dir, f"server-{side}.log"))
                for name, value in (("api", api), ("db", db_rec), ("flow", flow)):
                    if value:
                        results.setdefault(name, {})[side] = value
            if "perf" in scenario:
                results["perf"] = capture_perf(trees, scenario, tmp, log_dir)
        if "probe" in scenario:
            results["behavior"] = {side: capture_probe(tree, scenario["probe"]) for side, tree in trees.items()}
    finally:
        if entry:
            wtcache.release(entry)
        else:
            procs.remove_worktree(repo, base_tree)
        shutil.rmtree(tmp, ignore_errors=True)

    keys = set(scenario.get("redact_keys", [])) | set(scenario.get("api", {}).get("redact_keys", []))
    results = scrubber.scrub(results, keys)

    meta = {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base": base, "change": change,
        "python": platform.python_version(), "platform": platform.platform(),
        "scenario_path": os.path.abspath(args.scenario),
        "scenario": scrubber.scrub(scenario, keys),
        "captures": sorted(results),
    }
    for name, payload in [("meta", meta), *results.items()]:
        with open(os.path.join(args.out, f"{name}.json"), "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
    print(f"captured base {base['short']} vs change {change['short']}: {', '.join(sorted(results))}")
    if "tests" in results:
        print(f"  tests: base exit={results['tests']['base']['exit_code']} change exit={results['tests']['change']['exit_code']}")
    if "perf" in results:
        for side in ("base", "change"):
            s = results["perf"]["summary"][side]
            print(f"  perf {side}: queries={s.get('query_count')} client p50={s['client_ms']['p50']:.2f}ms")


if __name__ == "__main__":
    main()
