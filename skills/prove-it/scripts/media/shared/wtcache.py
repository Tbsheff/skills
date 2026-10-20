#!/usr/bin/env python3
"""Base worktree cache: keep base checkouts, their installed dependencies, and their dev servers across runs.

  wtcache.py list  [--repo REPO]          entries, their SHA, server, and last use
  wtcache.py stop  [--repo REPO]          stop kept servers, keep the worktrees
  wtcache.py clear [--repo REPO]          stop servers, remove worktrees and cache files

Layout: $PROVE_IT_CACHE_DIR (default ~/.cache/prove-it/worktrees)/<repo-hash>/
  <id>/            a detached `git worktree` of the repo
  <id>.json        sha, lock hash, setup hash, prepared paths, kept server, last use
  <id>.lock        held (flock) while a run uses the entry
  <id>.server.log  output of the kept server
  .lock            held while a run picks, creates, or evicts entries

An entry is reused as is for the same SHA. For a new SHA with the same lockfiles and the
same setup, the entry is moved to the new SHA and keeps its ignored files (node_modules,
.venv, build caches). Only the least recently used entries past the cap are removed.
The user's checkout is never changed; only `git worktree add/remove/prune` touch its .git.
"""
import argparse
import contextlib
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

try:
    import fcntl
except ImportError:
    fcntl = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procs

DEFAULT_CAP = 3
DEFAULT_SERVER_TTL_S = 1800
DEFAULT_SERVER_MAX_AGE_S = 4 * 3600
DEFAULT_KEEP = ("node_modules", ".venv", "venv", ".pnpm-store", ".turbo")
SCHEMA_FILES = {"schema.prisma", "schema.graphql", "openapi.yaml", "openapi.json"}
HEALTH_TIMEOUT_S = 3
LOCKFILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock", "npm-shrinkwrap.json",
    "poetry.lock", "uv.lock", "Pipfile.lock", "pdm.lock", "requirements.txt", "requirements-dev.txt",
    "Gemfile.lock", "go.sum", "Cargo.lock", "composer.lock", "mix.lock",
}
LOCKFILE_MAX_DEPTH = 4


def enabled(scenario=None, flag=False):
    if flag or fcntl is None:
        return False
    if os.environ.get("PROVE_IT_NO_CACHE", "").lower() in {"1", "true", "yes"}:
        return False
    return not (scenario and scenario.get("cache") is False)


def root():
    return os.path.expanduser(os.environ.get("PROVE_IT_CACHE_DIR") or "~/.cache/prove-it/worktrees")


def cap():
    return max(1, int(os.environ.get("PROVE_IT_CACHE_MAX", DEFAULT_CAP)))


def server_ttl():
    return float(os.environ.get("PROVE_IT_SERVER_TTL_S", DEFAULT_SERVER_TTL_S))


def server_max_age():
    return float(os.environ.get("PROVE_IT_SERVER_MAX_AGE_S", DEFAULT_SERVER_MAX_AGE_S))


def keep_dirs(setup):
    return list(DEFAULT_KEEP) + [str(k) for k in (setup or {}).get("keep", [])]


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {r.stderr.strip()}")
    return r.stdout.strip()


def common_dir(repo):
    return os.path.realpath(os.path.join(repo, git(repo, "rev-parse", "--git-common-dir")))


def repo_dir(repo):
    key = hashlib.sha256(common_dir(repo).encode()).hexdigest()[:16]
    return os.path.join(root(), key)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def lock_hash(repo, sha):
    """Hash of every lockfile and schema blob at sha (top LOCKFILE_MAX_DEPTH directory levels).
    A schema change (for example prisma/schema.prisma) gives a new entry, so generated code
    from another schema never carries over."""
    files = [p for p in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
             if (os.path.basename(p) in LOCKFILES | SCHEMA_FILES or p.endswith(".prisma"))
             and p.count("/") < LOCKFILE_MAX_DEPTH]
    blobs = git(repo, "rev-parse", *[f"{sha}:{p}" for p in files]).splitlines() if files else []
    return digest(sorted(zip(files, blobs)))


def setup_hash(setup):
    return digest(setup or {})


