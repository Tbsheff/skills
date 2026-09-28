"""Thin agent-browser wrapper with the environment fixes prove-it needs.

- AGENT_BROWSER_ENGINE is forced to chrome (a shell may export lightpanda).
- AGENT_BROWSER_EXECUTABLE_PATH wins; else the shared house finds Chrome for this OS.
- `open` runs before `set viewport` (older builds need that order).
- Viewport scale is the deviceScaleFactor: `set viewport W H 2` gives 2x pixels.
- use(session, state) sets the session name (and an auth state file) for the current
  thread, so base and change can run in two browsers at the same time.
- An auth state is loaded with `state load` on about:blank before the first page.
"""
import contextlib
import threading
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house

HERE = os.path.dirname(os.path.abspath(__file__))
_local = threading.local()


def default_session():
    return os.environ.get("AGENT_BROWSER_SESSION") or f"proveit-ui-{os.getpid()}"


@contextlib.contextmanager
def use(session, state=None):
    old = getattr(_local, "session", None), getattr(_local, "state", None)
    _local.session, _local.state = session, state
    try:
        yield
    finally:
        _local.session, _local.state = old


def env():
    e = dict(os.environ)
    e["AGENT_BROWSER_ENGINE"] = "chrome"
    e["AGENT_BROWSER_SESSION"] = getattr(_local, "session", None) or default_session()
    e.pop("AGENT_BROWSER_STATE", None)
    chrome = house.find_chrome()
    if chrome:
        e["AGENT_BROWSER_EXECUTABLE_PATH"] = chrome
    return e


def ab(*args, capture=True, secret=False):
    """Run one agent-browser command. secret=True keeps the arguments and output out of the error."""
    r = subprocess.run(["agent-browser", *[str(a) for a in args]], env=env(),
                       capture_output=capture, text=True)
    if r.returncode != 0:
        if secret:
            raise RuntimeError(f"agent-browser {args[0]} failed (arguments and output hidden)")
        raise RuntimeError(f"agent-browser {' '.join(map(str, args))} failed:\n{r.stdout}{r.stderr}")
    return (r.stdout or "").strip()


_loaded = set()


def load_state_once():
    """Load the thread's auth state into its session before the first real page.
    AGENT_BROWSER_STATE at launch reloads the first page to apply storage, which drops
    injected scripts; `state load` on about:blank does not."""
    session, state = getattr(_local, "session", None) or default_session(), getattr(_local, "state", None)
    if state and (session, state) not in _loaded:
        ab("open", "about:blank")
        ab("state", "load", state)
        _loaded.add((session, state))


def open_page(url, vw=1280, vh=800, scale=2, settle_ms=350):
    load_state_once()
    ab("open", url)
    ab("set", "viewport", vw, vh, scale)
    ab("eval", "document.fonts && document.fonts.ready.then(function(){return 1})")
    ab("wait", settle_ms)


def screenshot(path):
    ab("screenshot", os.path.abspath(path))
    return path


def eval_js(code):
    return ab("eval", code)


def box(selector):
    """Element box in CSS px: dict with x, y, width, height."""
    data = json.loads(ab("get", "box", selector, "--json"))["data"]
    return {k: float(data[k]) for k in ("x", "y", "width", "height")}


def inject_cursor(style):
    code = open(os.path.join(HERE, "cursor.js")).read()
    ab("eval", code)
    ab("eval", f"window.__proveit.setStyle({json.dumps(style)})")


VISIBLE_TEXT_JS = """(function (t) {
  function shown(e) {
    for (var n = e; n && n !== document.documentElement; n = n.parentElement) {
      var s = getComputedStyle(n);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
    }
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  return Array.prototype.some.call(document.querySelectorAll('body *'), function (e) {
    if (!e.textContent.includes(t)) return false;
    if (Array.prototype.some.call(e.children, function (c) { return c.textContent.includes(t); })) return false;
    return shown(e);
  });
})(%s)"""


def has_visible_text(text):
    return eval_js(VISIBLE_TEXT_JS % json.dumps(text)).strip() == "true"


def blur(selectors):
    """Blur elements that may show private data, before a screenshot or a recording."""
    if selectors:
        css = json.dumps(",".join(selectors) + "{filter:blur(8px) !important;}")
        eval_js("(function(){var s=document.getElementById('__proveit_blur')||document.createElement('style');"
                f"s.id='__proveit_blur';s.textContent={css};document.documentElement.appendChild(s);return true;}})()")


def close():
    session = getattr(_local, "session", None) or default_session()
    for key in [k for k in _loaded if k[0] == session]:
        _loaded.discard(key)
    try:
        ab("close")
    except RuntimeError:
        pass


def sleep_ms(ms):
    time.sleep(ms / 1000)
