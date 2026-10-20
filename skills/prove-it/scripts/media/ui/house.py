"""UI adapter for the shared house style in tools/shared/house.py.

Every UI artifact is a shared house card: title, BASE and CHANGE SHA pills,
subtitle, body, and a footer with the source file and the capture time.
Still images go inside the card body as <img>. Videos and GIFs use
video_card(): the card is rendered with colored slots, and compose() puts
the clips into the slots with ffmpeg.

This module adds only what the shared module does not have: process
helpers, the in-image step marker for change boxes, and video composition.
"""
import datetime
import importlib.util
import inspect
import os
import shutil
import subprocess
import tempfile
import threading

SHARED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared", "house.py")
_spec = importlib.util.spec_from_file_location("shared_house", SHARED_PATH)
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)

CARD_WIDTH = shared.CARD_WIDTH
BODY_WIDTH = CARD_WIDTH - 48
INK = "#0f172a"
ACCENT = "#f59e0b"
DIM = "#0f172a"
DIM_PERCENT = 50
BOX_RADIUS = 10
BOX_STROKE = 2.5
MARKER_FONT = "Helvetica-Neue-Medium"
MARKER_PT = 13
SLOT_COLORS = ["#ff00ff", "#00ff00"]
SLOT_BLEED = 3
SLOT_FUZZ = "20%"
GIF_FPS = "100/7"

esc = shared.esc
sha_pill = shared.sha_pill
side_label = shared.side_label
find_chrome = shared.find_chrome


def css(v, scale):
    return max(1, int(round(v * scale)))


def js_style():
    return {"accent": ACCENT, "ink": INK}


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd, **kw):
    kw.setdefault("check", True)
    return subprocess.run([str(c) for c in cmd], **kw)


def out(cmd):
    return run(cmd, capture_output=True, text=True).stdout.strip()


def size(img):
    w, h = out(["magick", "identify", "-format", "%w %h", img + "[0]"]).split()
    return int(w), int(h)


def tmpdir():
    return tempfile.mkdtemp(prefix="proveit-ui-")


def cleanup(d):
    shutil.rmtree(d, ignore_errors=True)


def marker(n, path, scale=2):
    """Numbered marker drawn onto an image (change boxes). Same font metrics for every digit."""
    pt, pad = css(MARKER_PT, scale), css(7, scale)
    h = css(MARKER_PT * 0.72, scale) + 2 * pad
    glyph_w = int(out(["magick", "-background", "none", "-font", MARKER_FONT, "-pointsize", pt, "-density", 72,
                       f"label:{n}", "-trim", "-format", "%w", "info:"]))
    w = max(h, glyph_w + 2 * pad)
    run(["magick", "-size", f"{w}x{h}", "xc:none", "-fill", INK, "-draw",
         f"roundrectangle 0,0 {w - 1},{h - 1} {h / 2},{h / 2}", "-fill", "#ffffff", "-font", MARKER_FONT,
         "-pointsize", pt, "-density", 72, "-annotate", f"+{(w - glyph_w) // 2}+{h - pad}", str(n), path])
    return path


def img_tag(path, alt):
    return f'<img src="file://{os.path.abspath(path)}" alt="{esc(alt)}">'


def num(n):
    return f'<span class="num">{esc(n)}</span>'


UI_CSS = """
.shot { display:block; width:100%; border:1px solid var(--line); border-radius:8px; }
.tiles { display:grid; gap:14px 12px; align-items:start; }
.tile .cap { display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); margin:0 0 6px; }
.tile .cap b { color:var(--ink); font-weight:600; }
.num { display:inline-grid; place-items:center; min-width:20px; height:20px; padding:0 6px; border-radius:999px;
  background:var(--ink); color:#fff; font:600 11px/1 var(--sans); }
.tile img { display:block; width:100%; border:1px solid var(--line); border-radius:8px; }
.legend { display:flex; flex-wrap:wrap; gap:6px 18px; margin-top:10px; font-size:12.5px; }
.legend span { display:inline-flex; align-items:center; gap:7px; }
.slot-head { display:flex; justify-content:space-between; align-items:center; margin:0 0 6px;
  font-size:12px; color:var(--muted); }
.slot-head > span { display:inline-flex; align-items:center; gap:6px; }
.slot { display:block; border-radius:0; }
"""


