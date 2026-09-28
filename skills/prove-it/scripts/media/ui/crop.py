#!/usr/bin/env python3
"""Crop to the change: one crop box for every image or frame of a claim.

  crop.py geom BASE.png OTHER.png [MORE.png ...] [--pad 40] [--aspect 4:3-16:9]
          [--min 640x400] [--scale 2]            -> prints WxH+X+Y
  crop.py video-geom RAW.mp4 [--every 3] [same options]  -> prints WxH+X+Y
  crop.py content A.png [B.png ...]                          -> prints WxH+X+Y (non-background area)
  crop.py apply WxH+X+Y IN.png OUT.png [IN2.png OUT2.png ...]

The box is the union of pixel-diff boxes against BASE (magick compare + %@),
then padded with context, grown to a minimum size and an aspect ratio,
moved outward until no edge cuts through content, and rounded to 8 px.
All size options are CSS px; --scale converts them to image pixels.
"""
import argparse
import concurrent.futures
import functools
import json
import os
import re
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house

DIFF_FUZZ = "4%"
VIDEO_DIFF_FUZZ = "10%"
VIDEO_WARMUP_S = 0.3
EDGE_PROBE_WIDTH = 640
EDGE_TRANSITION_DELTA = 6
EDGE_MAX_TRANSITIONS = 4
ROUND_TO = 8
BG_TOLERANCE = 3
ROW_GAP_CSS = 14
KEEP_WHOLE_AXIS = 0.95
ROW_BG_REACH_CSS = 96
BG_MAX_OFF_RATIO = 0.02
DIFF_WORKERS = 8
DIFF_WIDTH = 800
_UNION = {}
_UNION_LOCK = threading.Lock()


@functools.lru_cache(maxsize=256)
def _size(path):
    return house.size(path)


def diff_bbox(a, b, fuzz=DIFF_FUZZ):
    """Bounding box (x0, y0, x1, y1) of pixels that differ between a and b, or None."""
    geom = house.out(["magick", a, b, "-compose", "difference", "-composite", "-colorspace", "gray",
                      "-threshold", fuzz, "-bordercolor", "black", "-border", 1, "-format", "%@", "info:"])
    m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geom)
    if not m:
        return None
    w, h, x, y = map(int, m.groups())
    if w == 0 or h == 0:
        return None
    iw, ih = _size(a)
    return (max(0, x - 1), max(0, y - 1), min(iw, x - 1 + w), min(ih, y - 1 + h))


