#!/usr/bin/env python3
"""Base and change runs of the same click, stacked, aligned on the click.

  twin.py BASE_RAW.mp4 CHANGE_RAW.mp4 OUT.mp4 --base SHA --change SHA
          [--title "..."] [--slow 0.5 --slow-ms 750]

Both raws come from record.py with the same flow and --context. Each pane is
cropped to the same anchor (the context element, for example the form card)
plus whatever moved outside it, and both panes are shown at ONE scale,
stacked. Each pane is cut to the same window around its own click. The card
is 800 CSS px wide at 2x, so the video is 1600 px wide.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop
import house
import motion

PANE_PAD_CSS = 8
PANE_MIN = "100x100"
PANE_GAP_CSS = 12


def pane_crops(raws):
    """Per pane: the same anchor on both sides, the recorded context element (the form card),
    plus anything that moved outside it (the toast). No aspect forcing, so nothing is cut mid-word."""
    return [crop.video_change_geom(r, keep_context=True, pad=PANE_PAD_CSS, min_size=PANE_MIN,
                                   aspect="1:4-4:1", snap=False) for r in raws]


def render(base_raw, change_raw, out, base, change, title, slow=0.5, slow_ms=750, hold=1.0):
    raws = [base_raw, change_raw]
    runs = [motion.analyze(r) for r in raws]
    pre = max(r["click"] - r["start"] for r in runs) + motion.KEEP_BEFORE_MOVE_S
    post = max(r["settle"] - r["click"] for r in runs) + motion.AFTER_SETTLE_S
    windows = [(r["click"] - pre, r["click"] + post) for r in runs]
    plans = [motion.plan(r, slow, slow_ms, w) for r, w in zip(runs, windows)]
    lengths = [sum((t1 - t0) / s for t0, t1, s in p) for p in plans]
    geoms = pane_crops(raws)
    sizes = [crop.parse_geometry(g)[:2] for g in geoms]
    px_per_css = motion.meta_for(change_raw)["scale"]
    pane_scale = min(1.0, house.BODY_WIDTH / (max(w for w, _ in sizes) / px_per_css))
    d = house.tmpdir()
    try:
        clips = []
        for i, (raw, geom, w) in enumerate(zip(raws, geoms, windows)):
            clip = os.path.join(d, f"clip{i}.mp4")
            motion.render(raw, clip, geom, slow, slow_ms, hold + max(lengths) - lengths[i], window=w)
            clips.append(clip)
        bg = os.path.join(d, "card.png")
        subtitle = (f"The same cursor flow on both commits, lined up on the click. "
                    f"The click plays at {slow:g}&times; speed.")
        slots = [(house.side_label(side, sha), w, h, w / motion.meta_for(raw)["scale"] * pane_scale)
                 for (side, sha, raw), (w, h) in zip((("base", base, base_raw), ("change", change, change_raw)),
                                                      sizes)]
        rects = house.video_card(bg, title, subtitle, slots, base, change,
                                 f"{os.path.relpath(base_raw)} + {os.path.basename(change_raw)}", house.now(),
                                 row=False)
        house.compose(bg, rects, clips, out, fps=motion.OUT_FPS)
    finally:
        house.cleanup(d)
    return {"crops": geoms, "plans": plans}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_raw")
    ap.add_argument("change_raw")
    ap.add_argument("out")
    ap.add_argument("--base", required=True)
    ap.add_argument("--change", required=True)
    ap.add_argument("--title", default="Same click, base vs change")
    ap.add_argument("--slow", type=float, default=0.5)
    ap.add_argument("--slow-ms", type=int, default=750)
    o = ap.parse_args()
    print(json.dumps(render(o.base_raw, o.change_raw, o.out, o.base, o.change, o.title, o.slow, o.slow_ms)))


if __name__ == "__main__":
    main()
