#!/usr/bin/env python3
"""Draft a prove-it scenario from the diff. It reads only; it runs no install and no server.

  draft.py --repo . --base REF [--out scenario.json]

Reads `git diff BASE` (committed and uncommitted changes, plus untracked files) and proposes:
  - ui.path from changed Next.js routes (app router and pages router);
  - API handlers from Next.js route.ts / pages/api, FastAPI, Flask, and Express files;
  - backend.tests from changed test files, with the runner of their package;
  - ui.serve from the package.json dev script (or pyproject/manage.py), with {port};
  - ui.setup links for node_modules and ignored .env files;
  - text candidates for expect_text from added JSX text.
Every guess that a human or agent must check is listed in "todo". Do each item, then
remove it. "draft" holds the facts behind the guesses.
"""
import argparse
import json
import os
import re
import subprocess
import sys

PAGE_FILES = ("page.tsx", "page.jsx", "page.ts", "page.js", "page.mdx")
ROUTE_FILES = ("route.ts", "route.js")
CODE_EXT = (".tsx", ".jsx", ".ts", ".js", ".mjs", ".vue", ".svelte")
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)test_[^/]+\.py$|_test\.py$")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
PY_ROUTE_RE = re.compile(r"@\w+\.(get|post|put|patch|delete|route|api_route)\(\s*[rbf]?[\"']([^\"']+)")
JS_ROUTE_RE = re.compile(r"\b(?:app|router|server)\.(get|post|put|patch|delete)\(\s*[\"'`]([^\"'`]+)")
NEXT_METHOD_RE = re.compile(r"export\s+(?:async\s+)?(?:function|const)\s+(" + "|".join(HTTP_METHODS) + r")\b")
PORT_ENV_RE = re.compile(r"\$\{(\w+):-(\d+)\}")
PORT_FLAG_RE = re.compile(r"(--port|-p)[ =](\d+)")
JSX_TEXT_RE = re.compile(r">\s*([^<>{}\n]{3,60}?)\s*<")
ENTITY_RE = re.compile(r"&#?\w+;")
TOAST_RE = re.compile(r"\b(?:toast(?:\.\w+)?|alert|setMessage|setError)\(\s*[\"'`]([^\"'`]{3,60})[\"'`]")
MAX_ROUTES = 8
MAX_TEXTS = 8
MAX_IMPORTERS = 40


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def changed_files(repo, base):
    files = git(repo, "diff", "--name-only", base).splitlines()
    files += git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({f for f in files if f})


