#!/usr/bin/env python3
"""Labeled grid of screenshots in one shared house card (800 CSS px, 2x = 1600 px).

  grid.py OUT.png "Label=img.png" ["Label=img.png#WxH+X+Y" ...] --base SHA --change SHA
          [--cols 2] [--crop auto|none|WxH+X+Y] [--aspect 1:1-16:9 --pad 24]
          [--same-scale] [--title "..."] [--subtitle "..."] [--side change]

--crop auto applies ONE change box (crop.py, first image = base) to every
tile. A per-tile "#WxH+X+Y" crop wins over --crop. --same-scale stacks the
tiles in one column at their real CSS size (for viewports), so text stays at
1x and a narrow viewport looks narrow.
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop
import house


def parse(spec):
    label, _, rest = spec.partition("=")
    path, _, geom = rest.partition("#")
    return label, path, geom or None


def build(out, specs, base, change, title, subtitle="", cols=2, geom="none", aspect="4:3-16:9", pad=40,
          same_scale=False, side="change", workdir=None, pixel_scale=2):
    tiles = [parse(s) for s in specs]
    workdir = workdir or os.path.splitext(os.path.abspath(out))[0] + "-tiles"
    os.makedirs(workdir, exist_ok=True)
    if geom == "auto":
        geom = crop.geometry(crop.change_box([p for _, p, _ in tiles], pad=pad, aspect=aspect))
    shared_geom = None if geom in (None, "none") else geom
    cropped = []
    for i, (label, path, own) in enumerate(tiles):
        g = own or shared_geom
        dst = os.path.join(workdir, f"tile{i}.png")
        if g:
            crop.apply(g, [(path, dst)])
        else:
            shutil.copy(path, dst)
        cropped.append((label, dst))
    columns = "1fr" if same_scale else f"repeat({cols},1fr)"
    sha = change if side == "change" else base
    cells = ""
    for label, p in cropped:
        img = house.img_tag(p, label)
        if same_scale:
            css_w = house.size(p)[0] / pixel_scale
            img = img.replace("<img", f'<img style="width:{css_w:.0f}px;max-width:100%"')
        cells += f'<div class="tile"><p class="cap"><b>{house.esc(label)}</b></p>{img}</div>'
    body = f'<div class="tiles" style="grid-template-columns:{columns}">{cells}</div>'
    sub = subtitle or f"All tiles are {house.side_label(side, sha)}."
    folder = os.path.relpath(os.path.dirname(tiles[0][1]))
    source = f"{folder}/" + ", ".join(os.path.basename(p) for _, p, _ in tiles)
    house.card_png(out, title, sub, body, base, change, source, house.now())
    return shared_geom


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--base", required=True)
    ap.add_argument("--change", required=True)
    ap.add_argument("--title", default="Screens")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--crop", default="none")
    ap.add_argument("--aspect", default="4:3-16:9")
    ap.add_argument("--pad", type=float, default=40)
    ap.add_argument("--same-scale", action="store_true")
    ap.add_argument("--side", default="change", choices=["base", "change"])
    o = ap.parse_args()
    print(build(o.out, o.specs, o.base, o.change, o.title, o.subtitle, o.cols, o.crop, o.aspect, o.pad,
                o.same_scale, o.side))


if __name__ == "__main__":
    main()
