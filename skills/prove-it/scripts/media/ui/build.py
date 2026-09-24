#!/usr/bin/env python3
"""Build the UI proof media for one resolved scenario.

  build.py --scenario SCENARIO.json --out DIR [--work DIR] [--all-media] [--no-cache]

Serves the base ref from a cached git worktree and the change side from the working
tree (a ref of null). Base and change are captured at the same time, in two browser
sessions on two ports. The flow is one click (ui.click) or a list of steps (ui.steps).

Default media: action.gif (hero), twin.mp4 (inline), before.png and after.png (inputs),
and each details card that the scenario asks for: states.png (states), viewports.png
(viewports), diff-boxes.png (a followup ref), storyboard.png (steps or click.storyboard),
and any name in ui.media. --all-media (or ui.all_media, or PROVE_IT_ALL_MEDIA=1) builds
every card, wipe.gif included. --no-cache (or ui.cache: false, or PROVE_IT_NO_CACHE=1)
uses a temporary base worktree and stops every server at the end.
Writes media-manifest.json, which prove.py reads to register the media as evidence.
"""
import argparse
import concurrent.futures
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ab
import auth as authstate
import boxes
import capture
import crop
import grid
import house
import motion
import record
import scenario
import steps as flows
import storyboard
import twin
import wipe

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
import redact

EDGE_CSS = 24
STORY_ABOVE_CSS = 100
PAGE_TOP_SNAP_CSS = 100
RENDER_WORKERS = 4
FLOW_TAIL_MS = 2000
ALWAYS = ("before.png", "after.png", "action.gif", "twin.mp4")
OPTIONAL = ("wipe.gif", "storyboard.png", "states.png", "viewports.png", "diff-boxes.png")


def truthy(value):
    return str(value).lower() in {"1", "true", "yes"}


def media_plan(s, all_media=False):
    """Names of the media to build. Details cards are built only when asked for."""
    can = set(ALWAYS) | {"wipe.gif", "storyboard.png"}
    if s.get("states"):
        can.add("states.png")
    if s.get("viewports"):
        can.add("viewports.png")
    if "followup" in s.get("refs", {}):
        can.add("diff-boxes.png")
    if all_media or s.get("all_media") or truthy(os.environ.get("PROVE_IT_ALL_MEDIA", "")):
        return can
    asked = set(ALWAYS) | set(s.get("media") or [])
    unknown = asked - set(ALWAYS) - set(OPTIONAL)
    if unknown:
        raise RuntimeError(f"ui.media has unknown names {sorted(unknown)}; use {list(ALWAYS + OPTIONAL)}")
    if s.get("states"):
        asked.add("states.png")
    if s.get("viewports"):
        asked.add("viewports.png")
    if "followup" in s.get("refs", {}):
        asked.add("diff-boxes.png")
    if s.get("steps") or (s.get("click") or {}).get("storyboard"):
        asked.add("storyboard.png")
    return asked & can


def viewport_window(meta, focus, context, height_css):
    """Pixel crop for one viewport tile.

    Width: the whole context element (a vertical cut through a form reads badly).
    Height: height_css, ending EDGE_CSS below the focus element.
    """
    w, _ = meta["viewport"]
    sc = meta["scale"]
    f = meta["boxes"][focus]
    c = meta["boxes"].get(context) or {"x": 0, "width": w}
    x0 = max(0, c["x"] - EDGE_CSS / 2)
    x1 = min(w, c["x"] + c["width"] + EDGE_CSS / 2)
    bottom = f["y"] + f["height"] + EDGE_CSS
    y0 = max(0, bottom - height_css)
    return f"{int((x1 - x0) * sc)}x{int((bottom - y0) * sc)}+{int(x0 * sc)}+{int(y0 * sc)}"


def load_boxes(png):
    with open(os.path.splitext(png)[0] + ".json") as f:
        return json.load(f)["boxes"]


def css_geom(boxes, scale, pad_css, size_px, top_snap_css=0):
    """Pixel geometry of the union of CSS boxes, padded and clamped to the image.

    If the top edge lands within top_snap_css of the page top, it snaps to 0 and the
    left edge snaps to 0 too, so a full-width page header is kept whole instead of
    being cut through its text.
    """
    top = max(0, min(b["y"] for b in boxes) - pad_css)
    header_kept = top < top_snap_css
    x0 = 0 if header_kept else max(0, min(b["x"] for b in boxes) - pad_css) * scale
    y0 = (0 if header_kept else top) * scale
    x1 = min(size_px[0], (max(b["x"] + b["width"] for b in boxes) + pad_css) * scale)
    y1 = min(size_px[1], (max(b["y"] + b["height"] for b in boxes) + pad_css) * scale)
    x0, y0, x1, y1 = (int(v) for v in (x0, y0, x1, y1))
    return f"{x1 - x0}x{y1 - y0}+{x0}+{y0}"


