#!/usr/bin/env python3
"""Before/after wipe GIF in a shared house card.

  wipe.py BEFORE.png AFTER.png OUT.gif --base SHA --change SHA [--crop content|auto|none|WxH+X+Y]
          [--title "..."] [--source "..."]

An accent divider sweeps right to show the change, holds, and sweeps back.
Left of the line is CHANGE, right of the line is BASE; the slot header says
so with the shared side labels. Both images get the same crop
(content = the area that is not plain page background in either image).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop
import house

HOLD_START, SWEEP, HOLD_MID = 0.8, 1.0, 1.2
DURATION = HOLD_START + SWEEP + HOLD_MID + SWEEP + 0.6
CLIP_FPS = 30
DIVIDER_PX = 4
GIF_SCALE = 1.5


def smooth(u):
    return f"(({u})*({u})*(3-2*({u})))"


def position(t):
    a, b = HOLD_START, HOLD_START + SWEEP
    c, e = b + HOLD_MID, b + HOLD_MID + SWEEP
    return (f"if(lt({t},{a}),0,if(lt({t},{b}),{smooth(f'({t}-{a})/{SWEEP}')},"
            f"if(lt({t},{c}),1,if(lt({t},{e}),1-{smooth(f'({t}-{c})/{SWEEP}')},0))))")


def resolve_geom(before, after, geom):
    if geom == "content":
        return crop.geometry(crop.content_box([before, after]))
    if geom == "auto":
        return crop.geometry(crop.change_box([before, after]))
    if geom == "none":
        w, h = house.size(after)
        return f"{w}x{h}+0+0"
    return geom


def clip(before, after, out, geom):
    cw, ch, cx, cy = crop.parse_geometry(geom)
    prep = f"crop={cw}:{ch}:{cx}:{cy},format=gbrp"
    graph = (f"[0]{prep}[a];[1]{prep}[b];"
             f"[a][b]blend=all_expr='if(lt(X,W*{position('T')}),A,B)',format=rgb24[base];"
             f"[base][2]overlay=x='W*{position('t')}-{DIVIDER_PX // 2}':y=0:"
             f"enable='between({position('t')},0.002,0.998)',format=yuv444p[out]")
    house.run(["ffmpeg", "-y", "-v", "error",
               "-loop", 1, "-t", DURATION, "-framerate", CLIP_FPS, "-i", after,
               "-loop", 1, "-t", DURATION, "-framerate", CLIP_FPS, "-i", before,
               "-f", "lavfi", "-i", f"color={house.ACCENT}:s={DIVIDER_PX}x{ch}:r={CLIP_FPS}:d={DURATION}",
               "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264", "-crf", 10, "-preset", "fast", out])
    return cw, ch


def build(before, after, out, base, change, geom="content", title="Before and after", source=None,
          subtitle="The divider sweeps right to show the change, then back."):
    geom = resolve_geom(before, after, geom)
    d = house.tmpdir()
    try:
        mp4 = os.path.join(d, "wipe.mp4")
        cw, ch = clip(before, after, mp4, geom)
        head = (f"<span>{house.side_label('change', change)} &larr; left of the line</span>"
                f"<span>right of the line &rarr; {house.side_label('base', base)}</span>")
        bg = os.path.join(d, "card.png")
        rects = house.video_card(bg, title, subtitle,
                                 [(head, cw, ch)], base, change,
                                 source or f"{os.path.basename(before)} + {os.path.basename(after)}",
                                 house.now(), scale=GIF_SCALE)
        house.compose(bg, rects, [mp4], out, gif=True, fps=house.GIF_FPS)
    finally:
        house.cleanup(d)
    return geom


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("out")
    ap.add_argument("--base", required=True)
    ap.add_argument("--change", required=True)
    ap.add_argument("--crop", default="content")
    ap.add_argument("--title", default="Before and after")
    ap.add_argument("--source", default=None)
    o = ap.parse_args()
    print(build(o.before, o.after, o.out, o.base, o.change, o.crop, o.title, o.source))


if __name__ == "__main__":
    main()
