"""House style for prove-it proof cards. Stdlib only.

    import sys; sys.path.insert(0, "tools/shared")
    import house

    html = house.card(
        "API response: base vs change",
        "One request sent to each commit.",           # subtitle, HTML allowed
        "<div>...</div>",                              # body, HTML
        base="f6bf56c", change="9b4b434",             # both SHAs are stamped
        source="captures/api.json",                    # file the card was rendered from
        captured_at="2026-09-24T06:03:17Z",
        extra_css=".extra { color: red; }",            # optional card-specific CSS
    )
    house.write_and_shoot([(html, "media/x.html", "media/x.png")])

See tools/shared/README.md for the full contract.
"""
import atexit
import html as _html
import os
import platform
import shutil
import subprocess
import threading

CARD_WIDTH = 800
SCALE = 2
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "house.css")

CHROME_CANDIDATES = {
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ],
    "Linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"],
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ],
}


def esc(value):
    return _html.escape(str(value), quote=True)


def pill(kind, text):
    """kind: base | change | add | del | chg | neutral."""
    return f'<span class="pill {kind}">{esc(text)}</span>'


def sha_pill(side, sha):
    """The one label style for a commit: BASE abc1234 / CHANGE def5678."""
    return f'<span class="pill {side}">{side.upper()} <span class="sha">{esc(sha)}</span></span>'


def side_label(side, sha):
    """Quiet in-panel label for a side (the loud pills live in the card head only)."""
    return f'<span class="side {side}">{side} <span class="sha">{esc(sha)}</span></span>'


def css():
    with open(CSS_PATH) as f:
        return f.read()


def card(title, subtitle, body, *, base, change, source, captured_at, extra_css="", width=CARD_WIDTH):
    """Return a full HTML page for one card. `base`/`change` are short SHAs (change may end in +dirty)."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>{css()}{extra_css} :root {{ --card-width: {width}px; }}</style></head>
<body><div class="house-card">
<div class="house-head"><h1>{esc(title)}</h1><div class="pills">{sha_pill('base', base)}{sha_pill('change', change)}</div></div>
<p class="house-sub">{subtitle}</p>
{body}
<div class="house-foot"><span>from <code>{esc(source)}</code> · captured {esc(captured_at)}</span>
<span class="stamp">base {esc(base)} → change {esc(change)}</span></div>
</div></body></html>"""


def find_chrome():
    """AGENT_BROWSER_EXECUTABLE_PATH wins; otherwise look in the usual places for this OS."""
    env = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH")
    if env:
        return env
    for candidate in CHROME_CANDIDATES.get(platform.system(), []):
        path = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if path and os.path.exists(path):
            return path
    return None


def _browser(session, *args, check=True):
    env = dict(os.environ, AGENT_BROWSER_SESSION=session, AGENT_BROWSER_ENGINE="chrome")
    chrome = find_chrome()
    if chrome:
        env["AGENT_BROWSER_EXECUTABLE_PATH"] = chrome
    proc = subprocess.run(["agent-browser", *args], capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"agent-browser {' '.join(args)} failed: {proc.stdout}{proc.stderr}")
    return proc


_KEPT = {}
_KEPT_LOCK = threading.Lock()


def screenshot(pairs, session=None, width=CARD_WIDTH, scale=SCALE, keep=False):
    """Screenshot [(html_path, png_path)] at `scale`x. Output PNG width = width * scale.

    Uses `agent-browser set viewport W H SCALE` (agent-browser >= 0.38). Older builds get
    CSS zoom in a W*SCALE viewport instead, which gives the same pixel size.
    keep=True leaves the browser open for the next call with the same session;
    close_kept() closes every kept session.
    """
    session = session or f"house-{os.getpid()}-{threading.get_ident()}"
    done = []
    try:
        native = _KEPT.get(session)
        for html_path, png_path in pairs:
            html_path = os.path.abspath(html_path)
            if native is None:
                _browser(session, "open", "file://" + html_path)
                native = _browser(session, "set", "viewport", str(width), "200", str(scale), check=False).returncode == 0
                if not native:
                    _browser(session, "set", "viewport", str(width * scale), "200")
                if keep:
                    with _KEPT_LOCK:
                        _KEPT[session] = native
            _browser(session, "open", "file://" + html_path)
            if not native:
                _browser(session, "eval", f"document.documentElement.style.zoom = '{scale}'")
            _browser(session, "wait", "120")
            _browser(session, "screenshot", "--full", os.path.abspath(png_path))
            done.append(png_path)
    except BaseException:
        keep = False
        with _KEPT_LOCK:
            _KEPT.pop(session, None)
        raise
    finally:
        if not keep:
            _browser(session, "close", check=False)
    return done


def close_kept():
    with _KEPT_LOCK:
        names = list(_KEPT)
        _KEPT.clear()
    for session in names:
        _browser(session, "close", check=False)


atexit.register(close_kept)


def write_and_shoot(items, session=None, keep=False):
    """items: [(html_string, html_path, png_path)]. Writes each HTML file, then screenshots all."""
    for html_string, html_path, _ in items:
        os.makedirs(os.path.dirname(os.path.abspath(html_path)), exist_ok=True)
        with open(html_path, "w") as f:
            f.write(html_string)
    return screenshot([(h, p) for _, h, p in items], session=session, keep=keep)
