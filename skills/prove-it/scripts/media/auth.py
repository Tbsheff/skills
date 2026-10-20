#!/usr/bin/env python3
"""Saved login for UI media runs. The state file lives outside every repo.

  auth.py login NAME --url URL [--until-url TEXT | --until-text TEXT] [--timeout 600]
  auth.py list
  auth.py path NAME
  auth.py delete NAME

`login` opens a headed browser at URL. A human logs in. The tool waits until the page
URL contains --until-url, or the page shows --until-text, or (in a terminal) until you
press Enter. Then it saves cookies and storage with `agent-browser state save` to
~/.config/prove-it/auth/NAME.json (directory 700, file 600) and closes the browser.
The tool never reads, prints, or stores the credentials themselves.

A scenario uses the file with "auth": {"name": "NAME"}. See references/scenario.md.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui"))
import house

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
FORBIDDEN_KEYS = {"username", "user", "password", "pass", "token", "cookie", "cookies", "headers", "secret",
                  "credentials", "api_key", "apikey"}
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
POLL_S = 1.0


def auth_dir():
    return os.path.expanduser(os.environ.get("PROVE_IT_AUTH_DIR") or "~/.config/prove-it/auth")


def state_path(name):
    if not NAME_RE.match(name or ""):
        raise SystemExit(f"auth name must match {NAME_RE.pattern}: {name!r}")
    return os.path.join(auth_dir(), f"{name}.json")


def browser(session, *args, headed=False, check=True):
    env = dict(os.environ, AGENT_BROWSER_SESSION=session, AGENT_BROWSER_ENGINE="chrome")
    env.pop("AGENT_BROWSER_STATE", None)
    chrome = house.find_chrome()
    if chrome:
        env["AGENT_BROWSER_EXECUTABLE_PATH"] = chrome
    if headed:
        env["AGENT_BROWSER_HEADED"] = "1"
    r = subprocess.run(["agent-browser", *[str(a) for a in args]], env=env, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"agent-browser {args[0]} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def visible_text_js(text):
    return f"document.body && document.body.innerText.includes({json.dumps(text)})"


def login(name, url, until_url=None, until_text=None, timeout=600):
    path = state_path(name)
    session = f"prove-it-auth-{name}"
    os.makedirs(auth_dir(), mode=0o700, exist_ok=True)
    os.chmod(auth_dir(), 0o700)
    interactive = sys.stdin.isatty()
    if not (until_url or until_text or interactive):
        raise SystemExit("Not a terminal: pass --until-url or --until-text so the tool knows when login is done.")
    try:
        browser(session, "open", url, headed=True)
        print(f"Log in in the browser window. Target: {url}", file=sys.stderr)
        if until_url or until_text:
            deadline = time.time() + timeout
            while True:
                if until_url and until_url in browser(session, "get", "url", check=False):
                    break
                if until_text and browser(session, "eval", visible_text_js(until_text), check=False) == "true":
                    break
                if time.time() > deadline:
                    raise SystemExit(f"Login did not finish within {timeout}s. Nothing was saved.")
                time.sleep(POLL_S)
        else:
            input("Press Enter here after you log in... ")
        fd, tmp = tempfile.mkstemp(dir=auth_dir(), prefix=f".{name}.", suffix=".json")
        os.close(fd)
        os.chmod(tmp, 0o600)
        browser(session, "state", "save", tmp)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        browser(session, "close", check=False)
    print(path)
    return path


def check_perms(path):
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        raise RuntimeError(f"auth state {path} is readable by others (mode {oct(mode)}). Run: chmod 600 {path}")


def resolve(auth, repo):
    """Scenario auth block -> absolute state file path. Refuses credentials and files inside the repo."""
    if not isinstance(auth, dict):
        raise RuntimeError('scenario auth must be an object: {"name": "NAME"} or {"state": "/path/outside/repo.json"}')
    bad = sorted(FORBIDDEN_KEYS & {k.lower() for k in auth})
    if bad:
        raise RuntimeError(f"scenario auth has {', '.join(bad)}. Never put credentials in a scenario. "
                           "Run `auth.py login NAME --url URL` once and use {\"name\": \"NAME\"}.")
    if "name" in auth:
        path = state_path(auth["name"])
    elif "state" in auth:
        path = os.path.abspath(os.path.expanduser(auth["state"]))
    else:
        raise RuntimeError('scenario auth needs "name" or "state"')
    repo_real = os.path.realpath(repo)
    if os.path.commonpath([os.path.realpath(path), repo_real]) == repo_real:
        raise RuntimeError(f"auth state {path} is inside the repo. Keep it outside, for example in {auth_dir()}.")
    if not os.path.isfile(path):
        raise RuntimeError(f"auth state {path} does not exist. Run: auth.py login {auth.get('name', 'NAME')} --url URL")
    check_perms(path)
    return path


def for_origins(path, origins, workdir):
    """A private copy of the state for these run origins.

    Cookies for localhost or 127.0.0.1 are copied to both hosts. localStorage saved for a
    local origin is copied to each run origin, because runs use new ports.
    Returns the copy's path; the caller deletes it with shutil.rmtree(os.path.dirname(copy)).
    """
    with open(path) as f:
        state = json.load(f)
    cookies = []
    for c in state.get("cookies", []):
        cookies.append(c)
        if c.get("domain") in LOCAL_HOSTS:
            for host in LOCAL_HOSTS - {c["domain"]}:
                cookies.append({**c, "domain": host})
    saved = state.get("origins", [])
    local = [o for o in saved if urllib.parse.urlparse(o.get("origin", "")).hostname in LOCAL_HOSTS]
    out_origins = [o for o in saved if o not in local]
    if local:
        merged = {"localStorage": [], "sessionStorage": []}
        for o in local:
            for key in merged:
                merged[key] += o.get(key, [])
        out_origins += [{"origin": origin, **merged} for origin in origins]
    d = tempfile.mkdtemp(prefix="auth-", dir=workdir)
    os.chmod(d, 0o700)
    copy = os.path.join(d, "state.json")
    fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({**state, "cookies": cookies, "origins": out_origins}, f)
    return copy


def discard(copy):
    if copy:
        shutil.rmtree(os.path.dirname(copy), ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login")
    lg.add_argument("name")
    lg.add_argument("--url", required=True)
    lg.add_argument("--until-url", default=None, help="done when the page URL contains this text")
    lg.add_argument("--until-text", default=None, help="done when the page shows this text")
    lg.add_argument("--timeout", type=int, default=600)
    sub.add_parser("list")
    p = sub.add_parser("path")
    p.add_argument("name")
    d = sub.add_parser("delete")
    d.add_argument("name")
    o = ap.parse_args()
    if o.cmd == "login":
        login(o.name, o.url, o.until_url, o.until_text, o.timeout)
    elif o.cmd == "list":
        names = sorted(f[:-5] for f in os.listdir(auth_dir()) if f.endswith(".json")) if os.path.isdir(auth_dir()) else []
        print("\n".join(names))
    elif o.cmd == "path":
        print(state_path(o.name))
    else:
        path = state_path(o.name)
        if os.path.exists(path):
            os.remove(path)
        print(f"deleted {path}")


if __name__ == "__main__":
    main()