@contextlib.contextmanager
def flock(path, blocking=True):
    """Yield True when the lock is held, False when blocking=False and another process holds it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def read_meta(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_meta(path, meta):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(meta, f, indent=2)
    os.replace(tmp, path)


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def url_answers(url, timeout=HEALTH_TIMEOUT_S):
    try:
        urllib.request.urlopen(url, timeout=timeout).read(1)
        return True
    except urllib.error.HTTPError as err:
        return err.code < 500
    except OSError:
        return False


def ps_field(pid, field):
    r = subprocess.run(["ps", "-o", f"{field}=", "-p", str(pid)], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def identity(pid):
    """What makes a PID the same process later: start time, command line, process group."""
    try:
        pgid = os.getpgid(int(pid))
    except (OSError, ValueError, TypeError):
        return None
    return {"pgid": pgid, "start": ps_field(pid, "lstart"), "cmd": ps_field(pid, "command")}


def same_process(server):
    """True only when the recorded PID still is the server this cache started (not a reused PID)."""
    if not server or not pid_alive(server.get("pid")) or not server.get("start"):
        return False
    now = identity(server["pid"])
    return bool(now) and now["start"] == server["start"] and now["cmd"] == server.get("cmd") \
        and now["pgid"] == server.get("pgid") == int(server["pid"])


def stop_server(server):
    """Stop a kept server group. When the PID is not the recorded process any more, do nothing."""
    if not same_process(server):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(int(server["pid"]), sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.time() + procs.STOP_WAIT_S
        while time.time() < deadline and pid_alive(server["pid"]):
            time.sleep(0.1)
        if not pid_alive(server["pid"]):
            return


def is_worktree_of(path, repo):
    if not os.path.isdir(path):
        return False
    r = subprocess.run(["git", "-C", path, "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    return r.returncode == 0 and os.path.realpath(os.path.join(path, r.stdout.strip())) == common_dir(repo)


class Entry:
    """One cached worktree, locked for the life of a run. Use through acquire()."""

    def __init__(self, rdir, eid):
        self.rdir, self.id = rdir, eid
        self.path = os.path.join(rdir, eid)
        self.meta_path = self.path + ".json"
        self.lock_path = self.path + ".lock"
        self.server_log = self.path + ".server.log"
        self.meta = read_meta(self.meta_path) or {}
        self._lock = None

    def save(self):
        self.meta["last_used"] = time.time()
        write_meta(self.meta_path, self.meta)

    def try_lock(self):
        cm = flock(self.lock_path, blocking=False)
        if cm.__enter__():
            self._lock = cm
            return True
        cm.__exit__(None, None, None)
        return False

    def unlock(self):
        if self._lock:
            self._lock.__exit__(None, None, None)
            self._lock = None

    def live_server(self, serve_key, ready_url_for):
        """The kept server when it runs this entry's SHA with the same serve spec and answers; else None."""
        server = self.meta.get("server")
        if not server or server.get("serve") != serve_key or server.get("sha") != self.meta.get("sha"):
            return None
        if time.time() - server.get("started", 0) > server_max_age():
            return None
        if not same_process(server) or not url_answers(ready_url_for(server["port"])):
            return None
        return server

    def keep_server(self, proc, port, serve_key):
        ident = identity(proc.pid) or {}
        self.meta["server"] = {"pid": proc.pid, "port": port, "sha": self.meta.get("sha"), "serve": serve_key,
                               "started": time.time(), "log": self.server_log, **ident}
        self.save()

    def drop_server(self):
        stop_server(self.meta.pop("server", None))
        self.save()


def entries(rdir):
    if not os.path.isdir(rdir):
        return []
    return [Entry(rdir, n[:-5]) for n in sorted(os.listdir(rdir)) if n.endswith(".json") and not n.startswith(".")]


def remove_entry(repo, entry):
    stop_server(entry.meta.get("server"))
    if os.path.isdir(entry.path):
        procs.remove_worktree(repo, entry.path)
    for p in (entry.meta_path, entry.server_log, entry.lock_path):
        with contextlib.suppress(OSError):
            os.remove(p)


def _reset(entry, sha, keep):
    """Tracked files at sha; every untracked and ignored file removed except the dependency dirs in keep."""
    git(entry.path, "checkout", "--force", "--detach", "-q", sha)
    git(entry.path, "reset", "--hard", "-q", sha)
    excludes = [arg for k in keep for arg in ("-e", k)]
    git(entry.path, "clean", "-ffdxq", *excludes)


def _unprepare(entry, change_tree, setup):
    """Remove prepared paths that are copies or links that no longer point at the change tree."""
    keep = []
    for item in entry.meta.get("prepared", []):
        dst = os.path.join(entry.path, item["path"])
        want = os.path.abspath(os.path.join(change_tree, item["path"]))
        if item["action"] == "link" and os.path.islink(dst) and os.readlink(dst) == want \
                and item["path"] in (setup or {}).get("link_from_change", []):
            keep.append(item)
            continue
        if os.path.islink(dst) or os.path.isfile(dst):
            os.remove(dst)
        elif os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
    entry.meta["prepared"] = keep