def storyboard_geom(raw, above_css=STORY_ABOVE_CSS):
    """What moves (button, toast, cursor path), widened to the context element and lifted
    above_css so the tiles show the form around the action. Pixels of the raw video."""
    meta = motion.meta_for(raw)
    scale, context_box = meta["scale"], meta.get("context_box")
    w, h, x, y = crop.parse_geometry(crop.video_change_geom(raw, keep_context=False, pad=12, min_size="100x100",
                                                            aspect="1:4-8:1", snap=False))
    moved = {"x": x / scale, "y": y / scale - above_css, "width": w / scale, "height": h / scale + above_css}
    boxes_css = [moved] + ([{"x": context_box["x"], "y": moved["y"], "width": context_box["width"], "height": 1}]
                           if context_box else [])
    return css_geom(boxes_css, scale, 12, (int(meta["vw"] * scale), int(meta["vh"] * scale)))


def card_input(path, dst, title, side, sha_pair):
    base, change = sha_pair
    sha = base if side == "base" else change
    geom = crop.geometry(crop.content_box([path]))
    cropped = os.path.splitext(path)[0] + "-content.png"
    crop.apply(geom, [(path, cropped)])
    body = house.img_tag(cropped, title).replace("<img", '<img class="shot"')
    house.card_png(dst, title, f"Input screenshot of {house.side_label(side, sha)}.", body, base, change,
                   os.path.relpath(path), house.now())


def capture_side(side, s, co, w, flow, expect, plan, session, state):
    """All browser work for one side, in its own agent-browser session. Returns a result dict."""
    vw, vh = s.get("viewport", [1280, 800])
    sc = s.get("scale", 2)
    ctx = s.get("context")
    hide = s.get("redact_selectors") or []
    measure = [m for m in (ctx,) if m]
    result = {"states": [], "viewports": []}
    t = time.monotonic()
    with ab.use(session, state):
        try:
            capture.capture(co.url(side), w(f"{side}.png"), vw, vh, sc, measure=measure, redact_selectors=hide)
            if side == "change":
                if "followup" in co.names:
                    capture.capture(co.url("followup"), w("followup.png"), vw, vh, sc, redact_selectors=hide)
                states = s.get("states")
                if states and "states.png" in plan:
                    for v in states["values"]:
                        p = w(f"state-{v}.png")
                        capture.capture(co.url("change", f"{states['param']}={v}"), p, vw, vh, sc, measure=measure,
                                        redact_selectors=hide)
                        result["states"].append((str(v).capitalize(), p))
                vps = s.get("viewports")
                if vps and "viewports.png" in plan:
                    for vw_i, vh_i in vps["sizes"]:
                        p = w(f"vp-{vw_i}.png")
                        capture.capture(co.url("change"), p, vw_i, vh_i, sc, full=True,
                                        measure=[m for m in (vps["focus"], ctx) if m], redact_selectors=hide)
                        with open(os.path.splitext(p)[0] + ".json") as f:
                            meta = json.load(f)
                        result["viewports"].append((f"{vw_i} x {vh_i}", p,
                                                    viewport_window(meta, vps["focus"], ctx,
                                                                    vps.get("height_css", 300))))
            tail = s.get("tail_ms", FLOW_TAIL_MS if s.get("steps") else 2600)
            result["meta"] = record.record_flow(co.url(side), flow, w(f"{side}-raw.mp4"), vw, vh, sc, context=ctx,
                                                watch_text=expect, side=side, tail_ms=tail,
                                                redact_selectors=hide)
        finally:
            ab.close()
    result["seconds"] = round(time.monotonic() - t, 2)
    return result


def capture_all(s, co, w, flow, expect, plan, state):
    """Base and change in parallel, each in its own browser session."""
    root = ab.default_session()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {side: pool.submit(capture_side, side, s, co, w, flow, expect, plan, f"{root}-{side}", state)
                   for side in ("base", "change")}
        return {side: f.result() for side, f in futures.items()}


