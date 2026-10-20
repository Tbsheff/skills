#!/usr/bin/env python3
"""Turn a raw record.py take into a tight, smooth clip (and GIF).

  motion.py RAW.mp4 CLIP.mp4 [--crop WxH+X+Y|auto] [--slow 0.5 --slow-ms 750] [--hold 1.0]
            [--card OUT.gif --title "..." --subtitle "..." --base SHA --change SHA]

What it does, from the frame-to-frame difference signal of RAW:
  - finds when the cursor starts to move, and so when the click lands
    (start + move_ms from RAW.json), and when the page settles again;
  - trims idle time: keeps 0.35 s before the cursor moves and stops just
    after the page settles;
  - plays the click moment (from 0.15 s before the click to --slow-ms after)
    at --slow speed; RAW is 60 fps, so 0.5x slow motion is still real 30 fps;
  - holds the final frame for --hold seconds;
  - applies ONE crop to every frame (auto = crop.py video-geom, which also
    keeps the recorded context box);
  - writes a clean 30 fps H.264 clip, and with --card puts it in a shared
    house card (title, BASE/CHANGE pills, source + capture-time footer).
    Say "plays at 0.5x" in the card subtitle, so the note is always on screen.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop
import house

OUT_FPS = 30
CHANGE_THRESHOLD = 3
WARMUP_S = 0.3
KEEP_BEFORE_MOVE_S = 0.35
SLOW_LEAD_S = 0.15
MIN_SETTLE_AFTER_CLICK_S = 0.3
STILL_RUN_S = 0.4
AFTER_SETTLE_S = 0.1


def meta_for(raw):
    with open(os.path.splitext(raw)[0] + ".json") as f:
        return json.load(f)


def diff_signal(raw):
    """[(t, max luma change vs previous frame)] on a 640 px grayscale copy."""
    r = house.run(["ffmpeg", "-v", "error", "-i", raw, "-vf",
                   "scale=640:-2,format=gray,tblend=all_mode=difference,signalstats,"
                   "metadata=print:key=lavfi.signalstats.YMAX:file=-", "-f", "null", "-"],
                  capture_output=True, text=True)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stdout)]
    values = [int(v) for v in re.findall(r"YMAX=(\d+)", r.stdout)]
    return list(zip(times, values))


_ANALYSIS = {}


def analyze(raw):
    key = (os.path.abspath(raw), os.path.getmtime(raw))
    if key not in _ANALYSIS:
        _ANALYSIS[key] = _analyze(raw)
    return dict(_ANALYSIS[key])


def _analyze(raw):
    m = meta_for(raw)
    sig = diff_signal(raw)
    duration = sig[-1][0] if sig else 0
    earliest = max(WARMUP_S, m["lead_ms"] / 1000 - 0.35)
    start = next((t for t, v in sig if t >= earliest and v > CHANGE_THRESHOLD), earliest)
    click = start + m.get("anchor_s", m["move_ms"] / 1000)
    settle, run_start = None, None
    for t, v in sig:
        if t < click + MIN_SETTLE_AFTER_CLICK_S:
            continue
        if v > CHANGE_THRESHOLD:
            run_start = None
            continue
        run_start = t if run_start is None else run_start
        if t - run_start >= STILL_RUN_S:
            settle = run_start
            break
    settle = settle or duration
    return {"start": start, "click": click, "settle": settle, "duration": duration,
            "fps": m["fps"], "scale": m["scale"]}


def plan(a, slow=0.5, slow_ms=750, window=None):
    """Segments (t0, t1, speed) of RAW to play, in order."""
    w0, w1 = window or (a["start"] - KEEP_BEFORE_MOVE_S, a["settle"] + AFTER_SETTLE_S)
    w0, w1 = max(WARMUP_S, w0), min(a["duration"], w1)
    s0, s1 = max(w0, a["click"] - SLOW_LEAD_S), min(w1, a["click"] + slow_ms / 1000)
    return [(w0, s0, 1.0), (s0, s1, slow), (s1, w1, 1.0)]


def slow_window(segments):
    """Output-time interval where the slowed segment plays."""
    t = 0.0
    for t0, t1, speed in segments:
        d = (t1 - t0) / speed
        if speed != 1.0:
            return t, t + d
        t += d
    return None


def timeline_chain(inp, segments, tag, crop_geom=None, width=None, hold=1.0):
    """Filter chain: [inp] -> cut + retime segments -> fps -> crop -> scale -> hold -> [tag]."""
    n = len(segments)
    parts = [f"[{inp}]split={n}" + "".join(f"[{tag}s{i}]" for i in range(n))]
    for i, (t0, t1, speed) in enumerate(segments):
        parts.append(f"[{tag}s{i}]trim={t0:.4f}:{t1:.4f},setpts=(PTS-STARTPTS)/{speed}[{tag}p{i}]")
    tail = f"fps={OUT_FPS}"
    if crop_geom:
        w, h, x, y = crop.parse_geometry(crop_geom)
        tail += f",crop={w}:{h}:{x}:{y}"
    if width:
        tail += f",scale={width}:-2:flags=lanczos"
    tail += f",tpad=stop_mode=clone:stop_duration={hold}"
    parts.append("".join(f"[{tag}p{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,{tail}[{tag}]")
    return ";".join(parts)


def encode(inputs, graph, out_label, out):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for i in inputs:
        cmd += ["-i", i]
    cmd += ["-filter_complex", graph, "-map", f"[{out_label}]", "-r", OUT_FPS, "-c:v", "libx264",
            "-crf", 12, "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    house.run(cmd)


def render(raw, out, crop_geom=None, slow=0.5, slow_ms=750, hold=1.0, width=None, window=None):
    """Write the clean clip: cut, retimed, cropped, 30 fps, no chrome. Returns the plan."""
    a = analyze(raw)
    segs = plan(a, slow, slow_ms, window)
    encode([raw], timeline_chain("0:v", segs, "out", crop_geom, width, hold), "out", out)
    return {"analysis": a, "segments": segs, "slow_window": slow_window(segs)}


def card(clip, out, title, subtitle, head, base, change, source, gif=False, gif_scale=1.5):
    """Put a clean clip into a house video card (MP4 at 2x, or GIF at gif_scale)."""
    w, h = (int(v) for v in house.out(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height", "-of", "csv=p=0", clip]).split(","))
    d = house.tmpdir()
    try:
        bg = os.path.join(d, "card.png")
        rects = house.video_card(bg, title, subtitle, [(head, w, h)], base, change, source, house.now(),
                                 scale=gif_scale if gif else 2)
        house.compose(bg, rects, [clip], out, gif=gif, fps=house.GIF_FPS if gif else OUT_FPS)
    finally:
        house.cleanup(d)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("out", help="clean clip (MP4)")
    ap.add_argument("--crop", default=None, help="WxH+X+Y, or 'auto' for crop.py video-geom")
    ap.add_argument("--slow", type=float, default=0.5)
    ap.add_argument("--slow-ms", type=int, default=750)
    ap.add_argument("--hold", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=None, help="scale the clip to this width")
    ap.add_argument("--card", default=None, help="also write a house card: .gif or .mp4")
    ap.add_argument("--title", default="Interaction")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--base", default="")
    ap.add_argument("--change", default="")
    ap.add_argument("--side", default="change", choices=["base", "change"])
    o = ap.parse_args()
    geom = crop.resolve(o.crop, o.raw) if o.crop else None
    info = render(o.raw, o.out, geom, o.slow, o.slow_ms, o.hold, o.width)
    info["crop"] = geom
    if o.card:
        sha = o.change if o.side == "change" else o.base
        card(o.out, o.card, o.title, o.subtitle, house.side_label(o.side, sha), o.base, o.change, o.raw,
             gif=o.card.endswith(".gif"))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
