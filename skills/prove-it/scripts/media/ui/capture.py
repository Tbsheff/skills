#!/usr/bin/env python3
"""Screenshots at 2x deviceScaleFactor through agent-browser.

  capture.py URL=OUT.png [URL2=OUT2.png ...] [--vw 1280 --vh 800 --scale 2] [--full]
             [--measure "#save" --measure ".card"]

Every shot reuses one browser session, sets the viewport (with scale) after
`open`, waits for fonts, then saves a PNG of W*scale x H*scale pixels.
With --measure, the CSS-px box of each selector is saved to OUT.json.
"""
import json
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab


def capture(url, out, vw=1280, vh=800, scale=2, full=False, measure=(), redact_selectors=()):
    ab.open_page(url, vw, vh, scale)
    ab.blur(list(redact_selectors))
    args = ["screenshot"] + (["--full"] if full else []) + [os.path.abspath(out)]
    ab.ab(*args)
    boxes = {sel: ab.box(sel) for sel in measure}
    with open(os.path.splitext(out)[0] + ".json", "w") as f:
        json.dump({"url": url, "viewport": [vw, vh], "scale": scale, "full": full, "boxes": boxes}, f, indent=2)
    return boxes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shots", nargs="+", help="URL=OUT.png")
    ap.add_argument("--vw", type=int, default=1280)
    ap.add_argument("--vh", type=int, default=800)
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--measure", action="append", default=[])
    o = ap.parse_args()
    for shot in o.shots:
        url, _, out = shot.rpartition("=")
        capture(url, out, o.vw, o.vh, o.scale, o.full, o.measure)
        print(out)


if __name__ == "__main__":
    main()