def acquire(repo, sha, setup, change_tree, log_path, env=None, keep_live=False):
    """Lock and return a cached worktree at sha with setup applied. Call release() when done.

    Every use resets the tree: `git clean -ffdx` except the dependency dirs (DEFAULT_KEEP plus
    setup.keep), then links, copies, and setup.command run again, so generated code matches sha.
    Only a hit whose kept server still runs (keep_live) skips this and keeps that server.
    Returns (entry, status): status is "hit", "moved" (same deps, new SHA), or "new".
    """
    repo = os.path.abspath(repo)
    rdir = repo_dir(repo)
    lhash, shash = lock_hash(repo, sha), setup_hash(setup)
    with flock(os.path.join(rdir, ".lock")):
        chosen, status = None, "new"
        pool = entries(rdir)
        for want in ("hit", "moved"):
            for e in pool:
                m = e.meta
                if m.get("lock_hash") != lhash or m.get("setup_hash") != shash:
                    continue
                if want == "hit" and m.get("sha") != sha:
                    continue
                if not is_worktree_of(e.path, repo):
                    continue
                if e.try_lock():
                    chosen, status = e, want
                    break
            if chosen:
                break
        if chosen is None:
            eid = "pi-" + uuid.uuid4().hex[:10]
            chosen = Entry(rdir, eid)
            chosen.try_lock()
            try:
                git(repo, "worktree", "add", "--detach", "--force", chosen.path, sha)
            except BaseException:
                chosen.unlock()
                remove_entry(repo, chosen)
                raise
            chosen.meta = {"repo": repo, "sha": sha, "lock_hash": lhash, "setup_hash": shash, "ready": False,
                           "created": time.time(), "prepared": []}
            chosen.save()
        _expire_servers(pool, chosen)
        _evict(repo, rdir, chosen)
    _collect_dead_repos(rdir)
    try:
        if status == "moved":
            chosen.drop_server()
            chosen.meta.update(sha=sha, ready=False)
        server = chosen.meta.get("server")
        if status == "hit" and keep_live and same_process(server) and chosen.meta.get("ready"):
            git(chosen.path, "reset", "--hard", "-q", sha)
        else:
            chosen.drop_server()
            _unprepare(chosen, change_tree, setup)
            _reset(chosen, sha, keep_dirs(setup))
            chosen.meta["prepared"] = [p for p in chosen.meta.get("prepared", [])
                                       if os.path.lexists(os.path.join(chosen.path, p["path"]))]
            chosen.meta["ready"] = False
            made = procs.prepare_base(chosen.path, change_tree, setup, log_path, env)
            chosen.meta["prepared"] += [m for m in made if m not in chosen.meta["prepared"]]
        chosen.meta["ready"] = True
        chosen.save()
    except BaseException:
        chosen.meta["ready"] = False
        chosen.save()
        chosen.unlock()
        raise
    return chosen, status


def release(entry):
    entry.save()
    entry.unlock()


def _expire_servers(pool, chosen):
    now = time.time()
    for e in pool:
        if e is chosen or not e.meta.get("server"):
            continue
        old = now - e.meta["server"].get("started", 0) > server_max_age()
        if (old or now - e.meta.get("last_used", 0) > server_ttl()) and e.try_lock():
            try:
                e.drop_server()
            finally:
                e.unlock()


def _evict(repo, rdir, chosen):
    pool = sorted((e for e in entries(rdir) if e.id != chosen.id), key=lambda e: e.meta.get("last_used", 0))
    extra = len(pool) + 1 - cap()
    for e in pool:
        if extra <= 0:
            break
        if e.try_lock():
            try:
                remove_entry(repo, e)
            finally:
                e.unlock()
            extra -= 1
    git(repo, "worktree", "prune", check=False)


def _collect_dead_repos(keep_dir):
    """Remove cache dirs whose repo no longer exists (for example a deleted temp repo)."""
    for rdir in repo_dirs():
        if rdir == keep_dir:
            continue
        pool = entries(rdir)
        repos = {e.meta.get("repo") for e in pool}
        if not pool or any(r and os.path.isdir(r) for r in repos):
            continue
        with flock(os.path.join(rdir, ".lock"), blocking=False) as held:
            if not held:
                continue
            for e in pool:
                stop_server(e.meta.get("server"))
        shutil.rmtree(rdir, ignore_errors=True)


def repo_dirs(repo=None):
    if repo:
        return [repo_dir(os.path.abspath(repo))]
    base = root()
    return [os.path.join(base, d) for d in sorted(os.listdir(base))] if os.path.isdir(base) else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["list", "stop", "clear"])
    ap.add_argument("--repo", default=None, help="only this repo (default: every cached repo)")
    o = ap.parse_args()
    rows = []
    for rdir in repo_dirs(o.repo):
        with flock(os.path.join(rdir, ".lock")):
            for e in entries(rdir):
                repo = e.meta.get("repo") or o.repo
                server = e.meta.get("server")
                alive = same_process(server)
                row = {"id": e.id, "repo": repo, "path": e.path, "sha": (e.meta.get("sha") or "")[:12],
                       "server": f"127.0.0.1:{server['port']} pid {server['pid']}" if alive else None,
                       "last_used": time.strftime("%Y-%m-%d %H:%M", time.localtime(e.meta.get("last_used", 0)))}
                if o.action != "list":
                    if not e.try_lock():
                        row["skipped"] = "in use"
                        rows.append(row)
                        continue
                    try:
                        if o.action == "stop":
                            e.drop_server()
                        else:
                            remove_entry(repo, e)
                    finally:
                        e.unlock()
                    row["done"] = o.action
                rows.append(row)
            if o.action == "clear":
                for repo in {r["repo"] for r in rows if r.get("repo")}:
                    git(repo, "worktree", "prune", check=False)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
