#!/usr/bin/env python3
"""Numbered keyframes of one recorded click, all with the same crop.

  storyboard.py RAW.mp4 OUT.png --crop WxH+X+Y|auto
      [--step "Idle@-0.9" --step "Click@0.05" --step "Saving@0.35" --step "Saved@settle"]
      --base SHA --change SHA [--side change] [--cols 2] [--title "..."]

Times are seconds relative to the click that motion.py detects in RAW
(`settle` = the frame where the page stops changing). Captions show those
real times, not slowed ones. The sheet is a shared house card (1600 px).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop
import house
import motion

DEFAULT_STEPS = ["Idle@-0.9", "Click@0.05", "Saving@0.4", "Saved@settle"]


def frame_at(raw, t, path, geom):
    w, h, x, y = crop.parse_geometry(geom)
    house.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", raw, "-frames:v", 1,
               "-vf", f"crop={w}:{h}:{x}:{y}", path])
    return path


def build(raw, out, geom, steps, title, base, change, side="change", cols=2, workdir=None, anchor_name="click"):
    """Keyframes in a shared house card; frames are kept in workdir (the card links them)."""
    a = motion.analyze(raw)
    workdir = workdir or os.path.splitext(os.path.abspath(out))[0] + "-frames"
    os.makedirs(workdir, exist_ok=True)
    tiles = []
    for i, spec in enumerate(steps, 1):
        name, _, when = spec.partition("@")
        rel = (a["settle"] - a["click"]) if when == "settle" else float(when)
        f = frame_at(raw, a["click"] + rel, os.path.join(workdir, f"step{i}.png"), geom)
        tiles.append(f'<div class="tile"><p class="cap">{house.num(i)}<b>{house.esc(name)}</b>'
                     f'<span>{rel:+.2f} s</span></p>{house.img_tag(f, name)}</div>')
    body = f'<div class="tiles" style="grid-template-columns:repeat({cols},1fr)">{"".join(tiles)}</div>'
    sha = change if side == "change" else base
    subtitle = (f"Frames from one recording of {house.side_label(side, sha)}. "
                f"Times are real (not slowed), measured from the {anchor_name}.")
    house.card_png(out, title, subtitle, body, base, change, os.path.relpath(raw), house.now())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--crop", required=True)
    ap.add_argument("--step", action="append", default=None)
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--title", default="Storyboard")
    ap.add_argument("--base", required=True)
    ap.add_argument("--change", required=True)
    ap.add_argument("--side", default="change", choices=["base", "change"])
    o = ap.parse_args()
    geom = crop.resolve(o.crop, o.raw) if o.crop else None
    print(build(o.raw, o.out, geom, o.step or DEFAULT_STEPS, o.title, o.base, o.change, o.side, o.cols))


if __name__ == "__main__":
    main()
