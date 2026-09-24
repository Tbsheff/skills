"""Process, log, and worktree helpers shared by the UI and backend media tools.

Servers start in their own process group, so stop() also ends the children that
`pnpm dev` or `npm run` start. Output goes to a log file, never to an unread pipe.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

TAIL_LINES = 20
STOP_WAIT_S = 5
SETUP_TIMEOUT_S = 900
DEFAULT_READY_TIMEOUT_S = 60


def install_sigterm():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))


def tail(path, lines=TAIL_LINES):
    try:
        with open(path, errors="replace") as f:
            return "".join(f.readlines()[-lines:]).rstrip()
    except OSError:
        return ""


def start(cmd, cwd, env, log_path):
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    log = open(log_path, "ab")
    try:
        return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    finally:
        log.close()


def stop(proc):
    if proc.poll() is not None:
        return
    for sig, wait in ((signal.SIGTERM, STOP_WAIT_S), (signal.SIGKILL, STOP_WAIT_S)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def safe_rel(rel):
    norm = os.path.normpath(rel)
    return bool(rel) and not os.path.isabs(norm) and not norm.startswith("..")


def prepare_base(tree, change_tree, setup, log_path, env=None):
    """Link or copy listed paths from the change tree, then run setup.command in the base tree.

    Returns [{"path": rel, "action": "link"|"copy"}] for each path it made.
    """
    setup = setup or {}
    made = []
    if is_workspace(change_tree):
        bad = [rel for rel in setup.get("link_from_change", []) if "node_modules" in os.path.normpath(rel).split(os.sep)]
        if bad:
            raise RuntimeError(
                f"setup.link_from_change has {', '.join(bad)}, but this repo is a package workspace. Its node_modules "
                "link workspace packages of your checkout, so base would run change code. Remove the link and set "
                "setup.command, for example `pnpm install --frozen-lockfile --offline`.")
    for key, action in (("link_from_change", "link"), ("copy_from_change", "copy")):
        for rel in setup.get(key, []):
            if not safe_rel(rel):
                raise RuntimeError(f"setup.{key} path must stay inside the repo: {rel}")
            src, dst = os.path.join(change_tree, rel), os.path.join(tree, rel)
            if not os.path.lexists(src) or os.path.lexists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if action == "link":
                os.symlink(os.path.abspath(src), dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True)
            else:
                shutil.copy2(src, dst)
            made.append({"path": os.path.normpath(rel), "action": action})
    command = setup.get("command")
    if not command:
        return made
    cmd = command if isinstance(command, list) else ["/bin/sh", "-c", command]
    with open(log_path, "ab") as log:
        try:
            code = subprocess.run(cmd, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, timeout=setup.get("timeout", SETUP_TIMEOUT_S)).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    if code != 0:
        raise RuntimeError(f"setup in the base worktree failed ({code}). Last lines of {log_path}:\n{tail(log_path)}")
    return made


def is_workspace(tree):
    """True for a pnpm, yarn, or npm workspace root."""
    if os.path.isfile(os.path.join(tree, "pnpm-workspace.yaml")):
        return True
    try:
        with open(os.path.join(tree, "package.json")) as f:
            return "workspaces" in json.load(f)
    except (OSError, ValueError):
        return False


def remove_worktree(repo, path):
    subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", path], capture_output=True)
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(["git", "-C", repo, "worktree", "prune"], capture_output=True)


def wait_url(url, proc, log_path, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"server exited with code {proc.returncode} before {url} answered. "
                               f"Last lines of {log_path}:\n{tail(log_path)}")
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"server did not answer at {url} within {timeout}s. Last lines of {log_path}:\n{tail(log_path)}")
