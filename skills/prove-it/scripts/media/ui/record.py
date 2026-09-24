#!/usr/bin/env python3
"""Record one click, or a multi-step flow, with a visible cursor, ripple and target outline.

  record.py URL SELECTOR RAW.mp4 [--vw 1280 --vh 800 --scale 2 --fps 60]
            [--lead-ms 700 --move-ms 800 --tail-ms 2600 --from -190,-130] [--context .card]
  record.py URL --steps STEPS.json RAW.mp4 [...]

Uses `agent-browser record` (0.38+). The cursor is placed before recording starts (inside
the --context element, if given), so the video opens on a still frame with the pointer
visible. Then the pointer glides to each target and the real action runs through
agent-browser (trusted click, fill, select, press).
Writes RAW.mp4 and RAW.json: timing that motion.py reads (anchor_s: the anchor action,
in seconds from the first visible motion), step events, and seen_text. The video is often
smaller than viewport x scale, so RAW.json "scale" is the measured video px per CSS px.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab
import house
import steps as flows

OUTLINE_MS = 900
PLACE_SETTLE_MS = 150


def video_scale(raw, vw):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                        "-of", "csv=p=0", raw], capture_output=True, text=True)
    try:
        return int(r.stdout.strip()) / vw
    except ValueError:
        return None


def prepare_page(redact_selectors=()):
    ab.inject_cursor(house.js_style())
    ab.blur(list(redact_selectors))


def place_cursor(first_target, start_offset, context, runner):
    if first_target is not None:
        try:
            sel = runner.resolve(first_target)
            ab.eval_js(f"window.__proveit.place({json.dumps(sel)}, {start_offset[0]}, {start_offset[1]}, "
                       f"{json.dumps(context)})")
            return
        except flows.StepError:
            pass
    ab.eval_js("window.__proveit.moveTo(innerWidth / 2, innerHeight / 3)")


def record_flow(url, flow, raw, vw=1280, vh=800, scale=2, fps=60, lead_ms=700, move_ms=800, tail_ms=2600,
                start_offset=(-190, -130), context=None, watch_text=(), side="change", redact_selectors=()):
    """Open url, record the flow, and return the meta dict (also written to RAW.json).

    meta["before_text"] holds each watch text as seen right before the first step;
    meta["seen_text"] holds whether it showed at any moment after the flow started.
    """
    raw = os.path.abspath(raw)
    ab.open_page(url, vw, vh, scale)
    context_box = ab.box(context) if context else None
    prepare_page(redact_selectors)
    before = {text: ab.has_visible_text(text) for text in watch_text}
    origin = url.split("://", 1)[0] + "://" + url.split("://", 1)[1].split("/", 1)[0]

    def on_page():
        prepare_page(redact_selectors)
        ab.eval_js("window.__proveit.moveTo(innerWidth / 2, innerHeight / 3)")

    runner = flows.Runner(ab, side, origin, move_ms=move_ms, outline_ms=OUTLINE_MS, strict=(side == "change"),
                          on_page=on_page, watch=watch_text)
    first = next((s for s in flow if s["kind"] in flows.TARGETED), None)
    first_target = (first["step"] if side == "change" else first["base_step"])[first["kind"]] if first else None
    place_cursor(first_target, start_offset, context, runner)
    ab.ab("wait", PLACE_SETTLE_MS)
    ab.ab("record", "start", raw, "--fps", fps)
    try:
        ab.ab("wait", lead_ms)
        runner.run(flow)
        runner.tail(tail_ms)
    finally:
        ab.ab("record", "stop")
    events, anchor_s = flows.relative_events(runner.events)
    meta = {"url": url, "side": side, "selector": first_target if isinstance(first_target, str) else None,
            "vw": vw, "vh": vh, "scale": video_scale(raw, vw) or scale, "page_scale": scale, "fps": fps,
            "lead_ms": lead_ms, "move_ms": move_ms, "tail_ms": tail_ms, "outline_ms": OUTLINE_MS,
            "context": context, "context_box": context_box, "anchor_s": anchor_s, "events": events,
            "steps": flows.public(flow), "before_text": before, "seen_text": runner.seen}
    with open(os.path.splitext(raw)[0] + ".json", "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def record(url, selector, raw, vw=1280, vh=800, scale=2, fps=60, lead_ms=700, move_ms=800,
           tail_ms=2600, start_offset=(-190, -130), context=None, watch_text=()):
    """The single-click form: one click on selector."""
    flow = flows.from_click({"change_selector": selector, "label": "Click"})
    return record_flow(url, flow, raw, vw, vh, scale, fps, lead_ms, move_ms, tail_ms, start_offset, context,
                       watch_text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("selector", nargs="?", help="CSS selector to click (or use --steps)")
    ap.add_argument("raw")
    ap.add_argument("--steps", default=None, help="JSON file with a steps list")
    ap.add_argument("--vw", type=int, default=1280)
    ap.add_argument("--vh", type=int, default=800)
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--lead-ms", type=int, default=700)
    ap.add_argument("--move-ms", type=int, default=800)
    ap.add_argument("--tail-ms", type=int, default=2600)
    ap.add_argument("--context", default=None, help="selector whose box the crop must keep")
    ap.add_argument("--from", dest="start", default="-190,-130",
                    help="cursor start offset from the target center, CSS px")
    o = ap.parse_args()
    dx, dy = (int(v) for v in o.start.split(","))
    if o.steps:
        with open(o.steps) as f:
            flow = flows.normalize(json.load(f))
    elif o.selector:
        flow = flows.from_click({"change_selector": o.selector})
    else:
        ap.error("give SELECTOR or --steps")
    try:
        meta = record_flow(o.url, flow, o.raw, o.vw, o.vh, o.scale, o.fps, o.lead_ms, o.move_ms, o.tail_ms,
                           (dx, dy), o.context)
    finally:
        ab.close()
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
