#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import shlex
import pathlib
import signal
import subprocess
import sys
import tempfile
import time

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
PROVE = SKILL_DIR / "scripts" / "prove.py"
GIF_HEADER = b"GIF89a" + (1200).to_bytes(2, "little") + (900).to_bytes(2, "little") + b"\x00" * 16
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def start(*args: str) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-S", str(PROVE), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def wait_for(check, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.1)
    raise AssertionError("condition was not met in time")


def new_repo(path: pathlib.Path) -> pathlib.Path:
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "prove-it@example.test")
    git(path, "config", "user.name", "Prove It Test")
    return path


def rev(repo: pathlib.Path, ref: str = "HEAD") -> str:
    return subprocess.run(["git", "rev-parse", ref], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def run(*args: str, cwd: pathlib.Path | None = None, expect: int = 0) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run([sys.executable, "-S", str(PROVE), *args], cwd=cwd, text=True, capture_output=True)
    if cp.returncode != expect:
        raise AssertionError(
            f"command failed ({cp.returncode}, expected {expect}): {' '.join(args)}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
        )
    return cp


def git(repo: pathlib.Path, *args: str) -> None:
    cp = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if cp.returncode:
        raise AssertionError(cp.stderr)


def read_comments(path: pathlib.Path) -> list[dict[str, object]]:
    return json.loads(path.read_text()) if path.exists() else []


def write_fake_media(out: pathlib.Path, kind: str, artifacts: list[dict[str, object]], **extra: object) -> None:
    (out / "captures").mkdir(parents=True, exist_ok=True)
    (out / "captures" / "api.json").write_text("{}")
    for artifact in artifacts:
        path = out / str(artifact["file"])
        if str(artifact["file"]).endswith(".gif"):
            path.write_bytes(GIF_HEADER)
        elif str(artifact["file"]).endswith(".mmd"):
            path.write_text("sequenceDiagram\n    C->>H: GET /orders\n")
        else:
            path.write_bytes(PNG_1X1)
    manifest = {
        "kind": kind,
        "base": {"sha": "aaaaaaa", "ref": "base"},
        "change": {"sha": "bbbbbbb", "ref": None},
        "captured_at": "2026-09-24T00:00:00Z",
        "claim": "The orders list runs fewer queries.",
        "observations": ["`GET /orders` runs 2 queries instead of 42"],
        "passed": True,
        "caveat": "Latency is direction only. The query count is exact.",
        "notes": [],
        "artifacts": artifacts,
        **extra,
    }
    (out / "media-manifest.json").write_text(json.dumps(manifest))


def media_tests(root: pathlib.Path) -> None:
    repo = root / "media-repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "prove-it@example.test")
    git(repo, "config", "user.name", "Prove It Test")
    (repo / "web").mkdir()
    (repo / "web" / "index.html").write_text("<button id=save>Save</button>\n")
    (repo / ".prove-it.json").write_text(json.dumps({
        "app": {"start": "python3 -m http.server {port}", "ready": "http://127.0.0.1:3000/health"},
        "browser": {"viewport": [1440, 900]},
        "areas": [{"match": ["web/**"], "route": "/settings", "targeted_test": "python3 -m unittest -v"}],
    }))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
    (repo / "web" / "index.html").write_text("<button id=save>Save changes</button>\n")
    git(repo, "commit", "-qam", "change")
    head_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()

    run_dir = root / "media-proof"
    run("init", "--repo", str(repo), "--working-tree", "--out", str(run_dir), "--title", "Media proof")
    scenario = root / "scenario.json"
    scenario.write_text(json.dumps({
        "name": "Save label",
        "click": {"selector": "#save", "claim": "Save reads Save changes", "expect_text": "Save changes"},
        "tests": {"command": "python3 -m unittest -v"},
        "api": {"method": "GET", "path": "/orders"},
    }))
    bad = run("scenario", "--dir", str(run_dir), "--scenario", str(scenario), expect=2)
    assert "backend.api needs backend.server" in bad.stderr, bad.stderr
    scenario.write_text(json.dumps({
        "name": "Save label",
        "click": {"selector": "#save", "claim": "Save reads Save changes", "expect_text": "Save changes"},
        "tests": {"command": "python3 -m unittest -v"},
    }))
    plan = json.loads(run("scenario", "--dir", str(run_dir), "--scenario", str(scenario)).stdout)
    ui = plan["ui"]
    assert ui["serve"] == {"cmd": "python3 -m http.server {port}", "ready_path": "/health"}, ui
    assert ui["viewport"] == [1440, 900] and ui["path"] == "/settings" and ui["scale"] == 2, ui
    assert ui["click"]["change_selector"] == "#save" and ui["click"]["expect_text"] == ["Save changes"], ui
    assert ui["refs"] == {"base": base_sha, "change": None}, ui
    assert plan["backend"]["tests"]["command"] == ["python3", "-m", "unittest", "-v"], plan
    assert plan["backend"]["refs"]["base"] == base_sha, plan
    same = run("scenario", "--dir", str(run_dir), "--scenario", str(scenario), "--base", "HEAD", expect=2)
    assert "same commit and the tree is clean" in same.stderr, same.stderr
    steps_scenario = root / "steps-scenario.json"
    steps_scenario.write_text(json.dumps({
        "name": "Save flow", "claim": "Saving shows Saved",
        "ui": {"steps": [{"fill": "#name", "text": "Sam"}, {"click": {"role": "button", "name": "Save"}}],
               "expect_text": "Saved", "media": ["wipe.gif"], "auth": {"name": "demo"}},
    }))
    steps_plan = json.loads(run("scenario", "--dir", str(run_dir), "--scenario", str(steps_scenario)).stdout)["ui"]
    assert "click" not in steps_plan and len(steps_plan["steps"]) == 2, steps_plan
    assert steps_plan["expect_text"] == ["Saved"] and steps_plan["claim"] == "Saving shows Saved", steps_plan
    assert steps_plan["media"] == ["wipe.gif"] and steps_plan["auth"] == {"name": "demo"}, steps_plan
    flat = root / "flat-steps.json"
    flat.write_text(json.dumps({"name": "Flat", "claim": "c", "steps": [{"click": "#save"}], "path": "/x"}))
    flat_plan = json.loads(run("scenario", "--dir", str(run_dir), "--scenario", str(flat)).stdout)["ui"]
    assert flat_plan["steps"] == [{"click": "#save"}] and flat_plan["path"] == "/x", flat_plan
    bad_steps = root / "bad-steps.json"
    bad_steps.write_text(json.dumps({"ui": {"steps": []}}))
    refused = run("scenario", "--dir", str(run_dir), "--scenario", str(bad_steps), expect=2)
    assert "ui.steps must be a non-empty list" in refused.stderr, refused.stderr
    todo_scenario = root / "todo-scenario.json"
    todo_scenario.write_text(json.dumps({"name": "Draft", "todo": ["claim: write it", "ui.path: check it"],
                                         "ui": {"steps": [{"click": "#save"}]}}))
    todo = run("scenario", "--dir", str(run_dir), "--scenario", str(todo_scenario), expect=2)
    assert "2 todo item(s)" in todo.stderr and "ui.path: check it" in todo.stderr, todo.stderr
    todo_media = run("media", "--dir", str(run_dir), "--scenario", str(todo_scenario), expect=2)
    assert "todo item" in todo_media.stderr, todo_media.stderr
    placeholder = root / "placeholder-scenario.json"
    placeholder.write_text(json.dumps({"name": "Draft", "claim": "TODO: one sentence",
                                       "ui": {"serve": {"cmd": "TODO start command with {port}"},
                                              "steps": [{"click": {"role": "button", "name": "Save"}}, {"expect_text": "todo"}]}}))
    held = run("scenario", "--dir", str(run_dir), "--scenario", str(placeholder), expect=2)
    assert "3 todo item(s) or TODO placeholder(s)" in held.stderr and "ui.steps[1].expect_text" in held.stderr, held.stderr
    todo_app = root / "todo-app-scenario.json"
    todo_app.write_text(json.dumps({"name": "Todo app", "claim": "Adding a todo item shows it",
                                    "ui": {"steps": [{"click": "#add"}], "expect_text": "Buy milk todo"}}))
    run("scenario", "--dir", str(run_dir), "--scenario", str(todo_app))
    flag_tests()
    (repo / "web" / "index.html").write_text("<button id=save>Save now</button>\n")
    dirty_plan = json.loads(run("scenario", "--dir", str(run_dir), "--scenario", str(scenario)).stdout)
    assert dirty_plan["ui"]["refs"]["base"] == head_sha, dirty_plan
    git(repo, "checkout", "-q", "--", "web/index.html")
    scenario.write_text(json.dumps({"ui": {"click": {"label": "Save"}, "serve": {"static": "."}}}))
    no_selector = run("scenario", "--dir", str(run_dir), "--scenario", str(scenario), expect=2)
    assert "needs steps, or click.change_selector" in no_selector.stderr, no_selector.stderr
    scenario.write_text(json.dumps({"ui": {"click": {"selector": "#save"}, "serve": {"cmd": "npm run dev"}}}))
    no_port = run("scenario", "--dir", str(run_dir), "--scenario", str(scenario), expect=2)
    assert "must contain {port}" in no_port.stderr, no_port.stderr
    scenario.write_text(json.dumps({"ui": {"click": {"selector": "#save"}, "serve": {"static": "."}, "refs": {"change": "HEAD~1"}}}))
    wrong_change = run("scenario", "--dir", str(run_dir), "--scenario", str(scenario), expect=2)
    assert "always the working tree" in wrong_change.stderr, wrong_change.stderr

    scenario.write_text(json.dumps({"name": "orders", "backend": {"tests": {"command": ["python3", "-V"]}}}))
    out = run_dir / "media" / "backend"
    write_fake_media(out, "backend", [
        {"file": "red-green.png", "title": "Tests on both commits", "type": "screenshot", "placement": "inline", "source": "captures/api.json"},
        {"file": "numbers.png", "title": "Query count", "type": "screenshot", "placement": "details", "source": "captures/api.json"},
        {"file": "flow.mmd", "title": "Request flow", "type": "mermaid", "placement": "details", "source": "captures/api.json"},
        {"file": "input.png", "title": "Input only", "type": "screenshot", "placement": "none", "source": "captures/api.json"},
    ])
    registered = json.loads(run("media", "--dir", str(run_dir), "--scenario", str(scenario), "--reuse", "--proves").stdout)
    assert registered[0]["claim"] == "C1" and registered[0]["status"] == "passed", registered
    run("media", "--dir", str(run_dir), "--scenario", str(scenario), "--reuse", "--proves")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert len(manifest["claims"]) == 1, manifest["claims"]
    claim = manifest["claims"][0]
    assert claim["facts"] == ["`GET /orders` runs 2 queries instead of 42"], claim
    kinds = [(item["type"], item["path"]) for item in claim["evidence"]]
    assert kinds == [
        ("screenshot", "media/backend/red-green.png"),
        ("screenshot", "media/backend/numbers.png"),
        ("file", "media/backend/flow.mmd"),
        ("command", "media/backend/tool.log"),
    ], kinds
    shot = claim["evidence"][0]
    for key in ("sha256", "bytes", "width", "height"):
        assert key in shot["metadata"], shot
    assert shot["details"]["generated_by"] == "prove-it media" and shot["details"]["placement"] == "inline", shot
    assert shot["details"]["base_sha"] == "aaaaaaa" and shot["details"]["change_sha"] == "bbbbbbb", shot
    assert shot["details"]["source"] == "media/backend/captures/api.json", shot
    assert manifest["media_runs"] == [{
        "kind": "backend", "base": "aaaaaaa", "change": "bbbbbbb", "captured_at": "2026-09-24T00:00:00Z",
        "claim": "C1", "dir": "media/backend", "assertions": [],
    }], manifest["media_runs"]
    assert [note["text"] for note in manifest["notes"]] == ["Caveat: Latency is direction only. The query count is exact."], manifest["notes"]
    run("validate", "--dir", str(run_dir))
    run("render", "--dir", str(run_dir))
    template = (run_dir / "proof.template.md").read_text()
    proof = (run_dir / "proof.md").read_text()
    assert "![Tests on both commits]({{media:red-green.png}})" in template, template
    assert "![Tests on both commits](./media/backend/red-green.png)" in proof, proof
    assert "{{media:" not in proof, proof
    assert "against base `aaaaaaa`" in proof, proof
    assert "- `GET /orders` runs 2 queries instead of 42" in proof, proof
    assert proof.index("red-green.png") < proof.index("<summary>More media</summary>") < proof.index("numbers.png"), proof
    assert "```mermaid\nsequenceDiagram" in proof and "input.png" not in proof, proof
    assert "Caveat: Latency is direction only." in proof, proof

    dry = run("publish", "--dir", str(run_dir), "--dry-run").stdout
    assert "](https://github.com/user-attachments/assets/dry-run/red-green.png)" in dry, dry
    assert "{{media:" not in dry and "./media/" not in dry, dry
    assert run_dir.exists(), "dry run must keep the run directory"

    run("note", "--dir", str(run_dir), "--text", "Compare {{media:red-green.png}} with {{media:missing.png}}.")
    leftover_render = run("render", "--dir", str(run_dir), expect=1)
    assert "missing.png" in leftover_render.stderr or "missing.png" in leftover_render.stdout, leftover_render
    assert "{{media:missing.png}}" in (run_dir / "proof.md").read_text()
    assert "Compare ./media/backend/red-green.png" in (run_dir / "proof.md").read_text() or "red-green.png with" in (run_dir / "proof.md").read_text()
    leftover_publish = run("publish", "--dir", str(run_dir), "--dry-run", expect=2)
    assert "missing.png" in leftover_publish.stderr, leftover_publish.stderr
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["notes"] = [note for note in manifest["notes"] if "missing.png" not in note["text"]]
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    run("publish", "--dir", str(run_dir), "--dry-run")

    gif_dir = root / "gif-proof"
    run("init", "--repo", str(repo), "--working-tree", "--out", str(gif_dir))
    gif_scenario = root / "gif-scenario.json"
    gif_scenario.write_text(json.dumps({"ui": {"click": {"selector": "#save"}, "serve": {"static": "."}}}))
    write_fake_media(gif_dir / "media" / "ui", "ui", [
        {"file": "action.gif", "title": "Click", "type": "screenshot", "placement": "hero", "source": "captures/api.json"},
        {"file": "wipe.gif", "title": "Wipe", "type": "screenshot", "placement": "inline", "source": "captures/api.json"},
    ], passed=None)
    no_check = run("media", "--dir", str(gif_dir), "--scenario", str(gif_scenario), "--reuse", "--proves", expect=2)
    assert "no pass/fail check" in no_check.stderr, no_check.stderr
    run("media", "--dir", str(gif_dir), "--scenario", str(gif_scenario), "--reuse")
    two_gifs = run("validate", "--dir", str(gif_dir), expect=1)
    assert "more than one autoplaying GIF" in two_gifs.stdout, two_gifs.stdout
    write_fake_media(gif_dir / "media" / "ui", "ui", [
        {"file": "wide.png", "title": "Wide", "type": "screenshot", "placement": "inline", "source": "captures/missing.json"},
    ])
    missing_source = run("media", "--dir", str(gif_dir), "--scenario", str(gif_scenario), "--reuse", expect=2)
    assert "cards must come from captures" in missing_source.stderr, missing_source.stderr
    write_fake_media(gif_dir / "media" / "ui", "ui", [
        {"file": "wide.gif", "title": "Wide", "type": "screenshot", "placement": "hero", "source": "captures/api.json"},
    ])
    (gif_dir / "media" / "ui" / "wide.gif").write_bytes(b"GIF89a" + (2400).to_bytes(2, "little") + (900).to_bytes(2, "little") + b"\x00" * 16)
    run("media", "--dir", str(gif_dir), "--scenario", str(gif_scenario), "--reuse")
    too_wide = run("validate", "--dir", str(gif_dir), expect=1)
    assert "2400px wide" in too_wide.stdout, too_wide.stdout

    names_dir = root / "names-proof"
    run("init", "--repo", str(repo), "--working-tree", "--out", str(names_dir))
    both = root / "both-scenario.json"
    both.write_text(json.dumps({"ui": {"click": {"selector": "#save"}, "serve": {"static": "."}},
                                "backend": {"tests": {"command": "true"}}}))
    write_fake_media(names_dir / "media" / "ui", "ui", [
        {"file": "numbers.png", "title": "UI numbers", "type": "screenshot", "placement": "inline", "source": "captures/api.json"},
        {"file": "twin.mp4", "title": "Twin", "type": "video", "placement": "inline", "source": "captures/api.json"},
    ], claim="")
    no_claim = run("media", "--dir", str(names_dir), "--scenario", str(both), "--kind", "ui", "--reuse", expect=2)
    assert "has no claim" in no_claim.stderr, no_claim.stderr
    write_fake_media(names_dir / "media" / "ui", "ui", [
        {"file": "numbers.png", "title": "UI numbers", "type": "screenshot", "placement": "inline", "source": "captures/api.json"},
        {"file": "twin.mp4", "title": "Twin", "type": "video", "placement": "inline", "source": "captures/api.json"},
    ])
    (names_dir / "media" / "ui" / "twin.mp4").write_bytes(b"fake-video")
    write_fake_media(names_dir / "media" / "backend", "backend", [
        {"file": "numbers.png", "title": "Backend numbers", "type": "screenshot", "placement": "details", "source": "captures/api.json"},
    ], passed=None, not_proven_reason="The tests pass on base too, so they do not isolate this change.")
    run("media", "--dir", str(names_dir), "--scenario", str(both), "--kind", "ui", "--reuse")
    run("media", "--dir", str(names_dir), "--scenario", str(both), "--kind", "backend", "--reuse", "--proves")
    names_manifest = json.loads((names_dir / "manifest.json").read_text())
    backend_claim = next(c for c in names_manifest["claims"] if c["id"] == names_manifest["media_runs"][-1]["claim"])
    assert backend_claim["status"] == "not_proven" and "do not isolate" in backend_claim["observed"], backend_claim
    run("render", "--dir", str(names_dir))
    names_template = (names_dir / "proof.template.md").read_text()
    assert "{{media:numbers.png}}" in names_template and "{{media:numbers-2.png}}" in names_template, names_template
    assert "./media/backend/numbers.png" in (names_dir / "proof.md").read_text()
    names_dry = run("publish", "--dir", str(names_dir), "--dry-run").stdout
    assert "\nhttps://github.com/user-attachments/assets/dry-run/twin.mp4\n" in names_dry, names_dry
    names_manifest["claims"][0]["text"] = " "
    (names_dir / "manifest.json").write_text(json.dumps(names_manifest))
    empty = run("validate", "--dir", str(names_dir), expect=1)
    assert "claim text is empty" in empty.stdout, empty.stdout
    write_fake_media(names_dir / "media" / "ui", "ui", [
        {"file": "my card.png", "title": "Bad", "type": "screenshot", "placement": "inline", "source": "captures/api.json"},
    ])
    bad_name = run("media", "--dir", str(names_dir), "--scenario", str(both), "--kind", "ui", "--reuse", expect=2)
    assert "letters, digits" in bad_name.stderr, bad_name.stderr


MEDIA = SKILL_DIR / "scripts" / "media"


def flag_tests() -> None:
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import prove  # noqa: E402

    seen: list[list[str]] = []
    original = prove.run_media_tool
    prove.run_media_tool = lambda argv, cwd, log, timeout=0: seen.append([str(a) for a in argv]) or ""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            args = prove.build_parser().parse_args(["media", "--dir", tmp, "--scenario", "s.json", "--all-media", "--no-cache"])
            flags = prove.media_tool_flags(args)
            assert flags == {"ui": ["--no-cache", "--all-media"], "backend": ["--no-cache"]}, flags
            prove.run_capture_tools("ui", {"repo": tmp, "refs": {"base": "x"}}, out, flags["ui"])
            prove.run_capture_tools("backend", {"repo": tmp, "refs": {"base": "x"}}, out, flags["backend"])
            plain = prove.media_tool_flags(prove.build_parser().parse_args(["media", "--dir", tmp, "--scenario", "s.json"]))
            assert plain == {"ui": [], "backend": []}, plain
    finally:
        prove.run_media_tool = original
    ui_argv, capture_argv, render_argv = seen
    assert ui_argv[1].endswith("ui/build.py") and ui_argv[-2:] == ["--no-cache", "--all-media"], ui_argv
    assert capture_argv[1].endswith("backend/capture.py") and capture_argv[-1] == "--no-cache", capture_argv
    assert "--no-cache" not in render_argv, render_argv


def classifier_tests(root: pathlib.Path) -> None:
    repo = new_repo(root / "classify-repo")
    (repo / "README.md").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "checkout", "-qb", "feature")
    core = repo / "apps" / "dashboard" / "lib" / "core" / "orders" / "public" / "queries"
    core.mkdir(parents=True)
    (core / "get-order.ts").write_text("export const getOrder = (id: string) => id;\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "bounded-context api")
    scan = json.loads(run("scan", "--repo", str(repo), "--base", "main", "--json").stdout)
    item = next(f for f in scan["files"] if f["path"].endswith("get-order.ts"))
    assert item["categories"] == ["backend"], item
    assert scan["recommended_proof"] == "backend", scan

    assets = repo / "apps" / "dashboard" / "public"
    assets.mkdir(parents=True)
    (assets / "logo.png").write_bytes(PNG_1X1)
    (assets / "sw.js").write_text("self.addEventListener('fetch', () => {});\n")
    (repo / "public").mkdir()
    (repo / "public" / "index.html").write_text("<main>hi</main>\n")
    route = repo / "apps" / "dashboard" / "app" / "api" / "orders"
    route.mkdir(parents=True)
    (route / "route.ts").write_text("export const GET = () => Response.json({});\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "static assets")
    scan = json.loads(run("scan", "--repo", str(repo), "--base", "main", "--json").stdout)
    kinds = {f["path"]: f["categories"] for f in scan["files"]}
    assert "frontend" in kinds["apps/dashboard/public/logo.png"], kinds
    assert "frontend" in kinds["apps/dashboard/public/sw.js"], kinds
    assert "frontend" in kinds["public/index.html"], kinds
    assert kinds["apps/dashboard/lib/core/orders/public/queries/get-order.ts"] == ["backend"], kinds
    assert kinds["apps/dashboard/app/api/orders/route.ts"] == ["backend"], kinds

    (repo / ".prove-it.json").write_text(json.dumps({"classify": {"apps/*/lib/core/**": "frontend", "public/**": ["docs"]}}))
    scan = json.loads(run("scan", "--repo", str(repo), "--base", "main", "--json").stdout)
    kinds = {f["path"]: f["categories"] for f in scan["files"]}
    assert kinds["apps/dashboard/lib/core/orders/public/queries/get-order.ts"] == ["frontend"], kinds
    assert kinds["public/index.html"] == ["docs"], kinds
    (repo / ".prove-it.json").write_text(json.dumps({"classify": {"apps/**": "widget"}}))
    bad = run("scan", "--repo", str(repo), "--base", "main", expect=2)
    assert "must name kinds from" in bad.stderr, bad.stderr


def concurrency_tests(root: pathlib.Path) -> None:
    repo = new_repo(root / "race-repo")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    proof = root / "race-proof"
    run("init", "--repo", str(repo), "--out", str(proof), "--mode", "expanded")
    procs = [
        start("claim", "--dir", str(proof), "--id", f"P{i}", "--text", f"Claim {i}", "--expected", "kept", "--method", "command", "--force")
        for i in range(8)
    ]
    for proc in procs:
        _, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err
    procs = [
        start("run", "--dir", str(proof), "--claim", f"P{i}", "--label", f"check {i}", "--proves", "--",
              sys.executable, "-c", f"import time; time.sleep(0.2); print('ok {i}')")
        for i in range(8)
    ]
    for proc in procs:
        _, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err
    manifest = json.loads((proof / "manifest.json").read_text())
    claims = {c["id"]: c for c in manifest["claims"]}
    assert sorted(claims) == [f"P{i}" for i in range(8)], sorted(claims)
    for cid, claim in claims.items():
        assert claim["status"] == "passed" and len(claim["evidence"]) == 1, claim
    assert not list(proof.glob("manifest.json.*.tmp")), list(proof.iterdir())


def command_tests(root: pathlib.Path) -> None:
    repo = new_repo(root / "command-repo")
    (repo / "model.pkl").write_text("x")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    proof = root / "command-proof"
    run("init", "--repo", str(repo), "--out", str(proof), "--mode", "expanded")
    run("claim", "--dir", str(proof), "--text", "Globs stay literal.", "--expected", "The runner sees *.pkl.", "--method", "command")
    show = "import sys; print('args=' + ','.join(sys.argv[1:]))"
    run("run", "--dir", str(proof), "--claim", "C1", "--label", "literal glob", "--expect-output", "args=*.pkl",
        "--command", f"{shlex.quote(sys.executable)} -c {shlex.quote(show)} *.pkl | cat")
    run("run", "--dir", str(proof), "--claim", "C1", "--label", "argv glob", "--expect-output", "args=*.pkl", "--",
        sys.executable, "-c", show, "*.pkl")
    run("run", "--dir", str(proof), "--claim", "C1", "--label", "expanded glob", "--glob", "--expect-output", "args=model.pkl",
        "--command", f"{shlex.quote(sys.executable)} -c {shlex.quote(show)} *.pkl")

    run("claim", "--dir", str(proof), "--text", "A killed run keeps its receipt.", "--expected", "Partial output survives.", "--method", "command")
    child = root / "child.pid"
    slow = f"import os, pathlib, time; pathlib.Path({str(child)!r}).write_text(str(os.getpid())); print('child ' + 'started', flush=True); time.sleep(60)"
    proc = start("run", "--dir", str(proof), "--claim", "C2", "--label", "slow check", "--", sys.executable, "-c", slow)
    live = proof / "backend" / "c2-slow-check.partial.txt"
    wait_for(lambda: live.exists() and "child started" in live.read_text())
    proc.send_signal(signal.SIGKILL)
    proc.communicate(timeout=10)
    os.kill(int(child.read_text()), signal.SIGKILL)
    manifest = json.loads((proof / "manifest.json").read_text())
    evidence = next(c for c in manifest["claims"] if c["id"] == "C2")["evidence"]
    assert len(evidence) == 1 and evidence[0]["status"] == "running", evidence
    assert evidence[0]["path"] == "backend/c2-slow-check.partial.txt", evidence
    assert "child started" in live.read_text() and "status: running" in live.read_text()
    report = json.loads(run("validate", "--dir", str(proof)).stdout)
    assert any("did not finish" in w for w in report["warnings"]), report

    child.unlink()
    proc = start("run", "--dir", str(proof), "--claim", "C2", "--label", "term check", "--proves", "--", sys.executable, "-c", slow)
    term_live = proof / "backend" / "c2-term-check.partial.txt"
    wait_for(lambda: term_live.exists() and "child started" in term_live.read_text())
    proc.send_signal(signal.SIGTERM)
    proc.communicate(timeout=30)
    assert proc.returncode == 143, proc.returncode
    pid = int(child.read_text())
    wait_for(lambda: subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode != 0, 10)
    assert not term_live.exists()
    receipt = (proof / "backend" / "c2-term-check.txt").read_text()
    assert "interrupted: SIGTERM" in receipt and "child started" in receipt, receipt
    manifest = json.loads((proof / "manifest.json").read_text())
    claim = next(c for c in manifest["claims"] if c["id"] == "C2")
    final = next(e for e in claim["evidence"] if e["label"] == "term check")
    assert final["status"] == "failed" and final["details"]["interrupted"] == "SIGTERM", final
    assert claim["status"] == "pending", claim


def pin_and_publish_tests(root: pathlib.Path, repo: pathlib.Path, head: str, comments_file: pathlib.Path) -> None:
    show = "print(open('index.js').read())"
    pinned = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--pin", "--title", "Pinned proof").stdout.strip())
    checkout = pinned / "checkout"
    assert rev(checkout) == head, "pin must check out the capture SHA"
    assert json.loads((pinned / "manifest.json").read_text())["run"]["checkout"] == str(checkout.resolve())
    run("claim", "--dir", str(pinned), "--text", "Numeric strings are added numerically.", "--expected", "Number(a) is in the code.", "--method", "command", "--code", "index.js:1")
    git(repo, "checkout", "-q", "main")
    run("run", "--dir", str(pinned), "--claim", "C1", "--label", "pinned source", "--expect-output", "Number(a)", "--proves", "--", sys.executable, "-c", show)
    assert (repo / "index.js").read_text().startswith("export const add = (a, b) => a + b"), "pin must not touch the shared checkout"
    (checkout / "dist.txt").write_text("build output")
    dirty = run("publish", "--dir", str(pinned), "--dry-run", expect=2)
    assert "Dirty files: dist.txt" in dirty.stderr, dirty.stderr
    (checkout / "dist.txt").unlink()
    run("publish", "--dir", str(pinned))
    assert not pinned.exists()
    assert not any("checkout" in line for line in worktrees(repo)), worktrees(repo)
    assert "Number(a)" in str(read_comments(comments_file)[-1]["body"])
    git(repo, "checkout", "-q", "feature")

    moved = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Moved checkout").stdout.strip())
    run("claim", "--dir", str(moved), "--text", "Numeric strings are added numerically.", "--expected", "Number(a) is in the code.", "--method", "command", "--code", "index.js:1")
    run("run", "--dir", str(moved), "--claim", "C1", "--label", "shared source", "--expect-output", "Number(a)", "--proves", "--", sys.executable, "-c", show)
    git(repo, "checkout", "-q", "main")
    refused = run("run", "--dir", str(moved), "--claim", "C1", "--label", "wrong source", "--", sys.executable, "-c", show, expect=2)
    assert "Nothing ran" in refused.stderr and "init --pin" in refused.stderr, refused.stderr
    run("visualize", "--dir", str(moved))
    run("publish", "--dir", str(moved))
    assert "backend-behavior.png" in str(read_comments(comments_file)[-1]["body"])
    git(repo, "checkout", "-q", "feature")

    svg = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "SVG proof").stdout.strip())
    run("claim", "--dir", str(svg), "--text", "The flow is explained.", "--expected", "A diagram is attached.", "--method", "command", "--code", "index.js:1")
    diagram = root / "hand-flow.svg"
    diagram.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')
    run("add", "--dir", str(svg), "--claim", "C1", "--type", "diagram", "--path", str(diagram), "--label", "Hand flow")
    refused = run("publish", "--dir", str(svg), "--dry-run", expect=2)
    assert "GitHub rejects SVG attachments" in refused.stderr and "hand-flow.svg" in refused.stderr, refused.stderr
    manifest = json.loads((svg / "manifest.json").read_text())
    manifest["claims"][0]["evidence"] = []
    (svg / "manifest.json").write_text(json.dumps(manifest))
    legacy = svg / "frontend" / "backend-behavior.svg"
    legacy.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')
    run("status", "--dir", str(svg), "--claim", "C1", "--status", "passed", "--observed", "Explained.")
    manifest = json.loads((svg / "manifest.json").read_text())
    manifest["claims"][0]["evidence"] = [{"id": "E1", "type": "diagram", "label": "Backend checks", "status": "passed", "path": "frontend/backend-behavior.svg", "metadata": {}, "details": {"generated_by": "prove-it"}}]
    (svg / "manifest.json").write_text(json.dumps(manifest))
    dry = run("publish", "--dir", str(svg), "--dry-run").stdout
    assert "backend-behavior.png" in dry and "backend-behavior.svg" not in dry, dry

    (repo / ".prove-it.json").write_text(json.dumps({"ignore_dirty": ["gen/**"]}))
    git(repo, "add", ".prove-it.json")
    git(repo, "commit", "-qm", "ignore generated files")
    os.environ["FAKE_GH_HEAD"] = rev(repo)
    generated = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Generated output").stdout.strip())
    run("claim", "--dir", str(generated), "--text", "Numeric strings are added numerically.", "--expected", "Number(a) is in the code.", "--method", "command", "--code", "index.js:1")
    run("run", "--dir", str(generated), "--claim", "C1", "--label", "build", "--proves", "--command", "mkdir -p gen && echo built > gen/out.txt && echo stray > stray.txt")
    dirty = run("publish", "--dir", str(generated), "--dry-run", expect=2)
    assert "Dirty files: stray.txt." in dirty.stderr and "gen/out.txt" not in dirty.stderr, dirty.stderr
    (repo / "stray.txt").unlink()
    run("publish", "--dir", str(generated), "--dry-run")
    run("cleanup", "--dir", str(generated))
    import shutil
    shutil.rmtree(repo / "gen")
    os.environ["FAKE_GH_HEAD"] = head