def read(repo, rel):
    try:
        with open(os.path.join(repo, rel), errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def package_root(repo, rel):
    """Nearest directory (relative, "" for the root) with a package.json or pyproject.toml above rel."""
    d = os.path.dirname(rel)
    while True:
        for marker in ("package.json", "pyproject.toml"):
            if os.path.isfile(os.path.join(repo, d, marker)):
                return d
        if not d:
            return ""
        d = os.path.dirname(d)


def route_of(segments):
    """Next.js app-router URL for directory segments under app/. None when not routable."""
    out, dynamic = [], False
    for seg in segments:
        if seg.startswith("_") or seg.startswith("@"):
            return None, False
        if seg.startswith("(") and seg.endswith(")"):
            continue
        if seg.startswith("["):
            dynamic = True
        out.append(seg)
    return "/" + "/".join(out), dynamic


def split_app(rel):
    """(package-relative app dir prefix, path parts under app/) or (None, None)."""
    parts = rel.split("/")
    if "app" in parts[:-1]:
        i = parts.index("app")
        return "/".join(parts[:i + 1]), parts[i + 1:]
    return None, None


def app_route_for(repo, rel):
    """Route of the page that owns rel: rel itself, or the nearest page file above it inside app/."""
    app_dir, rest = split_app(rel)
    if app_dir is None:
        return None
    dirs = rest[:-1]
    for n in range(len(dirs), -1, -1):
        here = "/".join([app_dir] + dirs[:n])
        page = next((p for p in PAGE_FILES if os.path.isfile(os.path.join(repo, here, p))), None)
        if page:
            route, dynamic = route_of(dirs[:n])
            if route is None:
                return None
            return {"route": route, "dynamic": dynamic, "page": f"{here}/{page}", "from": rel}
    return None


def pages_route_for(rel):
    parts = rel.split("/")
    if "pages" not in parts:
        return None
    i = parts.index("pages")
    rest = parts[i + 1:]
    if not rest or rest[0] == "api" or rest[-1].startswith("_") or not rest[-1].endswith(CODE_EXT):
        return None
    stem = os.path.splitext(rest[-1])[0]
    segs = rest[:-1] + ([] if stem == "index" else [stem])
    return {"route": "/" + "/".join(segs), "dynamic": any(s.startswith("[") for s in segs), "page": rel, "from": rel}


def api_handlers(repo, rel):
    name = os.path.basename(rel)
    text = read(repo, rel)
    out = []
    if name in ROUTE_FILES:
        app_dir, rest = split_app(rel)
        if app_dir is not None:
            route, _ = route_of(rest[:-1])
            for m in sorted(set(NEXT_METHOD_RE.findall(text))):
                out.append({"method": m, "path": route, "file": rel})
    elif "/pages/api/" in f"/{rel}":
        path = "/api/" + rel.split("pages/api/", 1)[1].rsplit(".", 1)[0]
        out.append({"method": "ANY", "path": path.removesuffix("/index"), "file": rel})
    elif rel.endswith(".py"):
        out += [{"method": m.upper() if m not in ("route", "api_route") else "ANY", "path": p, "file": rel}
                for m, p in PY_ROUTE_RE.findall(text)]
    elif rel.endswith(CODE_EXT):
        out += [{"method": m.upper(), "path": p, "file": rel} for m, p in JS_ROUTE_RE.findall(text)]
    return out


def importing_pages(repo, rel, pkg):
    """Pages under the package app/ or pages/ dirs that import the module rel (one level only)."""
    stem = os.path.splitext(os.path.basename(rel))[0]
    if stem in ("index", "utils", "types", "constants"):
        stem = os.path.basename(os.path.dirname(rel))
    if len(stem) < 4:
        return []
    roots = [p for p in (os.path.join(pkg, "app"), os.path.join(pkg, "src", "app"), os.path.join(pkg, "pages"))
             if os.path.isdir(os.path.join(repo, p))]
    if not roots:
        return []
    hits = git(repo, "grep", "-l", "-F", f"/{stem}", "--", *roots, check=False).splitlines()[:MAX_IMPORTERS]
    routes = []
    for hit in hits:
        r = app_route_for(repo, hit) or pages_route_for(hit)
        if r:
            routes.append({**r, "from": rel})
    return routes


def package_manager(repo):
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun")):
        if os.path.isfile(os.path.join(repo, lock)):
            return pm
    return "npm"


def load_json(repo, rel):
    try:
        return json.loads(read(repo, rel) or "{}")
    except ValueError:
        return {}


def run_script(pm, pkg_dir, pkg_name, script):
    if not pkg_dir:
        return f"{pm} run {script}" if pm == "npm" else f"{pm} {script}"
    if pm == "pnpm":
        return f"pnpm --filter {pkg_name} {script}" if pkg_name else f"pnpm --dir {pkg_dir} {script}"
    if pm == "yarn":
        return f"yarn --cwd {pkg_dir} {script}"
    if pm == "bun":
        return f"bun --cwd {pkg_dir} run {script}"
    return f"npm --prefix {pkg_dir} run {script}"


def js_serve(repo, pkg, todo):
    pkg_json = load_json(repo, os.path.join(pkg, "package.json"))
    scripts = pkg_json.get("scripts") or {}
    script = next((s for s in ("dev", "start:dev", "serve", "start") if s in scripts), None)
    if not script:
        todo.append(f"ui.serve: no dev script in {pkg or '.'}/package.json; write the start command with {{port}}.")
        return None
    body, pm = scripts[script], package_manager(repo)
    base_cmd = run_script(pm, pkg, pkg_json.get("name"), script)
    serve = {"ready_timeout": 180 if "next" in body else 90}
    env_port = PORT_ENV_RE.search(body)
    flag = PORT_FLAG_RE.search(body)
    if env_port:
        serve["cmd"] = base_cmd
        serve["env"] = {env_port.group(1): "{port}"}
    elif flag:
        serve["cmd"] = base_cmd
        todo.append(f"ui.serve.cmd: the {script} script fixes the port ({flag.group(0)}). Base and change need "
                    "two ports; call the framework directly with --port {port}.")
    else:
        extra = " -- --port {port}" if pm == "npm" else " --port {port}"
        serve["cmd"] = base_cmd + extra
        if "vite" in body:
            serve["cmd"] += " --strictPort"
    if "{port}" not in serve["cmd"] and "env" not in serve:
        serve["cmd"] += " --port {port}"
    todo.append(f"ui.serve: guessed from the {script} script in {pkg or '.'}/package.json ({body[:80]}). "
                "Check that it starts one app on {port}, not every workspace app.")
    return serve


def py_serve(repo, pkg, changed, todo):
    pyproject = read(repo, os.path.join(pkg, "pyproject.toml")).lower()
    reqs = read(repo, os.path.join(pkg, "requirements.txt")).lower()
    deps = pyproject + reqs
    if os.path.isfile(os.path.join(repo, pkg, "manage.py")):
        todo.append("ui.serve: Django guessed from manage.py; check settings and the database.")
        return {"cmd": "{python} manage.py runserver 127.0.0.1:{port}", "ready_timeout": 90}
    if "fastapi" in deps or "uvicorn" in deps:
        module = "TODO.module"
        for rel in changed + git(repo, "ls-files", "--", pkg or ".", check=False).splitlines():
            if rel.endswith(".py") and re.search(r"^\s*app\s*=\s*FastAPI\(", read(repo, rel), re.M):
                module = os.path.splitext(os.path.relpath(rel, pkg or "."))[0].replace("/", ".")
                break
        todo.append(f"ui.serve / backend.server: FastAPI guessed; the app object is {module}:app.")
        return {"cmd": f"{{python}} -m uvicorn {module}:app --port {{port}}", "ready_timeout": 60}
    if "flask" in deps:
        todo.append("ui.serve: Flask guessed; set --app to the app module.")
        return {"cmd": "{python} -m flask --app TODO run --port {port}", "ready_timeout": 60}
    return None


def ignored_env_files(repo, pkg):
    out = []
    for d in {"", pkg}:
        full = os.path.join(repo, d)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            rel = os.path.join(d, name) if d else name
            if name.startswith(".env") and not name.endswith((".example", ".sample", ".template")) \
                    and os.path.isfile(os.path.join(repo, rel)) \
                    and subprocess.run(["git", "-C", repo, "check-ignore", "-q", rel]).returncode == 0:
                out.append(rel)
    return out


def test_command(repo, tests, todo):
    js = [t for t in tests if not t.endswith(".py")]
    py = [t for t in tests if t.endswith(".py")]
    if js:
        pkg = package_root(repo, js[0])
        pkg_json = load_json(repo, os.path.join(pkg, "package.json"))
        script = (pkg_json.get("scripts") or {}).get("test", "")
        runner = "vitest" if "vitest" in script or "vitest" in json.dumps(pkg_json.get("devDependencies", {})) \
            else "jest" if "jest" in script else None
        pm = package_manager(repo)
        files = " ".join(os.path.relpath(t, pkg or ".") for t in js if package_root(repo, t) == pkg)
        if runner:
            exec_ = f"pnpm --filter {pkg_json.get('name')} exec" if pm == "pnpm" and pkg and pkg_json.get("name") \
                else f"{pm} exec" if pm != "npm" else "npx"
            cmd = f"{exec_} {runner} run {files}" if runner == "vitest" else f"{exec_} jest {files}"
            if pm != "pnpm" and pkg:
                cmd = f"cd {pkg} && {cmd}"
                todo.append("backend.tests.command: runs in a subshell with cd; check it.")
            return cmd
        todo.append(f"backend.tests.command: no vitest or jest found for {pkg or '.'}; write the test command.")
        return f"TODO test runner for {files}"
    if py:
        deps = read(repo, "pyproject.toml") + read(repo, "requirements-dev.txt") + read(repo, "requirements.txt")
        if "pytest" in deps.lower():
            return "{python} -m pytest -q " + " ".join(py)
        return "{python} -m unittest -v " + " ".join(os.path.splitext(p)[0].replace("/", ".") for p in py)
    return None


def added_texts(repo, base, files):
    """Text from added lines that the base version of the file does not have. Status and toast text first."""
    diff = git(repo, "diff", "-U0", base, "--", *files, check=False) if files else ""
    old = "\n".join(git(repo, "show", f"{base}:{f}", check=False) for f in files)
    first, rest = [], []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for m in JSX_TEXT_RE.findall(line) + TOAST_RE.findall(line):
            t = ENTITY_RE.sub("", m).strip()
            if not t[:1].isalpha() or not t[:1].isupper() or t in old:
                continue
            (first if re.search(r"toast|role=[\"'](status|alert)|aria-live", line, re.I) else rest).append(t)
    return list(dict.fromkeys(first + rest))[:MAX_TEXTS]


def workspace(repo):
    if os.path.isfile(os.path.join(repo, "pnpm-workspace.yaml")):
        return True
    return "workspaces" in load_json(repo, "package.json")


def default_base(repo):
    """Merge base of HEAD with the first default branch that exists."""
    for ref in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).strip():
            mb = git(repo, "merge-base", "HEAD", ref, check=False).strip()
            if mb:
                return mb
    raise SystemExit("No default branch found for the merge base. Pass --base.")