MOMENTS = (("change_before", "change, before the flow"), ("change_after", "change, after the flow started"),
           ("base_after", "base, after the flow started"))


def seen_from(results, expect):
    seen = {}
    for text in expect:
        seen[("change_before", text)] = results["change"]["meta"]["before_text"].get(text)
        seen[("change_after", text)] = results["change"]["meta"]["seen_text"].get(text)
        seen[("base_after", text)] = results["base"]["meta"]["seen_text"].get(text)
    return seen


def expect_assertions(expect, seen):
    return [{"text": text, "side": label, "moment": moment, "found": seen.get((moment, text))}
            for text in expect for moment, label in MOMENTS]


def expect_verdict(assertions, before_ok=False, base_failures=()):
    """(passed, reason). Each text must show on change after the flow, must not show on base after
    the flow, and must not show on change before the flow (unless before_ok: the scenario says the
    claim is about a text that stays while the flow runs; base must still differ). A base step that
    failed makes the base run unfit to compare."""
    texts = list(dict.fromkeys(a["text"] for a in assertions))
    if not texts:
        return None, ""
    found = {(a["moment"], a["text"]): a["found"] for a in assertions}
    for text in texts:
        if not found.get(("change_after", text)):
            return False, f"{text!r} is not on the change page after the flow."
    if base_failures:
        return None, ("These base steps did not run, so base is not a fair comparison: "
                      + "; ".join(base_failures) + ". Mark a step that may fail on base with \"base\": {\"may_fail\": true}.")
    for text in texts:
        if found.get(("base_after", text)):
            return None, f"{text!r} also shows on base after the flow, so it does not isolate this change."
        if found.get(("change_before", text)) and not before_ok:
            return None, (f"{text!r} was on the change page before the flow, so the flow did not make it show. "
                          "Set \"text_may_show_before\": true only if the claim is not about the flow making it show.")
    return True, ""


def base_step_failures(flow, base_events):
    """Labels of visible base steps that failed and are not marked base.may_fail."""
    out = []
    for item, ev in zip(flow, base_events):
        if ev["kind"] in flows.VISIBLE and not ev["ok"] and not item["base_step"].get("may_fail"):
            out.append(item["label"])
    return out


def step_lines(events):
    out = []
    for i, e in enumerate(events, 1):
        state = "ok" if e["ok"] else f"failed: {e.get('error', 'no result')}"
        out.append(f"{i}. {e['label']} ({state})")
    return out


