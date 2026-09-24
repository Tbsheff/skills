"""Scenario file + base/change checkout and server runner.

A scenario (JSON) names the repo, the git refs to compare, how to serve a
checkout, and what to click or measure. See references/scenario.md.
A ref of null means the working tree of the repo itself (no worktree).

    with Checkouts(load("app/prove-scenario.json"), "work/ui/wt") as co:
        co.url("base")            # http://127.0.0.1:PORT/ served from a worktree of refs.base
        co.sha("change")          # short SHA from git rev-parse

"serve" is either {"static": "<dir inside the checkout>"} (python http.server)
or {"cmd": "npm run dev -- --port {port}", "ready_path": "/"} (any dev server;
{port} is filled in, the command runs inside the checkout).

Base-side worktrees come from the worktree cache (../shared/wtcache.py) unless the
cache is off. With serve.keep (or PROVE_IT_KEEP_SERVERS=1), a base server started from
a cached worktree stays up after the run and the next run for the same SHA reuses it.
"origin_repo" (set by prove.py for `init --pin`) is the user's checkout: links and copies
come from it, and the pinned change tree gets the same setup as base.
"reuse_url" points the change side at a server that the user already runs.
"""
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
import procs
import wtcache

REUSE_CHECK_TIMEOUT_S = 5


def load(path):
    path = os.path.abspath(path)
    with open(path) as f:
        s = json.load(f)
    s["_file"] = path
    s["_dir"] = os.path.dirname(path)
    s["repo"] = os.path.normpath(os.path.join(s["_dir"], s.get("repo", ".")))
    return s


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout.strip()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve_key(s):
    serve = s.get("serve", {"static": "."})
    return wtcache.digest({"serve": serve, "python": s.get("python")})


def fetch(url, timeout=REUSE_CHECK_TIMEOUT_S):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read(2_000_000).decode(errors="replace")


def reuse_urls(s):
    value = s.get("reuse_url")
    if not value:
        return {}
    return {"change": value} if isinstance(value, str) else dict(value)