def validator_tests() -> None:
    validator = SKILL_DIR / "scripts" / "validate_skill.py"
    ok = subprocess.run([sys.executable, str(validator), str(SKILL_DIR)], text=True, capture_output=True)
    assert ok.returncode == 0 and "PASS" in ok.stdout, ok.stdout + ok.stderr
    bad = subprocess.run([sys.executable, str(validator), "/nonexistent-skill"], text=True, capture_output=True)
    assert bad.returncode == 2 and "pass the skill directory" in bad.stderr, bad.stderr


def tool(script: str, *args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(MEDIA / script), *args], cwd=cwd, text=True, capture_output=True, timeout=180)


def worktrees(repo: pathlib.Path) -> list[str]:
    out = subprocess.run(["git", "worktree", "list"], cwd=repo, text=True, capture_output=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def alive(marker: str) -> bool:
    return subprocess.run(["pgrep", "-f", marker], capture_output=True).returncode == 0


def tool_tests(root: pathlib.Path) -> None:
    repo = root / "tool-repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "prove-it@example.test")
    git(repo, "config", "user.name", "Prove It Test")
    (repo / ".gitignore").write_text(".env\n.venv/\nsetup.done\n__pycache__/\n")
    (repo / "app.py").write_text("def f(x):\n    return {'email': 'a@b.c', 'note': 'password=hunter2', 'x': x}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    (repo / "app.py").write_text("def f(x):\n    return {'email': 'a@b.c', 'note': 'password=hunter2', 'x': x * 2}\n")
    git(repo, "commit", "-qam", "change")
    (repo / ".env").write_text("SECRET_FLAG=1\n")
    (repo / ".venv" / "bin").mkdir(parents=True)
    venv_python = repo / ".venv" / "bin" / "python"
    venv_python.write_text(f"#!/bin/sh\nPROVE_IT_VENV=1 exec {shlex.quote(sys.executable)} \"$@\"\n")
    venv_python.chmod(0o755)
    marker = f"prove-it-leak-{os.getpid()}"

    run_dir = root / "tool-proof"
    run("init", "--repo", str(repo), "--working-tree", "--out", str(run_dir))
    scenario = root / "tool-scenario.json"
    scenario.write_text(json.dumps({"claim": "f doubles x", "backend": {"probe": {"module": "app", "function": "f", "inputs": [1]}}}))
    plan = json.loads(run("scenario", "--dir", str(run_dir), "--scenario", str(scenario)).stdout)
    assert pathlib.Path(plan["backend"]["python"]).parent.resolve() == (repo / ".venv" / "bin").resolve(), plan

    failing = root / "failing.json"
    failing.write_text(json.dumps({"claim": "The server answers", "backend": {
        "server": {
            "command": ["{python}", "-c",
                        "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)', '" + marker + "']);"
                        " print('fatal: cannot bind the port', flush=True); time.sleep(600)"],
            "ready_path": "/", "ready_timeout": 2,
        },
        "api": {"method": "GET", "path": "/"},
    }}))
    failed = run("media", "--dir", str(run_dir), "--scenario", str(failing), expect=2)
    assert "fatal: cannot bind the port" in failed.stderr, failed.stderr
    assert "did not answer" in failed.stderr, failed.stderr
    assert len(worktrees(repo)) == 1, worktrees(repo)
    time.sleep(0.5)
    assert not alive(marker), "server process group must be stopped after a failed start"
    assert (run_dir / "media" / "backend" / "logs" / "server-base.log").exists()

    ui_scenario = {
        "repo": str(repo), "path": "/", "refs": {"base": "HEAD~1", "change": None},
        "serve": {"cmd": "{python} -c \"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)', '"
                  + marker + "-ui']); print('ui server boom', flush=True); time.sleep(600)\" {port}", "ready_timeout": 2},
        "setup": {"command": "touch setup.done", "link_from_change": [".env"]},
    }
    probe = subprocess.run([sys.executable, "-c",
        "import json, sys; sys.path.insert(0, sys.argv[1]); import scenario\n"
        "s = json.loads(sys.argv[2]); s['_file'] = 'x'\n"
        "try:\n    scenario.Checkouts(s, sys.argv[3]).__enter__()\nexcept RuntimeError as exc:\n    print(exc)\n",
        str(MEDIA / "ui"), json.dumps(ui_scenario), str(root / "ui-work")], text=True, capture_output=True, timeout=120)
    assert "ui server boom" in probe.stdout, probe.stdout + probe.stderr
    assert len(worktrees(repo)) == 1, worktrees(repo)
    time.sleep(0.5)
    assert not alive(marker + "-ui"), "UI server process group must be stopped after a failed start"

    out = root / "tool-captures"
    good = root / "good.json"
    good.write_text(json.dumps({
        "name": "tool", "python": str(repo / ".venv" / "bin" / "python"), "redact_keys": ["email"],
        "setup": {"command": "touch setup.done", "link_from_change": [".env", "../escape"]},
        "tests": {"command": ["{python}", "-c",
                              "import os, sys; print('env=%s setup=%s' % (os.path.exists('.env'), os.path.exists('setup.done'))); "
                              "print('password=hunter2'); print('venv=%s' % os.environ.get('PROVE_IT_VENV'))"]},
        "probe": {"module": "app", "function": "f", "inputs": [2]},
    }))
    escaped = tool("backend/capture.py", "--scenario", str(good), "--repo", str(repo), "--base", "HEAD~1", "--out", str(out))
    assert escaped.returncode != 0 and "must stay inside the repo" in escaped.stderr, escaped.stderr
    assert len(worktrees(repo)) == 1, worktrees(repo)
    spec = json.loads(good.read_text())
    spec["setup"]["link_from_change"] = [".env"]
    good.write_text(json.dumps(spec))
    ok = tool("backend/capture.py", "--scenario", str(good), "--repo", str(repo), "--base", "HEAD~1", "--out", str(out))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert len(worktrees(repo)) == 1, worktrees(repo)
    captured = (out / "tests.json").read_text() + (out / "behavior.json").read_text()
    tests_json = json.loads((out / "tests.json").read_text())
    assert "env=True setup=True" in tests_json["base"]["stdout"], tests_json["base"]
    assert "env=True setup=False" in tests_json["change"]["stdout"], tests_json["change"]
    assert "venv=1" in tests_json["change"]["stdout"] and "venv=1" in tests_json["base"]["stdout"], tests_json
    assert "hunter2" not in captured and "a@b.c" not in captured, captured
    assert "[REDACTED]" in captured and "<redacted>" in captured, captured

    rendered = tool("backend/render.py", "--captures", str(out), "--out", str(root / "tool-media"), "--no-shots")
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    media_manifest = json.loads((root / "tool-media" / "media-manifest.json").read_text())
    assert media_manifest["passed"] is None, media_manifest
    assert "pass on base too" in media_manifest["not_proven_reason"], media_manifest
    assert "pass on base too" in media_manifest["caveat"], media_manifest
    card = (root / "tool-media" / "html" / "red-green.html").read_text()
    assert "Tests: green on both commits" in card and "red on base" not in card, card
    red = "Ran 1 test in 0.001s\n\nFAILED (failures=1)\n"
    import_error = "ImportError: cannot import name 'new_fn'\nRan 1 test in 0.001s\n\nFAILED (errors=1)\n"
    green_out = {side: dict(tests_json[side]) for side in ("base", "change")}
    for base_exit, change_exit, base_text, expected in ((1, 0, red, True), (1, 0, import_error, None),
                                                        (127, 0, "sh: pytest: not found", None),
                                                        (0, 1, red, False), (1, 1, red, False)):
        tests_json["base"] = {**green_out["base"], "exit_code": base_exit,
                              "stderr": base_text if base_exit else green_out["base"]["stderr"]}
        tests_json["change"] = {**green_out["change"], "exit_code": change_exit,
                                "stderr": red if change_exit else green_out["change"]["stderr"]}
        (out / "tests.json").write_text(json.dumps(tests_json))
        tool("backend/render.py", "--captures", str(out), "--out", str(root / "tool-media"), "--no-shots")
        verdict = json.loads((root / "tool-media" / "media-manifest.json").read_text())["passed"]
        assert verdict is expected, (base_exit, change_exit, base_text, verdict)
    assert "Tests: red on both commits" in (root / "tool-media" / "html" / "red-green.html").read_text()

    spec["tests"]["command"] = ["{python}", "-c", "import time; time.sleep(30)"]
    spec["tests"]["timeout"] = 1
    spec.pop("probe")
    good.write_text(json.dumps(spec))
    slow = tool("backend/capture.py", "--scenario", str(good), "--repo", str(repo), "--base", "HEAD~1", "--out", str(out))
    assert slow.returncode == 0, slow.stderr
    slow_tests = json.loads((out / "tests.json").read_text())
    assert slow_tests["change"]["exit_code"] == 124 and slow_tests["change"]["timed_out"], slow_tests

    verdicts = subprocess.run([sys.executable, "-c",
        "import json, sys; sys.path.insert(0, sys.argv[1]); import build\n"
        "cases = [(False, True, False), (True, True, True), (False, True, True), (True, True, False), (False, False, False)]\n"
        "out = []\n"
        "for before, after, base in cases:\n"
        "    seen = {('change_before', 'Saved'): before, ('change_after', 'Saved'): after, ('base_after', 'Saved'): base}\n"
        "    out.append(build.expect_verdict(build.expect_assertions(['Saved'], seen)))\n"
        "print(json.dumps(out))\n", str(MEDIA / "ui")], text=True, capture_output=True, timeout=60)
    results = json.loads(verdicts.stdout)
    assert [item[0] for item in results] == [True, None, None, None, False], results
    assert "also shows on base" in results[2][1] and "before the flow" in results[3][1], results
    assert "not on the change page" in results[4][1], results


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="prove-it-self-test-") as tmp:
        root = pathlib.Path(tmp)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
body_file = pathlib.Path(os.environ.get("FAKE_GH_BODY_FILE", "/tmp/fake-gh-body.md"))
comments_file = pathlib.Path(os.environ.get("FAKE_GH_COMMENTS_FILE", "/tmp/fake-gh-comments.json"))
head_file_raw = os.environ.get("FAKE_GH_HEAD_FILE", "")
head_file = pathlib.Path(head_file_raw) if head_file_raw else None
head = head_file.read_text().strip() if head_file and head_file.exists() else os.environ.get("FAKE_GH_HEAD", "")

def comments():
    return json.loads(comments_file.read_text()) if comments_file.exists() else []

def save(items):
    comments_file.write_text(json.dumps(items))

if args == ["--version"]:
    print("gh version 9.9.9")
    raise SystemExit(0)
if args[:3] == ["pr", "comment", "--help"]:
    print("--attach <file>\n--body-file <file>")
    raise SystemExit(0)
if args[:2] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner": "test/prove-it"}))
    raise SystemExit(0)
if args[:2] == ["pr", "view"]:
    print(json.dumps({
        "number": 42,
        "url": "https://github.com/test/prove-it/pull/42",
        "title": "Test proof",
        "headRefOid": head,
        "headRefName": "feature",
        "baseRefName": "main",
        "isDraft": False,
        "state": "OPEN",
    }))
    raise SystemExit(0)
if args[:2] == ["pr", "comment"]:
    body_path = pathlib.Path(args[args.index("--body-file") + 1])
    body = body_path.read_text()
    i = 0
    while i < len(args):
        if args[i] == "--attach":
            rel = args[i + 1].split("#", 1)[0]
            url = "https://github.com/user-attachments/assets/" + pathlib.Path(rel).name
            if pathlib.Path(rel).suffix.lower() in {".mp4", ".mov", ".webm"}:
                body = body.replace("![](./" + rel + ")", url)
                body = body.replace("![](" + rel + ")", url)
            else:
                body = body.replace("](./" + rel + ")", "](" + url + ")")
                body = body.replace("](" + rel + ")", "](" + url + ")")
            i += 2
        else:
            i += 1
    items = comments()
    comment_id = 9000 + len(items) + 1
    url = f"https://github.com/test/prove-it/pull/42#issuecomment-{comment_id}"
    items.append({"id": comment_id, "body": body, "html_url": url})
    save(items)
    head_after = os.environ.get("FAKE_GH_HEAD_AFTER_COMMENT", "")
    if head_file and head_after:
        head_file.write_text(head_after)
    print(url)
    raise SystemExit(int(os.environ.get("FAKE_GH_COMMENT_EXIT", "0")))
if args and args[0] == "api":
    if "--method" in args and args[args.index("--method") + 1] == "PATCH":
        endpoint = args[args.index("--method") + 2]
        comment_id = int(endpoint.rsplit("/", 1)[1])
        payload = json.loads(pathlib.Path(args[args.index("--input") + 1]).read_text())
        items = comments()
        for item in items:
            if int(item["id"]) == comment_id:
                item["body"] = payload["body"]
                save(items)
                print(json.dumps(item))
                raise SystemExit(0)
        raise SystemExit(4)
    endpoint = args[-1]
    if "/issues/comments/" in endpoint:
        comment_id = int(endpoint.rsplit("/", 1)[1])
        for item in comments():
            if int(item["id"]) == comment_id:
                print(json.dumps(item))
                raise SystemExit(0)
        raise SystemExit(4)
    if "/issues/42/comments" in endpoint:
        value = comments()
        print(json.dumps([value] if "--slurp" in args else value))
        raise SystemExit(0)
print("unsupported fake gh args: " + repr(args), file=sys.stderr)
raise SystemExit(2)
''',
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        os.environ["PATH"] = str(fake_bin) + os.pathsep + os.environ.get("PATH", "")
        os.environ["PROVE_IT_NO_CACHE"] = "1"
        os.environ["PROVE_IT_KEEP_SERVERS"] = "0"
        pr_body_file = root / "fake-pr-body.md"
        pr_body_file.write_text("## What\n\nOriginal PR description.\n")
        comments_file = root / "fake-gh-comments.json"
        comments_file.write_text("[]")
        os.environ["FAKE_GH_BODY_FILE"] = str(pr_body_file)
        os.environ["FAKE_GH_COMMENTS_FILE"] = str(comments_file)

        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "prove-it@example.test")
        git(repo, "config", "user.name", "Prove It Test")
        (repo / "index.js").write_text("export const add = (a, b) => a + b;\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "base")
        git(repo, "branch", "-M", "main")
        git(repo, "checkout", "-qb", "feature")
        (repo / "index.js").write_text("export const add = (a, b) => Number(a) + Number(b);\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "handle numeric strings")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        os.environ["FAKE_GH_HEAD"] = head

        scan = json.loads(run("scan", "--repo", str(repo), "--base", "main", "--json").stdout)
        assert scan["recommended_proof"] == "backend", scan

        # Backend-only proof renders concrete receipts and no decorative graphics.
        backend = root / "backend-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(backend), "--title", "Numeric string addition")
        run(
            "claim", "--dir", str(backend), "--text", "Numeric strings are added numerically.",
            "--expected", "add('2', '3') returns 5.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(backend), "--claim", "C1", "--kind", "test",
            "--label", "Focused Node assertion", "--expect-output", "result=5",
            "--observed", "The executable example returned result=5.", "--proves", "--",
            "node", "--input-type=module", "-e",
            "import('./index.js').then(m=>{const value=m.add('2','3');console.log('result='+value);if(value!==5)process.exit(1)})",
        )
        run(
            "example", "--dir", str(backend), "--claim", "C1",
            "--input", "add('2', '3')", "--observed", "5",
        )
        run("note", "--dir", str(backend), "--text", "Local executable example; no network call.")
        run("visualize", "--dir", str(backend))
        run("render", "--dir", str(backend))
        backend_md = (backend / "proof.md").read_text()
        assert "## QA" in backend_md and "## QA:" not in backend_md, backend_md
        assert "Tested on" in backend_md, backend_md
        assert "- The executable example returned result=5." not in backend_md, backend_md
        assert "add('2', '3') produced 5" in backend_md, backend_md
        assert "**Scope:** Local executable example; no network call." in backend_md, backend_md
        assert backend_md.index("**Scope:**") < backend_md.index("backend-behavior.png"), backend_md
        assert "### Backend" not in backend_md, backend_md
        assert "output:" in backend_md and "result=5" in backend_md, backend_md
        assert backend_md.index("<details>") < backend_md.index("output:"), backend_md
        assert "What I ran" in backend_md, backend_md
        for phrase in ("Verified on", "Runtime evidence", "Evidence:", "Freshness:", "> [!"):
            assert phrase not in backend_md, backend_md
        assert "claims proven" not in backend_md.casefold(), backend_md
        assert "proof map" not in backend_md.casefold(), backend_md
        assert "- [x]" not in backend_md.casefold(), backend_md
        assert json.loads((backend / "attachments.json").read_text())["files"] == ["frontend/backend-behavior.png"]
        assert (backend / "frontend" / "backend-behavior.png").read_bytes().startswith(b"\x89PNG")
        backend_svg = (backend / "frontend" / "backend-behavior.svg").read_text()
        assert "Backend checks" in backend_svg, backend_svg
        assert "Numeric strings are added" in backend_svg and "numerically." in backend_svg, backend_svg
        assert "index.js:1" in backend_svg, backend_svg
        assert "add(&#x27;2&#x27;, &#x27;3&#x27;)" in backend_svg, backend_svg
        assert ">5</text>" in backend_svg, backend_svg
        assert "PASSED" in backend_svg, backend_svg
        assert "…" not in backend_svg, backend_svg
        assert "aria-labelledby" in backend_svg and "<desc" in backend_svg, backend_svg
        assert not (backend / "visual").exists()

        ui_without_visual = root / "ui-without-visual"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(ui_without_visual), "--title", "Visible reviewer state")
        ui_manifest_path = ui_without_visual / "manifest.json"
        ui_manifest = json.loads(ui_manifest_path.read_text())
        ui_manifest["change"]["recommended_proof"] = "mixed"
        ui_manifest_path.write_text(json.dumps(ui_manifest, indent=2) + "\n")
        run(
            "claim", "--dir", str(ui_without_visual), "--text", "The assigned reviewer is visible after save.",
            "--expected", "The queue shows Jane Reviewer.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(ui_without_visual), "--claim", "C1", "--kind", "test",
            "--label", "Reviewer state unit test", "--expect-output", "reviewer=Jane Reviewer",
            "--observed", "The unit test returned reviewer=Jane Reviewer.", "--proves", "--",
            "node", "-e", "console.log('reviewer=Jane Reviewer')",
        )
        missing_visual_claim = run("validate", "--dir", str(ui_without_visual), expect=1)
        assert "UI-facing change has no visual claim" in missing_visual_claim.stdout
        run(
            "claim", "--dir", str(ui_without_visual), "--text", "The save flow is visible in the real app.",
            "--expected", "A reviewer can see the state before and after save.", "--method", "browser", "--code", "index.js:1"
        )
        run(
            "status", "--dir", str(ui_without_visual), "--claim", "C2", "--status", "not_proven",
            "--observed", "The real app route could not be started in this environment."
        )
        explicit_visual_block = json.loads(run("validate", "--dir", str(ui_without_visual)).stdout)
        assert explicit_visual_block["status"] == "partial", explicit_visual_block

        # Failed and partial runs are plain about what happened.
        failed = root / "failed-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(failed), "--title", "Failed behavior")
        run(
            "claim", "--dir", str(failed), "--text", "Numeric strings return the expected value.",
            "--expected", "The command prints result=5.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(failed), "--claim", "C1", "--kind", "test",
            "--label", "Deliberate failing assertion", "--expect-output", "result=5",
            "--observed", "The command returned result=4.", "--proves", "--",
            "node", "-e", "console.log('result=4')", expect=1,
        )
        run("render", "--dir", str(failed))
        failed_md = (failed / "proof.md").read_text()
        assert "Tested on" in failed_md and "and hit a failure." in failed_md, failed_md
        assert "- The command returned result=4." in failed_md, failed_md

        partial = root / "partial-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(partial), "--title", "Partial behavior")
        run(
            "claim", "--dir", str(partial), "--text", "Concurrent updates preserve the latest reviewer.",
            "--expected", "Two concurrent saves resolve deterministically.", "--method", "test", "--code", "index.js:1"
        )
        run("status", "--dir", str(partial), "--claim", "C1", "--status", "not_proven", "--observed", "Concurrency was not exercised.")
        run("render", "--dir", str(partial))
        partial_md = (partial / "proof.md").read_text()
        assert "Tested on" in partial_md and "but I couldn't check everything." in partial_md, partial_md
        assert "- Concurrency was not exercised." in partial_md, partial_md

        # Full-stack output leads with real media, then causal flow and backend receipt.
        full = root / "full-stack-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(full), "--title", "Reviewer assignment")
        run(
            "claim", "--dir", str(full), "--text", "The assigned reviewer appears in the queue.",
            "--expected", "The queue shows Jane Reviewer after save.", "--method", "browser", "--code", "index.js:1"
        )
        run(
            "claim", "--dir", str(full), "--text", "The selected reviewer is persisted.",
            "--expected", "A fresh read returns reviewerId=reviewer-test.", "--method", "test", "--code", "index.js:1"
        )
        run("review-step", "--dir", str(full), "--text", "The browser saves reviewer-test.", "--code", "index.js:1")
        run("review-step", "--dir", str(full), "--text", "A fresh read returns the same reviewer.", "--code", "index.js:1")
        before = root / "before.png"; before.write_bytes(PNG_1X1)
        after = root / "after.png"; after.write_bytes(PNG_1X1)
        video = root / "demo.webm"; video.write_bytes(b"prove-it-video-fixture")
        run("add", "--dir", str(full), "--claim", "C1", "--type", "screenshot", "--path", str(before), "--label", "Before assignment", "--role", "before", "--observed", "No reviewer is assigned.")
        run("add", "--dir", str(full), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "After assignment", "--role", "after", "--observed", "Jane Reviewer appears in the queue.", "--proves")
        run("add", "--dir", str(full), "--claim", "C1", "--type", "video", "--path", str(video), "--label", "Reviewer assignment flow", "--role", "primary", "--observed", "Saving the assignment updates the queue.")
        run(
            "run", "--dir", str(full), "--claim", "C2", "--kind", "database",
            "--label", "Persisted reviewer", "--expect-output", "reviewerId=reviewer-test",
            "--observed", "A fresh read returned reviewerId=reviewer-test.", "--proves", "--",
            "node", "-e", "console.log('reviewerId=reviewer-test')",
        )
        run("render", "--dir", str(full))
        full_md = (full / "proof.md").read_text()
        assert full_md.index("Tested on") < full_md.index("![](./frontend/reviewer-assignment-flow.webm)"), full_md
        assert full_md.index("![](./frontend/reviewer-assignment-flow.webm)") < full_md.index("| Before | After |"), full_md
        assert "### Demo" not in full_md and "### Backend" not in full_md and "Path I checked" not in full_md, full_md
        assert "- Jane Reviewer appears in the queue." in full_md, full_md
        assert "- A fresh read returned reviewerId=reviewer-test." in full_md, full_md
        assert full_md.index("<details>") < full_md.index("Path: The browser saves reviewer-test → A fresh read returns the same reviewer"), full_md
        for phrase in ("Verified on", "Runtime evidence", "Evidence:", "Freshness:", "> [!", "claims proven"):
            assert phrase not in full_md, full_md
        assert full_md.index("<details>") < full_md.index("result: passed"), full_md
        assert "proof map" not in full_md.casefold(), full_md
        assert "claims proven" not in full_md.casefold(), full_md
        attachments = json.loads((full / "attachments.json").read_text())["files"]
        assert attachments == [
            "frontend/before-assignment.png",
            "frontend/after-assignment.png",
            "frontend/reviewer-assignment-flow.webm",
        ], attachments

        diagram = root / "flow.svg"
        diagram.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>flow</text></svg>')
        bad_diagram = run(
            "add", "--dir", str(full), "--claim", "C2", "--type", "diagram",
            "--path", str(diagram), "--label", "Invalid proof diagram", "--proves", expect=2
        )
        assert "cannot prove runtime behavior" in bad_diagram.stderr

        # Tampering is detected.
        screenshot = full / "frontend" / "after-assignment.png"
        original = screenshot.read_bytes()
        screenshot.write_bytes(original + b"tampered")
        tamper = run("validate", "--dir", str(full), expect=1)
        assert "hash mismatch" in tamper.stdout
        screenshot.write_bytes(original)
        run("validate", "--dir", str(full), "--strict")

        # Publishing creates a dedicated comment and leaves the PR description alone.
        original_pr_body = pr_body_file.read_text()
        published = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Human invoked proof").stdout.strip())
        run(
            "claim", "--dir", str(published), "--text", "The assigned reviewer appears in the queue.",
            "--expected", "The interaction is visible in the comment.", "--method", "browser", "--code", "index.js:1"
        )
        run("add", "--dir", str(published), "--claim", "C1", "--type", "screenshot", "--path", str(before), "--label", "Before reviewer state", "--role", "before", "--observed", "The review is unassigned.")
        run("add", "--dir", str(published), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "After reviewer state", "--role", "after", "--observed", "The assigned reviewer is visible.", "--proves")
        run("add", "--dir", str(published), "--claim", "C1", "--type", "video", "--path", str(video), "--label", "Reviewer assignment flow", "--role", "primary", "--observed", "Assigning the reviewer updates the visible state.")
        publish_stdout = run("publish", "--dir", str(published)).stdout
        result, _ = json.JSONDecoder().raw_decode(publish_stdout)
        assert result["comment_url"].endswith("#issuecomment-9001"), result
        assert not published.exists(), "successful publish should remove its temp directory"
        assert pr_body_file.read_text() == original_pr_body, "publish must not rewrite the PR description"
        comments = read_comments(comments_file)
        assert len(comments) == 1, comments
        comment_body = str(comments[0]["body"])
        assert "### Demo" not in comment_body and "### Before / after" not in comment_body, comment_body
        assert "Tested on" in comment_body and comment_body.index("Tested on") < comment_body.index("github.com/user-attachments/assets/"), comment_body
        assert "| Before | After |" in comment_body, comment_body
        for phrase in ("Verified on", "Runtime evidence", "Evidence:", "Freshness:", "> [!"):
            assert phrase not in comment_body, comment_body
        assert "github.com/user-attachments/assets/" in comment_body, comment_body
        assert "proof map" not in comment_body.casefold(), comment_body
        assert "claims proven" not in comment_body.casefold(), comment_body
        assert "- [x]" not in comment_body.casefold(), comment_body
        assert "### Observed" not in comment_body, comment_body
        assert "./frontend/" not in comment_body, comment_body

        # Each invocation creates another self-contained receipt rather than editing the first.
        second = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Second proof run").stdout.strip())
        run(
            "claim", "--dir", str(second), "--text", "The final state is visible.",
            "--expected", "The screenshot is attached.", "--method", "screenshot", "--code", "index.js:1"
        )
        run("add", "--dir", str(second), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "Final state", "--role", "final", "--observed", "The final state is visible.", "--proves")
        run("publish", "--dir", str(second))
        comments = read_comments(comments_file)
        assert len(comments) == 2, comments
        assert comments[0]["id"] != comments[1]["id"]
        assert "<!-- prove-it:run id=" in str(comments[0]["body"])
        assert "<!-- prove-it:run id=" in str(comments[1]["body"])
        assert str(comments[0]["body"]) != str(comments[1]["body"])
        assert "Human invoked proof" not in str(comments[0]["body"])
        assert "Second proof run" not in str(comments[1]["body"])

        # A later unrelated commit labels point-in-time proof but does not block it.
        point = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Point-in-time proof").stdout.strip())
        run(
            "claim", "--dir", str(point), "--text", "The captured state remains visible.",
            "--expected", "A screenshot from the captured SHA is attached.", "--method", "screenshot", "--code", "index.js:1"
        )
        run("add", "--dir", str(point), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "Captured state", "--role", "final", "--observed", "Captured at the original PR head.", "--proves")
        git(repo, "checkout", "-qb", "future-unrelated")
        (repo / "README.md").write_text("Later unrelated note.\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "add unrelated note")
        future_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        git(repo, "checkout", "-q", "feature")
        os.environ["FAKE_GH_HEAD"] = future_head
        point_result, _ = json.JSONDecoder().raw_decode(run("publish", "--dir", str(point)).stdout)
        assert point_result["relationship"] == "advanced-unrelated", point_result
        point_body = str(read_comments(comments_file)[-1]["body"])
        assert "The PR is now" in point_body, point_body
        assert "None of the files I checked changed afterward." in point_body, point_body
        assert head[:8] in point_body and future_head[:8] in point_body, point_body

        # If the PR advances during upload, the exact newly-created comment is refreshed.
        os.environ["FAKE_GH_HEAD"] = head
        moving = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Moving-head proof").stdout.strip())
        run(
            "claim", "--dir", str(moving), "--text", "The captured state survives a head update.",
            "--expected", "The comment retains the media and names both SHAs.", "--method", "screenshot", "--code", "index.js:1"
        )
        run("add", "--dir", str(moving), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "Moving head state", "--role", "final", "--observed", "Captured before upload began.", "--proves")
        head_file = root / "fake-gh-head.txt"
        head_file.write_text(head)
        os.environ["FAKE_GH_HEAD_FILE"] = str(head_file)
        os.environ["FAKE_GH_HEAD_AFTER_COMMENT"] = future_head
        moving_result, _ = json.JSONDecoder().raw_decode(run("publish", "--dir", str(moving)).stdout)
        assert moving_result["relationship"] == "advanced-unrelated", moving_result
        moving_body = str(read_comments(comments_file)[-1]["body"])
        assert "The PR is now" in moving_body, moving_body
        assert future_head[:8] in moving_body, moving_body
        assert "github.com/user-attachments/assets/" in moving_body, moving_body
        assert "./frontend/" not in moving_body, moving_body
        os.environ.pop("FAKE_GH_HEAD_FILE", None)
        os.environ.pop("FAKE_GH_HEAD_AFTER_COMMENT", None)
        head_file.unlink()
        os.environ["FAKE_GH_HEAD"] = head

        media_pr = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Media proof").stdout.strip())
        media_scenario = root / "pr-scenario.json"
        media_scenario.write_text(json.dumps({"backend": {"tests": {"command": "node -v"}}}))
        write_fake_media(media_pr / "media" / "backend", "backend", [
            {"file": "numbers.png", "title": "Query count", "type": "screenshot", "placement": "inline", "source": "captures/api.json"},
            {"file": "db-state.png", "title": "Row state", "type": "screenshot", "placement": "details", "source": "captures/api.json"},
        ])
        run("media", "--dir", str(media_pr), "--scenario", str(media_scenario), "--reuse", "--proves")
        comments_before = len(read_comments(comments_file))
        dry_body = run("publish", "--dir", str(media_pr), "--dry-run").stdout
        assert "assets/dry-run/numbers.png" in dry_body and len(read_comments(comments_file)) == comments_before, dry_body
        run("publish", "--dir", str(media_pr))
        media_body = str(read_comments(comments_file)[-1]["body"])
        assert "](https://github.com/user-attachments/assets/numbers.png)" in media_body, media_body
        assert "](https://github.com/user-attachments/assets/db-state.png)" in media_body, media_body
        assert "{{media:" not in media_body and "./media/" not in media_body, media_body
        assert "against base `aaaaaaa`" in media_body, media_body

        auto_backend = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Generated backend visual").stdout.strip())
        run(
            "claim", "--dir", str(auto_backend), "--text", "Numeric strings are added numerically.",
            "--expected", "The command prints result=5.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(auto_backend), "--claim", "C1", "--kind", "test",
            "--label", "Numeric string addition", "--expect-output", "result=5",
            "--observed", "The command returned result=5.", "--proves", "--",
            "node", "-e", "console.log('result=5')",
        )
        auto_publish_stdout = run("publish", "--dir", str(auto_backend)).stdout
        auto_publish_result, _ = json.JSONDecoder().raw_decode(auto_publish_stdout)
        assert auto_publish_result["attachments"] == 1, auto_publish_result
        auto_backend_body = str(read_comments(comments_file)[-1]["body"])
        assert "Backend checks" in auto_backend_body, auto_backend_body
        assert "github.com/user-attachments/assets/backend-behavior.png" in auto_backend_body, auto_backend_body
        assert not auto_backend.exists(), "successful backend publish should remove its temp directory"

        (repo / "dirty.tmp").write_text("dirty")
        dirty = run("init", "--repo", str(repo), "--pr", "current", expect=2)
        assert "clean working tree" in dirty.stderr

        local = root / "local-proof"
        run("init", "--repo", str(repo), "--base", "main", "--working-tree", "--out", str(local))
        local_manifest = json.loads((local / "manifest.json").read_text())
        assert local_manifest["target_pr"] is None, local_manifest
        assert local_manifest["capture"]["worktree_clean_at_start"] is False, local_manifest
        assert local_manifest["change"]["dirty"] is True, local_manifest
        dirty_change = next(item for item in local_manifest["change"]["files"] if item["path"] == "dirty.tmp")
        assert dirty_change["working_tree"] is True and dirty_change["untracked"] is True, dirty_change
        run(
            "claim", "--dir", str(local), "--text", "Numeric strings are added before the change is pushed.",
            "--expected", "The local command prints result=5.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(local), "--claim", "C1", "--kind", "test",
            "--label", "Local numeric string addition", "--expect-output", "result=5",
            "--observed", "The local command returned result=5.", "--proves", "--",
            "node", "-e", "console.log('result=5')",
        )
        run("validate", "--dir", str(local))
        run("visualize", "--dir", str(local))
        run("render", "--dir", str(local))
        assert (local / "proof.md").exists()
        assert "Tested local changes on" in (local / "proof.md").read_text()
        assert "Local changes at" in (local / "frontend" / "backend-behavior.svg").read_text()
        local_publish = run("publish", "--dir", str(local), expect=2)
        assert "This is a local proof run" in local_publish.stderr, local_publish.stderr
        assert "Use `render` for local output" in local_publish.stderr, local_publish.stderr
        (repo / "dirty.tmp").unlink()

        missing = root / "missing-visual"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(missing))
        run(
            "claim", "--dir", str(missing), "--text", "The changed interaction is visible.",
            "--expected", "A reviewer can see the interaction.", "--method", "browser"
        )
        run("status", "--dir", str(missing), "--claim", "C1", "--status", "passed", "--observed", "Claimed without media.")
        invalid = run("validate", "--dir", str(missing), expect=1)
        assert "without a screenshot or video" in invalid.stdout

        pin_and_publish_tests(root, repo, head, comments_file)
        classifier_tests(root)
        concurrency_tests(root)
        command_tests(root)
        validator_tests()
        media_tests(root)
        tool_tests(root)

        print("prove-it self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