def _css_kwarg():
    """Name of the shared card() parameter for extra CSS (it moved while the module was new)."""
    params = inspect.signature(shared.card).parameters
    return next(k for k in ("extra_css", "css_extra", "css") if k in params)


close_cards = shared.close_kept


def card_png(path, title, subtitle, body, base, change, source, captured_at, scale=2, css_extra=""):
    """Render one house card to PNG (width = 800 * scale).

    The card HTML is kept in $PROVE_CARD_DIR (default: next to the PNG).
    """
    page = shared.card(title, subtitle, body, base=base, change=change, source=source,
                       captured_at=captured_at, **{_css_kwarg(): UI_CSS + css_extra})
    html_dir = os.environ.get("PROVE_CARD_DIR") or os.path.dirname(os.path.abspath(path))
    os.makedirs(html_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem == "card":
        stem = os.path.basename(os.path.dirname(os.path.abspath(path)))
    html_path = os.path.join(html_dir, stem + ".card.html")
    shared.write_and_shoot([(page, html_path, path)], session=f"ui-card-{os.getpid()}-{threading.get_ident()}",
                           keep=True)
    if scale != shared.SCALE:
        run(["magick", path, "-resize", f"{scale / shared.SCALE * 100:.4f}%", path])
    return path


def video_card(path, title, subtitle, slots, base, change, source, captured_at, scale=2, row=False):
    """Render a card with one colored slot per clip. slots: [(head_html, w, h[, css_width])].

    w/h give the aspect; css_width (default: full body width) lets panes share one scale.
    row=True puts the slots side by side instead of stacked.
    Returns the slot rectangles in PNG pixels: [(x, y, w, h)], even sizes.
    """
    cells = []
    for i, (head, w, h, *rest) in enumerate(slots):
        width = min(BODY_WIDTH, rest[0]) if rest else BODY_WIDTH
        height = round(width * h / w)
        head_html = f'<div class="slot-head">{head}</div>' if head else ""
        cells.append(f'<div>{head_html}<div class="slot" style="width:{width}px;height:{height}px;'
                     f'background:{SLOT_COLORS[i]}"></div></div>')
    layout = "display:flex;gap:12px;align-items:flex-start" if row else "display:grid;gap:14px"
    body = f'<div style="{layout}">{"".join(cells)}</div>'
    card_png(path, title, subtitle, body, base, change, source, captured_at, scale)
    rects = []
    for color in SLOT_COLORS[:len(slots)]:
        geom = out(["magick", path, "-fuzz", SLOT_FUZZ, "-fill", "black", "+opaque", color, "-fill", "white",
                    "-opaque", color, "-format", "%@", "info:"])
        w, h, x, y = (int(v) for v in geom.replace("x", "+").split("+"))
        x, y, w, h = x - SLOT_BLEED, y - SLOT_BLEED, w + 2 * SLOT_BLEED, h + 2 * SLOT_BLEED
        rects.append((x, y, w + w % 2, h + h % 2))
    return rects


def compose(card, rects, clips, out_path, gif=False, fps=30):
    """Place each clip (scaled to its slot) on the card; stop with the shortest clip."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", 1, "-framerate", fps, "-i", card]
    for c in clips:
        cmd += ["-i", c]
    graph, cur = ["[0]format=rgb24,setsar=1[bg0]"], "bg0"
    for i, (x, y, w, h) in enumerate(rects):
        graph.append(f"[{i + 1}:v]fps={fps},scale={w}:{h}:flags=lanczos,setsar=1[c{i}]")
        graph.append(f"[{cur}][c{i}]overlay={x}:{y}:shortest=1[bg{i + 1}]")
        cur = f"bg{i + 1}"
    if gif:
        graph.append(f"[{cur}]split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];"
                     "[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
        run(cmd + ["-filter_complex", ";".join(graph), "-loop", 0, out_path])
    else:
        graph.append(f"[{cur}]pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p[out]")
        run(cmd + ["-filter_complex", ";".join(graph), "-map", "[out]", "-c:v", "libx264", "-crf", 20,
                   "-preset", "slow", "-movflags", "+faststart", out_path])
    return out_path