def diff_union(base, others, fuzz=DIFF_FUZZ):
    """Union of diff_bbox(base, o) for every o, computed in parallel."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=DIFF_WORKERS) as pool:
        return union(list(pool.map(lambda o: diff_bbox(base, o, fuzz), others)))


def union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _gray(img, width):
    iw, ih = house.size(img)
    f = width / iw
    h = max(1, round(ih * f))
    raw = house.run(["magick", img, "-resize", f"{width}x{h}!", "-colorspace", "gray", "-depth", 8,
                     "gray:-"], capture_output=True).stdout
    return raw, width, h, f


def _line(raw, w, pos, lo, hi, vertical):
    return [raw[i * w + pos] if vertical else raw[pos * w + i] for i in range(lo, hi)]


def _is_calm(values):
    transitions = sum(1 for a, b in zip(values, values[1:]) if abs(a - b) > EDGE_TRANSITION_DELTA)
    return transitions <= EDGE_MAX_TRANSITIONS


def _is_page_background(values, bg):
    off = sum(1 for v in values if abs(v - bg) > BG_TOLERANCE)
    return off <= len(values) * BG_MAX_OFF_RATIO


def _page_background(raw, w, h):
    """Most common gray value on the left, right and bottom image edges."""
    edge = [raw[y * w] for y in range(h)] + [raw[y * w + w - 1] for y in range(h)] + \
        list(raw[(h - 1) * w:h * w])
    return max(set(edge), key=edge.count)


def _walk_gap(start, stop, test, gap):
    """Middle of the first run of `gap` passing lines from start toward stop, else None."""
    step = 1 if stop >= start else -1
    run = 0
    for p in range(start, stop + step, step):
        run = run + 1 if test(p) else 0
        if run >= gap:
            return p - step * (gap // 2)
    return None


def snap_calm_edges(box, ref, max_css=120, scale=2, side_reach_css=320, row_bg_reach_css=None):
    """Move each edge outward so it does not cut through content.

    Left and right edges: first the nearest column of plain page background
    within side_reach_css (a crop must not slice a card or a form field in
    half), then the nearest calm column within max_css.
    Top and bottom edges: a page-background row if one is within
    ROW_BG_REACH_CSS (keeps a nearby card edge whole), else the nearest calm
    row within max_css (a cut between two form rows reads fine).
    """
    raw, gw, gh, f = _gray(ref, EDGE_PROBE_WIDTH)
    bg = _page_background(raw, gw, gh)
    x0, y0, x1, y1 = [int(v * f) for v in box]
    x1, y1 = min(gw - 1, x1), min(gh - 1, y1)
    reach = max(1, int(max_css * scale * f))
    side = max(1, int(side_reach_css * scale * f))

    def is_bg(line_at):
        return lambda p: _is_page_background(line_at(p), bg)

    def is_calm(line_at):
        return lambda p: _is_calm(line_at(p))

    gap = max(1, int(ROW_GAP_CSS * scale * f))

    def pick(start, direction, last, tries, min_run=1):
        for test, distance in tries:
            limit = min(max(0, start + direction * distance), last)
            found = _walk_gap(start, limit, test, min_run)
            if found is not None:
                return found
        return start

    def col(p):
        return _line(raw, gw, p, y0, y1, True)

    def row(p):
        return _line(raw, gw, p, x0, x1, False)

    x0 = pick(x0, -1, gw - 1, [(is_bg(col), side), (is_calm(col), reach)])
    x1 = pick(x1, 1, gw - 1, [(is_bg(col), side), (is_calm(col), reach)])
    row_bg = ROW_BG_REACH_CSS if row_bg_reach_css is None else row_bg_reach_css
    near = max(0, int(row_bg * scale * f))
    y0 = pick(y0, -1, gh - 1, [(is_bg(row), near), (is_calm(row), reach), (is_bg(row), reach)], gap)
    y1 = pick(y1, 1, gh - 1, [(is_bg(row), near), (is_calm(row), reach), (is_bg(row), reach)], gap)
    snapped = (int(x0 / f), int(y0 / f), int((x1 + 1) / f), int((y1 + 1) / f))
    return union([box, snapped])


def _fit(lo, hi, want, limit):
    grow = want - (hi - lo)
    lo, hi = lo - grow // 2, hi + grow - grow // 2
    if lo < 0:
        lo, hi = 0, hi - lo
    if hi > limit:
        lo, hi = max(0, lo - (hi - limit)), limit
    return lo, hi


def grow(box, img_w, img_h, pad=0, min_w=0, min_h=0, aspect=None):
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(img_w, x1 + pad), min(img_h, y1 + pad)
    x0, x1 = _fit(x0, x1, max(x1 - x0, min_w), img_w)
    y0, y1 = _fit(y0, y1, max(y1 - y0, min_h), img_h)
    if aspect:
        narrowest, widest = aspect
        w, h = x1 - x0, y1 - y0
        if w / h < narrowest:
            x0, x1 = _fit(x0, x1, min(img_w, round(h * narrowest)), img_w)
        elif w / h > widest:
            y0, y1 = _fit(y0, y1, min(img_h, round(w / widest)), img_h)
    return x0, y0, x1, y1


def round_box(box, img_w, img_h, step=ROUND_TO, keep_whole=True):
    """Round the size up to `step`; with keep_whole, an axis that is almost all kept is kept whole."""
    x0, y0, x1, y1 = box
    if keep_whole and x1 - x0 >= KEEP_WHOLE_AXIS * img_w:
        x0, x1 = 0, img_w
    if keep_whole and y1 - y0 >= KEEP_WHOLE_AXIS * img_h:
        y0, y1 = 0, img_h
    w = min(img_w, -(-(x1 - x0) // step) * step)
    h = min(img_h, -(-(y1 - y0) // step) * step)
    x0 = min(max(0, x0 - (w - (x1 - x0)) // 2), img_w - w)
    y0 = min(max(0, y0 - (h - (y1 - y0)) // 2), img_h - h)
    return x0, y0, x0 + w, y0 + h


def geometry(box):
    x0, y0, x1, y1 = box
    return f"{x1 - x0}x{y1 - y0}+{x0}+{y0}"


def parse_geometry(g):
    w, h, x, y = map(int, re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", g).groups())
    return w, h, x, y


def parse_aspect(spec):
    """'16:10' -> exactly 1.6; '4:3-16:9' -> any ratio from 1.33 to 1.78."""
    def one(r):
        a, b = r.split(":")
        return float(a) / float(b)
    lo, _, hi = spec.partition("-")
    return (one(lo), one(hi or lo))


def page_background_hex(img):
    raw, gw, gh, _ = _gray(img, EDGE_PROBE_WIDTH)
    level = _page_background(raw, gw, gh)
    return f"gray({level * 100 / 255:.2f}%)"


def content_box(images, pad_css=16, scale=2):
    """Union of what is not plain page background in each image (drops empty page bottoms)."""
    boxes = []
    for img in images:
        iw, ih = house.size(img)
        geom = house.out(["magick", img, "-colorspace", "gray", "-bordercolor", page_background_hex(img),
                          "-border", 1, "-fuzz", "3%", "-trim", "-format", "%@", "info:"])
        m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geom)
        w, h, x, y = map(int, m.groups())
        boxes.append((max(0, x - 1), max(0, y - 1), min(iw, x - 1 + w), min(ih, y - 1 + h)))
    iw, ih = house.size(images[0])
    x0, y0, x1, y1 = union(boxes)
    pad = int(pad_css * scale)
    return round_box((max(0, x0 - pad), max(0, y0 - pad), min(iw, x1 + pad), min(ih, y1 + pad)), iw, ih,
                     keep_whole=False)


def css_box(box, scale):
    """{x, y, width, height} in CSS px (agent-browser get box) -> pixel (x0, y0, x1, y1)."""
    return (int(box["x"] * scale), int(box["y"] * scale), int((box["x"] + box["width"]) * scale),
            int((box["y"] + box["height"]) * scale))


def change_box(images, pad=40, aspect="4:3-16:9", min_size="640x400", scale=2, snap=True,
               fuzz=DIFF_FUZZ, keep=(), diff=None):
    """The full pipeline: diff union (+ keep boxes) -> pad -> min size -> aspect -> calm edges -> round.

    `keep` is a list of pixel boxes that must stay in frame (for example the card
    that holds the change, so its header is not cut off).
    """
    base = images[0]
    iw, ih = house.size(base)
    diff = diff if diff is not None else diff_union(base, images[1:], fuzz)
    raw_box = union([diff] + list(keep))
    if raw_box is None:
        return (0, 0, iw, ih)
    mw, mh = (int(v) for v in min_size.split("x"))
    ratio = parse_aspect(aspect) if aspect else None
    box = grow(raw_box, iw, ih, pad=int(pad * scale), min_w=int(mw * scale), min_h=int(mh * scale))
    if snap:
        box = snap_calm_edges(box, base, scale=scale)
    box = grow(box, iw, ih, aspect=ratio)
    if snap:
        box = snap_calm_edges(box, base, scale=scale)
    return round_box(box, iw, ih)


def video_frames(raw, every=3, skip_s=VIDEO_WARMUP_S, width=None, first_only=False):
    """Every Nth frame after the encoder warm-up (the first frames are soft), optionally scaled to width."""
    d = house.tmpdir()
    vf = f"select='gte(t\\,{skip_s})*not(mod(n\\,{every}))'"
    if width:
        vf += f",scale={width}:-2:flags=area"
    house.run(["ffmpeg", "-v", "error", "-i", raw, "-vf", vf, "-fps_mode", "passthrough"]
              + (["-frames:v", "1"] if first_only else []) + [os.path.join(d, "f%05d.png")])
    return d, sorted(os.path.join(d, f) for f in os.listdir(d))


def video_diff(raw, every=3):
    """Union of frame diffs against the first frame, in full-size pixels. Diffs run on frames
    scaled to DIFF_WIDTH (much faster); the box is scaled back and padded by one small pixel."""
    key = (os.path.abspath(raw), os.path.getmtime(raw), every)
    with _UNION_LOCK:
        if key in _UNION:
            return _UNION[key]
        d, frames = video_frames(raw, every, width=DIFF_WIDTH)
        try:
            box = diff_union(frames[0], frames[1:], VIDEO_DIFF_FUZZ)
            small_w, _ = _size(frames[0])
        finally:
            house.cleanup(d)
        full_w, full_h = (int(v) for v in house.out(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                                      "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                                      raw]).split(","))
        if box:
            k = full_w / small_w
            box = (max(0, int(box[0] * k - k)), max(0, int(box[1] * k - k)),
                   min(full_w, int(box[2] * k + k)), min(full_h, int(box[3] * k + k)))
        _UNION[key] = box
        return box


def video_change_geom(raw, every=3, keep_context=True, **opts):
    """Change box of a record.py take; also keeps the recorded context box, if any."""
    meta_path = os.path.splitext(raw)[0] + ".json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        opts.setdefault("scale", meta["scale"])
        if keep_context and meta.get("context_box"):
            opts.setdefault("keep", [css_box(meta["context_box"], meta["scale"])])
    diff = video_diff(raw, every)
    d, frames = video_frames(raw, every, first_only=True)
    try:
        return geometry(change_box(frames[:1], fuzz=VIDEO_DIFF_FUZZ, diff=diff, **opts))
    finally:
        house.cleanup(d)


def resolve(geom, raw):
    """'auto' -> the change box of a video; anything else is returned as is."""
    return video_change_geom(raw) if geom == "auto" else geom


def apply(geom, pairs):
    w, h, x, y = parse_geometry(geom)
    for src, dst in pairs:
        house.run(["magick", src, "-crop", f"{w}x{h}+{x}+{y}", "+repage", dst])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["geom", "video-geom", "content", "apply"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--pad", type=float, default=40)
    ap.add_argument("--aspect", default="4:3-16:9", help="W:H or a range W:H-W:H")
    ap.add_argument("--min", default="640x400")
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--no-snap", action="store_true")
    o = ap.parse_args()
    opts = dict(pad=o.pad, aspect=o.aspect or None, min_size=o.min, scale=o.scale, snap=not o.no_snap)
    if o.cmd == "geom":
        print(geometry(change_box(o.args, **opts)))
    elif o.cmd == "content":
        print(geometry(content_box(o.args, scale=o.scale)))
    elif o.cmd == "video-geom":
        print(video_change_geom(o.args[0], o.every, **opts))
    else:
        rest = o.args[1:]
        apply(o.args[0], list(zip(rest[0::2], rest[1::2])))


if __name__ == "__main__":
    main()