def draft(repo, base=None):
    repo = os.path.abspath(repo)
    repo = git(repo, "rev-parse", "--show-toplevel").strip()
    base = base or default_base(repo)
    base_sha = git(repo, "rev-parse", "--verify", base + "^{commit}").strip()
    ancestor = subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", base_sha, "HEAD"]).returncode == 0
    warnings = []
    if not ancestor:
        mb = git(repo, "merge-base", "HEAD", base_sha, check=False).strip()
        warnings.append(f"base {base} is not an ancestor of HEAD, so the diff includes commits that are not in "
                        f"this change. Use the merge base {mb[:12]} (or omit --base).")
        print("draft: warning: " + warnings[-1], file=sys.stderr)
    files = changed_files(repo, base_sha)
    todo, routes, apis, ui_files = [], [], [], []
    tests = [f for f in files if TEST_RE.search(f)]
    for rel in files:
        if rel in tests:
            continue
        apis += api_handlers(repo, rel)
        r = app_route_for(repo, rel) or pages_route_for(rel)
        if r and os.path.basename(rel) not in ROUTE_FILES:
            routes.append(r)
            ui_files.append(rel)
        elif rel.endswith((".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".html")):
            ui_files.append(rel)
            if not r:
                routes += importing_pages(repo, rel, package_root(repo, rel))
    seen, uniq = set(), []
    for r in routes:
        if r["route"] not in seen:
            seen.add(r["route"])
            uniq.append(r)
    routes = uniq[:MAX_ROUTES]
    ui_pkg = package_root(repo, (routes[0]["page"] if routes else ui_files[0])) if (routes or ui_files) else None
    other_ui = sorted({package_root(repo, f) or "." for f in ui_files} - {ui_pkg or "."})
    if other_ui:
        todo.append(f"ui: covers {ui_pkg or '.'} only. UI files also changed in {', '.join(other_ui)}; "
                    "prove those with their own run (a mobile app needs a simulator, not this scenario).")
    head_subject = git(repo, "log", "-1", "--format=%s").strip()
    dirty = bool(git(repo, "status", "--porcelain").strip())
    scenario = {"name": head_subject if not dirty else f"Working tree on {head_subject}",
                "claim": "TODO: one sentence a reviewer can see, for example 'Clicking Save shows a Saved toast'",
                "refs": {"base": base}}
    todo.append("claim: write the one observable behavior this change adds or fixes.")
    todo += [f"refs.base: {w}" for w in warnings]
    if ui_files:
        ui = {}
        is_js = os.path.isfile(os.path.join(repo, ui_pkg or "", "package.json"))
        html = next((f for f in ui_files if f.endswith(".html")), None)
        if is_js:
            serve = js_serve(repo, ui_pkg, todo)
        else:
            serve = py_serve(repo, ui_pkg, files, todo)
            if not serve and html:
                serve = {"static": os.path.dirname(html) or "."}
                todo.append(f"ui.serve: static files guessed from {html}; the page is served by python http.server.")
                routes = routes or [{"route": "/" if os.path.basename(html) == "index.html"
                                     else "/" + os.path.basename(html), "dynamic": False, "page": html, "from": html}]
        if serve:
            ui["serve"] = serve
        else:
            ui["serve"] = {"cmd": "TODO start command with {port}"}
            todo.append("ui.serve: no dev command found; write one with {port}.")
        if is_js:
            pm = package_manager(repo)
            envs = ignored_env_files(repo, ui_pkg or "")
            lock_changed = any(os.path.basename(f) in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock")
                               for f in files)
            install = {"pnpm": "pnpm install --frozen-lockfile --offline", "yarn": "yarn install --frozen-lockfile",
                       "bun": "bun install --frozen-lockfile"}.get(pm, "npm ci")
            if workspace(repo):
                setup = {"link_from_change": envs, "command": install}
                todo.append("ui.setup: this is a package workspace. Base installs its own node_modules, because "
                            "linked ones point workspace packages at your checkout (base would run change code). "
                            "The worktree cache keeps the install.")
            elif lock_changed:
                setup = {"link_from_change": envs, "command": install.replace(" --offline", "")}
                todo.append("ui.setup: the lockfile changed, so base installs its own dependencies (slow once; "
                            "the worktree cache keeps them).")
            else:
                links = [p for p in ["node_modules"] + ([f"{ui_pkg}/node_modules"] if ui_pkg else [])
                         if os.path.isdir(os.path.join(repo, p))]
                setup = {"link_from_change": links + envs}
                if not links:
                    setup["command"] = install.replace(" --offline", "")
                    todo.append("ui.setup: this checkout has no node_modules, so base installs its own.")
            links = setup["link_from_change"]
            ui["setup"] = setup
            if any(".env" in p for p in links):
                todo.append("ui.setup: .env files are linked from your checkout. Make sure they point at a local "
                            "or test database, never production.")
        if routes:
            ui["path"] = routes[0]["route"]
            if routes[0]["dynamic"]:
                todo.append(f"ui.path: {routes[0]['route']} has a dynamic segment; put a real id from seed data.")
            todo.append(f"ui.path: guessed from {routes[0]['page']} (changed: {routes[0]['from']}).")
        else:
            ui["path"] = "/"
            todo.append("ui.path: no changed route found; set the page that shows the change.")
        texts = added_texts(repo, base_sha, [f for f in ui_files if f.endswith((".tsx", ".jsx", ".vue", ".svelte",
                                                                                ".html"))])
        ui["steps"] = [{"click": {"role": "button", "name": "TODO"}, "label": "TODO"},
                       {"expect_text": texts[0] if texts else "TODO"}]
        todo.append("ui.steps: replace the TODO target and label; add goto/fill/select steps if the flow needs them.")
        todo.append("ui.steps expect_text: " + (f"guessed from added text {texts[0]!r}; check it shows after the "
                                                "flow and not before." if texts else "write the text that proves it."))
        if routes:
            todo.append("ui.auth: if the page needs login, run `scripts/media/auth.py login NAME --url URL` once "
                        "and add \"auth\": {\"name\": \"NAME\"}.")
        scenario["ui"] = ui
    backend = {}
    test_pkg = package_root(repo, next((t for t in tests if package_root(repo, t) == ui_pkg), tests[0])) \
        if tests else None
    own_tests = [t for t in tests if package_root(repo, t) == test_pkg]
    if len(own_tests) < len(tests):
        others = sorted({package_root(repo, t) or "." for t in tests} - {test_pkg or "."})
        todo.append(f"backend.tests: covers {test_pkg or '.'} only; changed tests in {', '.join(others)} need "
                    "their own run.")
    cmd = test_command(repo, own_tests, todo) if own_tests else None
    if cmd:
        backend["tests"] = {"command": cmd, "copy_from_change": own_tests}
        todo.append("backend.tests: runs the changed tests on base (copied in) and on change; expect red then green.")
    if apis and not ui_files:
        serve = py_serve(repo, package_root(repo, apis[0]["file"]), files, todo) \
            if apis[0]["file"].endswith(".py") else None
        if serve:
            backend["server"] = {"command": serve["cmd"], "ready_path": "/", "ready_timeout": serve["ready_timeout"]}
        first = next((a for a in apis if a["method"] in ("GET", "ANY")), apis[0])
        backend["api"] = {"method": "GET" if first["method"] == "ANY" else first["method"], "path": first["path"]}
        todo.append(f"backend.api: guessed {first['method']} {first['path']} from {first['file']}; add body and "
                    "real ids.")
    if backend:
        scenario["backend"] = backend
    scenario["todo"] = todo
    scenario["draft"] = {"base_sha": base_sha[:12], "changed_files": len(files), "routes": routes,
                         "api_handlers": apis[:MAX_ROUTES], "tests": tests,
                         "text_candidates": added_texts(repo, base_sha, [f for f in ui_files if
                                                                         f.endswith((".tsx", ".jsx", ".vue",
                                                                                     ".svelte", ".html"))]),
                         "package": ui_pkg}
    return scenario


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default=None, help="default: merge base of HEAD with the default branch")
    ap.add_argument("--out", default=None)
    o = ap.parse_args()
    s = draft(o.repo, o.base)
    text = json.dumps(s, indent=2)
    if o.out:
        with open(o.out, "w") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