def build(s, out, work, all_media=False, no_cache=False):
    t_start = time.monotonic()
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    os.environ["PROVE_CARD_DIR"] = os.path.join(work, "cards")
    vw, vh = s.get("viewport", [1280, 800])
    sc = s.get("scale", 2)
    ctx = s.get("context")
    click = s.get("click") or {}
    if not (s.get("steps") or click.get("change_selector")):
        raise RuntimeError("Scenario ui needs steps, or click.change_selector")
    flow = flows.normalize(s["steps"]) if s.get("steps") else flows.from_click(click)
    expect = flows.expect_texts(s, flow)
    plan = media_plan(s, all_media)
    label = click.get("label") or s.get("label") or next(f["label"] for f in flow if f["anchor"])
    claim_text = click.get("claim") or s.get("claim") or ""
    title = claim_text or label
    manifest = []
    timings = {}

    def add(name, title, what, placement="none", kind="screenshot", source=None):
        manifest.append({"file": name, "title": title, "what": what, "placement": placement, "type": kind,
                         "source": source})

    def w(name):
        return os.path.join(work, name)

    def o(name):
        return os.path.join(out, name)

    names = [n for n in ("base", "change", "followup") if n in s["refs"]]
    state_file = authstate.resolve(s["auth"], s["repo"]) if s.get("auth") else None
    state_copy = None
    t = time.monotonic()
    try:
        with scenario.Checkouts(s, w("wt"), names, cache=not no_cache) as co:
            timings.update(co.timings)
            timings["servers_s"] = round(time.monotonic() - t, 2)
            if state_file:
                state_copy = authstate.for_origins(state_file, [co.origin(n) for n in names], None)
            t = time.monotonic()
            results = capture_all(s, co, w, flow, expect, plan, state_copy)
            timings["capture_s"] = round(time.monotonic() - t, 2)
            timings.update({f"capture_{side}_s": r["seconds"] for side, r in results.items()})
            B, C = co.sha("base"), co.sha("change")
            F = co.sha("followup") if "followup" in names else None
            checkout_status, caveats = dict(co.status), list(co.caveats)
    finally:
        authstate.discard(state_copy)
    seen = seen_from(results, expect)
    assertions = expect_assertions(expect, seen)
    change_meta, base_meta = results["change"]["meta"], results["base"]["meta"]
    passed, reason = expect_verdict(assertions, bool(s.get("text_may_show_before")),
                                    base_step_failures(flow, base_meta["events"]))
    pair = (B, C)
    raw_c, raw_b = w("change-raw.mp4"), w("base-raw.mp4")
    a = motion.analyze(raw_c)
    settle = a["settle"] - a["click"]

    def r_inputs():
        card_input(w("base.png"), o("before.png"), "Base screenshot", "base", pair)
        card_input(w("change.png"), o("after.png"), "Change screenshot", "change", pair)

    def r_wipe():
        size_px = (int(vw * sc), int(vh * sc))
        geom = (css_geom([load_boxes(w("base.png"))[ctx], load_boxes(w("change.png"))[ctx]], sc, 12, size_px,
                         top_snap_css=PAGE_TOP_SNAP_CSS) if ctx else "content")
        wipe.build(w("base.png"), w("change.png"), o("wipe.gif"), B, C, geom, "Before and after",
                   "base.png + change.png",
                   subtitle=f"{s['name']}. Both commits cropped to the same region (the <code>"
                            f"{house.esc(ctx or 'page')}</code> of either). Where one page is shorter, the grey "
                            "below it is the real page.")

    def r_action():
        act = crop.video_change_geom(raw_c, pad=12, aspect="1:1-16:9")
        clip = w("action-clip.mp4")
        motion.render(raw_c, clip, act)
        what = "click" if len(flow) == 1 else "flow"
        subtitle = (f"Recorded on {house.side_label('change', C)} with a visible cursor. "
                    f"The {'click' if what == 'click' else 'anchor step'} plays at 0.5&times; speed; "
                    f"the page settles {settle:.1f} s after it.")
        motion.card(clip, o("action.gif"), title, subtitle, "", B, C, os.path.relpath(raw_c), gif=True)

    def r_twin():
        twin.render(raw_b, raw_c, o("twin.mp4"), B, C, f"{label}: base vs change")

    def r_story():
        if s.get("steps"):
            specs = flows.keyframes(change_meta["events"], change_meta["anchor_s"], settle)
        else:
            specs = click.get("storyboard", storyboard.DEFAULT_STEPS)
        storyboard.build(raw_c, o("storyboard.png"), storyboard_geom(raw_c), specs, f"{label}: keyframes", B, C,
                         cols=2 if len(specs) > 4 else 1, workdir=w("storyboard"),
                         anchor_name="click" if len(flow) == 1 else "anchor step")

    def r_states():
        shots = results["change"]["states"]
        specs = [f"{lab}={p}#{css_geom([load_boxes(p)[ctx]], sc, 12, (int(vw * sc), int(vh * sc)))}"
                 if ctx else f"{lab}={p}" for lab, p in shots]
        grid.build(o("states.png"), specs, B, C, "States", geom="none" if ctx else "auto", aspect="1:1-16:9",
                   pad=24, workdir=w("states"))

    def r_viewports():
        grid.build(o("viewports.png"), [f"{lab}={p}#{g}" for lab, p, g in results["change"]["viewports"]], B, C,
                   "Viewports", subtitle=f"The focus element at each width, on {house.side_label('change', C)}.",
                   same_scale=True, pixel_scale=sc, workdir=w("viewports"))

    def r_boxes():
        fu = s.get("followup", {})
        found = boxes.snap_boxes(boxes.find_boxes(w("change.png"), w("followup.png"), sc), w("followup.png"), sc)
        boxes.render(w("change.png"), w("followup.png"), o("diff-boxes.png"), found, C, F,
                     fu.get("title", "Follow-up commit: what changed"), fu.get("legend"), workdir=work)

    jobs = [("inputs", r_inputs), ("action.gif", r_action), ("twin.mp4", r_twin)]
    jobs += [(n, fn) for n, fn in (("wipe.gif", r_wipe), ("storyboard.png", r_story), ("states.png", r_states),
                                   ("viewports.png", r_viewports), ("diff-boxes.png", r_boxes)) if n in plan]
    t = time.monotonic()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=RENDER_WORKERS) as pool:
            futures = {name: pool.submit(timed, fn) for name, fn in jobs}
            for name, f in futures.items():
                timings[f"render_{name}_s"] = f.result()
    finally:
        house.close_cards()
    timings["render_s"] = round(time.monotonic() - t, 2)

    add("before.png", "Base screenshot", "Input only: base commit, content-cropped.", source="work/base.png")
    add("after.png", "Change screenshot", "Input only: change commit, content-cropped.", source="work/change.png")
    add("action.gif", title, "Recorded flow with cursor, ripple and outline; one crop keeps the card.",
        "hero", source="work/change-raw.mp4")
    add("twin.mp4", f"{label}: base vs change", "Both commits side by side at one scale, lined up on the anchor step.",
        "inline", "video", source="work/base-raw.mp4")
    if "wipe.gif" in plan:
        add("wipe.gif", "Wipe: change left of the line, base right", "Divider sweeps from base to change and back.",
            "details", source="work/base.png")
    if "storyboard.png" in plan:
        add("storyboard.png", f"{label}: keyframes", "Numbered keyframes of the flow, one crop for all.",
            "details", source="work/change-raw.mp4")
    if "states.png" in plan:
        add("states.png", "States", "Every ?state= value on the change commit, each cropped to its card.", "details",
            source=f"work/state-{s['states']['values'][0]}.png")
    if "viewports.png" in plan:
        add("viewports.png", "Viewports", "Each width cropped to the focus element.", "details",
            source=f"work/vp-{s['viewports']['sizes'][0][0]}.png")
    if "diff-boxes.png" in plan:
        fu = s.get("followup", {})
        add("diff-boxes.png", fu.get("title", "Follow-up commit"),
            f"Follow-up commit {F} compared with {C}; stamped with that pair.", "details", source="work/followup.png")

    observation = f"{title.rstrip('.')}. The page settles about {settle:.1f} s after the anchor step."
    observations = [observation]
    if len(flow) > 1:
        observations.append("Steps on change: " + "; ".join(step_lines(change_meta["events"])) + ".")
    notes = ["The GIF plays the anchor step at 0.5x speed."]
    failed_base = [e for e in base_meta["events"] if not e["ok"] and e["kind"] in flows.VISIBLE]
    if failed_base:
        notes.append("On base, these steps could not run: " + "; ".join(e["label"] for e in failed_base) + ".")
    if F:
        notes.append(f"Follow-up commit `{F}` (on top of `{C}`) changes only the boxed regions.")
    skipped = [n for n in OPTIONAL if n not in plan]
    caveat = "I checked only what the browser shows. No test suite ran for this UI change."
    if caveats:
        caveat += " " + " ".join(caveats)
    timings["total_s"] = round(time.monotonic() - t_start, 2)
    result = {
        "kind": "ui",
        "scenario": s["_file"],
        "name": s.get("name", ""),
        "base": {"sha": B, "ref": s["refs"]["base"]},
        "change": {"sha": C, "ref": s["refs"].get("change")},
        "followup": F,
        "captured_at": house.now(),
        "claim": claim_text,
        "observations": observations,
        "assertions": assertions,
        "passed": passed,
        "not_proven_reason": reason,
        "caveat": caveat,
        "notes": notes,
        "settle_s": round(settle, 3),
        "viewport": [vw, vh],
        "scale": sc,
        "steps": flows.public(flow),
        "events": {"change": change_meta["events"], "base": base_meta["events"]},
        "auth": {"used": bool(state_file)},
        "checkouts": checkout_status,
        "media_skipped": skipped,
        "timings": timings,
        "artifacts": manifest,
    }
    result = redact.auth(result)
    for side in ("base", "change"):
        meta_path = w(f"{side}-raw.json")
        with open(meta_path) as f:
            meta = redact.auth(json.load(f))
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
    with open(o("media-manifest.json"), "w") as f:
        json.dump(result, f, indent=2)
    return result


def timed(fn):
    t = time.monotonic()
    fn()
    return round(time.monotonic() - t, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default=None)
    ap.add_argument("--all-media", action="store_true", help="also build every details card, wipe.gif included")
    ap.add_argument("--no-cache", action="store_true", help="temporary base worktree; stop every server at the end")
    o = ap.parse_args()
    scenario.procs.install_sigterm()
    s = scenario.load(o.scenario)
    out = os.path.abspath(o.out)
    result = build(s, out, os.path.abspath(o.work or os.path.join(out, "work")), o.all_media, o.no_cache)
    for a in result["artifacts"]:
        print(a["file"])


if __name__ == "__main__":
    main()
