#!/usr/bin/env python3
"""Change boxes: dim the page, outline each changed region.

  boxes.py BEFORE.png AFTER.png OUT.png --base SHA_OF_BEFORE --change SHA_OF_AFTER
           [--crop none|auto|WxH+X+Y] [--merge 40] [--max 6] [--title "..."] [--legend "box 1" --legend ...]

Changed pixels (magick difference + threshold) are binned into CELL_CSS
cells, cells closer than --merge CSS px are clustered (connected
components), and the clusters become at most --max boxes. The after image
is dimmed except inside the boxes, each box gets a rounded accent outline and
a numbered marker; box edges are pushed out so they do not cut an element in
half. The result is a shared house card stamped with the SHAs of the pair.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop
import house

CELL_CSS = 4
BOX_PAD_CSS = 6
BOX_SNAP_CSS = 24
BOX_SIDE_SNAP_CSS = 120


def changed_cells(before, after, scale):
    w, h = house.size(after)
    cell = max(1, int(CELL_CSS * scale))
    gw, gh = -(-w // cell), -(-h // cell)
    raw = house.run(["magick", before, after, "-compose", "difference", "-composite", "-colorspace",
                     "gray", "-threshold", crop.DIFF_FUZZ, "-filter", "box", "-resize", f"{gw}x{gh}!",
                     "-depth", 8, "gray:-"], capture_output=True).stdout
    return raw, gw, gh, cell


def cluster(raw, gw, gh, reach):
    """Connected components of changed cells, joining cells up to `reach` cells apart."""
    on = {(x, y) for y in range(gh) for x in range(gw) if raw[y * gw + x] > 0}
    seen, boxes = set(), []
    for start in on:
        if start in seen:
            continue
        stack, members = [start], []
        seen.add(start)
        while stack:
            x, y = stack.pop()
            members.append((x, y))
            for dx in range(-reach, reach + 1):
                for dy in range(-reach, reach + 1):
                    n = (x + dx, y + dy)
                    if n in on and n not in seen:
                        seen.add(n)
                        stack.append(n)
        xs, ys = [m[0] for m in members], [m[1] for m in members]
        boxes.append([min(xs), min(ys), max(xs) + 1, max(ys) + 1])
    return boxes


def merge_to(boxes, limit):
    """Merge the two closest boxes until there are at most `limit`."""
    def gap(a, b):
        return max(0, max(a[0], b[0]) - min(a[2], b[2])) + max(0, max(a[1], b[1]) - min(a[3], b[3]))
    boxes = [list(b) for b in boxes]
    while len(boxes) > limit:
        i, j = min(((i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))),
                   key=lambda p: gap(boxes[p[0]], boxes[p[1]]))
        a, b = boxes[i], boxes.pop(j)
        boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
    return boxes


def find_boxes(before, after, scale=2, merge_css=40, max_boxes=6):
    raw, gw, gh, cell = changed_cells(before, after, scale)
    boxes = merge_to(cluster(raw, gw, gh, max(1, round(merge_css / CELL_CSS))), max_boxes)
    w, h = house.size(after)
    pad = int(BOX_PAD_CSS * scale)
    px = [(max(0, x0 * cell - pad), max(0, y0 * cell - pad), min(w, x1 * cell + pad), min(h, y1 * cell + pad))
          for x0, y0, x1, y1 in boxes]
    return sorted(px, key=lambda b: (b[1] // int(40 * scale), b[0]))


def snap_boxes(boxes, ref, scale):
    """Grow each box so its edges do not cut through an element (for example a nav pill)."""
    return [crop.snap_calm_edges(b, ref, max_css=BOX_SNAP_CSS, scale=scale, side_reach_css=BOX_SIDE_SNAP_CSS,
                                 row_bg_reach_css=0) for b in boxes]


def mark(after, out, boxes, scale=2, dim=True):
    """Draw numbered rounded boxes on `after` (dimmed outside the boxes when dim=True)."""
    w, h = house.size(after)
    r, sw = house.css(house.BOX_RADIUS, scale), house.css(house.BOX_STROKE, scale)
    d = house.tmpdir()
    try:
        mask = ["magick", "-size", f"{w}x{h}", "xc:black", "-fill", "white"]
        rings = ["-fill", "none", "-stroke", house.ACCENT, "-strokewidth", sw]
        for x0, y0, x1, y1 in boxes:
            mask += ["-draw", f"roundrectangle {x0},{y0} {x1},{y1} {r},{r}"]
            rings += ["-draw", f"roundrectangle {x0},{y0} {x1},{y1} {r},{r}"]
        m = os.path.join(d, "mask.png")
        house.run(mask + [m])
        dimmed = os.path.join(d, "dim.png")
        house.run(["magick", after, "-fill", house.DIM, "-colorize", f"{house.DIM_PERCENT if dim else 0}%", dimmed])
        cmd = ["magick", dimmed, after, m, "-composite", *rings]
        for i, (x0, y0, x1, y1) in enumerate(boxes, 1):
            p = house.marker(i, os.path.join(d, f"n{i}.png"), scale)
            pw, ph = house.size(p)
            px = min(max(0, x0 - pw // 3), w - pw)
            py = y0 - ph - house.css(4, scale)
            py = py if py >= 0 else min(h - ph, y1 + house.css(4, scale))
            cmd += [p, "-geometry", f"+{px}+{py}", "-composite"]
        house.run(cmd + [out])
    finally:
        house.cleanup(d)
    return out


def render(before, after, out, boxes, base, change, title, legend=None, geom=None, scale=2, workdir=None):
    """Marked image in a shared house card. base/change are the SHAs of THIS pair."""
    workdir = workdir or os.path.dirname(os.path.abspath(out))
    marked = os.path.join(workdir, os.path.splitext(os.path.basename(out))[0] + "-marked.png")
    mark(after, marked, boxes, scale)
    if geom:
        crop.apply(geom, [(marked, marked)])
    items = "".join(f"<span>{house.num(i)}{house.esc(t)}</span>" for i, t in enumerate(legend or [], 1))
    body = house.img_tag(marked, title).replace("<img", '<img class="shot"')
    body += f'<div class="legend">{items}</div>' if items else ""
    subtitle = (f"{house.side_label('change', change)} compared with {house.side_label('base', base)}. "
                f"The page is dimmed except where pixels changed.")
    house.card_png(out, title, subtitle, body, base, change,
                   f"{os.path.relpath(before)} vs {os.path.relpath(after)}", house.now())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("out")
    ap.add_argument("--crop", default="none")
    ap.add_argument("--merge", type=float, default=40, help="join changes closer than this, CSS px")
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--title", default="What changed")
    ap.add_argument("--base", required=True, help="SHA of BEFORE")
    ap.add_argument("--change", required=True, help="SHA of AFTER")
    ap.add_argument("--legend", action="append", default=None,
                    help="text for box 1, then box 2, ... (boxes are numbered top to bottom)")
    o = ap.parse_args()
    boxes = snap_boxes(find_boxes(o.before, o.after, o.scale, o.merge, o.max), o.after, o.scale)
    geom = None
    if o.crop == "auto":
        geom = crop.geometry(crop.change_box([o.before, o.after], scale=o.scale, pad=56))
    elif o.crop != "none":
        geom = o.crop
    render(o.before, o.after, o.out, boxes, o.base, o.change, o.title, o.legend, geom, o.scale)
    print(json.dumps({"boxes": boxes, "crop": geom}))


if __name__ == "__main__":
    main()