class Checkouts:
    """One checkout and one server per ref name in scenario["refs"].

    A null ref serves the working tree. Other refs get a cached worktree (or, with the
    cache off, a temporary one) with scenario["setup"] applied before their server starts.
    Every exit path stops the servers this run owns, releases cache locks, and removes
    temporary worktrees. Kept base servers stay up for the next run.
    """

    def __init__(self, scenario, workdir, names=None, cache=True, keep_servers=None):
        self.s = scenario
        self.workdir = os.path.abspath(workdir)
        self.names = names or list(scenario["refs"])
        self.cache = cache and wtcache.enabled(scenario)
        keep = os.environ.get("PROVE_IT_KEEP_SERVERS", "").lower() in {"1", "true", "yes"} \
            or (scenario.get("serve") or {}).get("keep") is True
        self.keep_servers = self.cache and keep if keep_servers is None else keep_servers
        self.source = scenario.get("origin_repo") or scenario["repo"]
        self.host = scenario.get("host", "127.0.0.1")
        self.procs, self.ports, self.paths, self.shas, self.logs = {}, {}, {}, {}, {}
        self.entries, self.status, self.base_urls, self.caveats = {}, {}, {}, []
        self.kept_names = set()
        self.timings = {}

    def __enter__(self):
        try:
            self._start()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _start(self):
        os.makedirs(self.workdir, exist_ok=True)
        repo = self.s["repo"]
        reuse = reuse_urls(self.s)
        order = sorted(self.names, key=lambda n: self.s["refs"][n] is not None)
        for name in order:
            t = time.monotonic()
            ref = self.s["refs"][name]
            if ref is None:
                full = git(repo, "rev-parse", "HEAD")
                dirty = bool(git(repo, "status", "--porcelain"))
                self.shas[name] = git(repo, "rev-parse", "--short", full) + ("+dirty" if dirty else "")
                self.paths[name] = repo
                if os.path.realpath(self.source) != os.path.realpath(repo):
                    procs.prepare_base(repo, self.source, self.s.get("setup"), self.log_path(name, "setup"))
            else:
                full = git(repo, "rev-parse", ref + "^{commit}")
                self.shas[name] = git(repo, "rev-parse", "--short", full)
                self._checkout(name, full)
            if name in reuse and self._use_reuse_url(name, reuse[name], full):
                self.status[name] = "reuse_url"
            elif not self._reuse_kept(name):
                self._serve(name)
            self.timings[f"checkout_{name}_s"] = round(time.monotonic() - t, 2)
        timeout = self.s.get("serve", {}).get("ready_timeout", procs.DEFAULT_READY_TIMEOUT_S)
        t = time.monotonic()
        for name in self.names:
            if self.procs.get(name) is not None:
                procs.wait_url(self.ready_url(name), self.procs[name], self.logs[name], timeout)
                if name in self.entries and self.keep_servers:
                    self.entries[name].keep_server(self.procs[name], self.ports[name], serve_key(self.s))
                    self.kept_names.add(name)
        self.timings["servers_ready_s"] = round(time.monotonic() - t, 2)

    def _checkout(self, name, full):
        repo = self.s["repo"]
        setup_log = self.log_path(name, "setup")
        if self.cache:
            entry, status = wtcache.acquire(repo, full, self.s.get("setup"), self.source, setup_log,
                                            keep_live=self.keep_servers)
            self.entries[name], self.status[name] = entry, f"cache_{status}"
            self.paths[name] = entry.path
            return
        path = os.path.join(self.workdir, name)
        if os.path.exists(path):
            procs.remove_worktree(repo, path)
        self.paths[name] = path
        git(repo, "worktree", "add", "--detach", "--force", path, full)
        self.status[name] = "temp"
        procs.prepare_base(path, self.source, self.s.get("setup"), setup_log)

    def _reuse_kept(self, name):
        entry = self.entries.get(name)
        if not entry or not self.keep_servers:
            return False
        server = entry.live_server(serve_key(self.s), lambda port: self._ready_at(port))
        if not server:
            if entry.meta.get("server"):
                entry.drop_server()
            return False
        self.ports[name], self.procs[name], self.logs[name] = server["port"], None, server.get("log")
        self.status[name] += "+server_reused"
        self.kept_names.add(name)
        return True

    def _use_reuse_url(self, name, url, full_sha):
        """Use a server the user runs. Check it with reuse_check when given; else accept with a caveat."""
        url = url.rstrip("/")
        check = self.s.get("reuse_check")
        if not wtcache.url_answers(url + (check or {}).get("path", self.s.get("path", "/")), REUSE_CHECK_TIMEOUT_S):
            self.caveats.append(f"reuse_url {url} did not answer; the tool started its own server.")
            return False
        if check:
            marker = str(check.get("marker", "{short_sha}")).format(sha=full_sha, short_sha=full_sha[:7])
            try:
                body = fetch(url + check.get("path", "/"))
            except OSError:
                body = ""
            if marker not in body:
                self.caveats.append(f"reuse_url {url} did not show {marker!r} at {check.get('path', '/')}; "
                                    "the tool started its own server.")
                return False
        else:
            self.caveats.append(f"The {name} side used the server at {url} that you run. "
                                "The tool did not check that it serves this commit.")
        self.base_urls[name] = url
        self.procs[name] = None
        return True

    def log_path(self, name, what="server"):
        return os.path.join(self.workdir, f"{what}-{name}.log")

    def _serve(self, name):
        path = self.paths[name]
        port = free_port()
        serve = self.s.get("serve", {"static": "."})
        python = self.s.get("python") or sys.executable
        env = dict(os.environ, PORT=str(port))
        env.update({k: str(v).format(port=port, python=python) for k, v in serve.get("env", {}).items()})
        if "cmd" in serve:
            cmd = shlex.split(serve["cmd"].format(port=port, python=python))
            cwd = path
        else:
            cmd = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
            cwd = os.path.join(path, serve.get("static", "."))
        entry = self.entries.get(name)
        self.logs[name] = entry.server_log if entry and self.keep_servers else self.log_path(name)
        self.ports[name] = port
        self.procs[name] = procs.start(cmd, cwd, env, self.logs[name])

    def origin(self, name):
        return self.base_urls.get(name) or f"http://{self.host}:{self.ports[name]}"

    def url(self, name, query=None):
        path = self.s.get("path", "/")
        q = f"?{query}" if query else ""
        return f"{self.origin(name)}{path}{q}"

    def _ready_at(self, port):
        ready = self.s.get("serve", {}).get("ready_path") or self.s.get("path", "/")
        return f"http://127.0.0.1:{port}{ready}"

    def ready_url(self, name):
        ready = self.s.get("serve", {}).get("ready_path")
        return f"{self.origin(name)}{ready}" if ready else self.url(name)

    def sha(self, name):
        return self.shas[name]

    def kept(self, name):
        return name in self.kept_names

    def __exit__(self, *exc):
        for name, proc in self.procs.items():
            if proc is not None and not self.kept(name):
                procs.stop(proc)
        for name, entry in self.entries.items():
            if not self.kept(name) and entry.meta.get("server"):
                entry.drop_server()
            wtcache.release(entry)
        for name, path in self.paths.items():
            if path != self.s["repo"] and name not in self.entries:
                procs.remove_worktree(self.s["repo"], path)
        subprocess.run(["git", "-C", self.s["repo"], "worktree", "prune"], capture_output=True)
        return False
