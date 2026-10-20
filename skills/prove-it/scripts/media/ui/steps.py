"""Multi-step UI flows: normalize scenario steps and play them in one browser session.

A step is one JSON object with one action key:

    {"goto": "/settings"}
    {"click": "#save"}                        CSS selector
    {"click": {"role": "button", "name": "Save"}}   also {"text"}, {"label"}, {"placeholder"}, {"testid"}, {"css"}
    {"fill": "#name", "text": "Sam"}          or "text_env": "VAR" (value read from the environment, never stored)
    {"press": "Enter"}                        optional "target" to focus first
    {"select": "#role", "value": "Engineer"}
    {"wait_text": "Saved", "timeout_ms": 5000}
    {"wait_ms": 500}
    {"expect_text": "Saved", "timeout_ms": 3000}

Optional keys on any step: "label" (storyboard caption), "anchor": true (the moment the
GIF slows down and the twin video lines up on; default: the last click), and "base": {...}
(keys that replace this step's keys on the base side, for example a different selector).
"""
import json
import os
import re
import time

ACTIONS = ("goto", "click", "fill", "press", "select", "wait_text", "wait_ms", "expect_text")
VISIBLE = {"goto", "click", "fill", "press", "select"}
TARGETED = {"click", "fill", "select"}
DEFAULT_WAIT_TEXT_MS = 5000
DEFAULT_EXPECT_MS = 3000
POLL_S = 0.1
TAP_TO_ACT_S = 0.09
KEYFRAME_AFTER_CLICK_S = 0.35
MAX_KEYFRAMES = 8
SECRET = "<redacted>"
SECRET_TARGET_RE = re.compile(r"(?i)pass(word|wd)?|secret|token|api[_-]?key|otp|pin\b|ssn|card")


class StepError(RuntimeError):
    pass


def action_of(step):
    found = [k for k in ACTIONS if k in step]
    if len(found) != 1:
        raise StepError(f"each step needs exactly one of {', '.join(ACTIONS)}: {json.dumps(step)}")
    return found[0]


def target_spec(value):
    if isinstance(value, str) and value:
        return {"css": value}
    if isinstance(value, dict) and value:
        allowed = {"css", "role", "name", "text", "label", "placeholder", "testid"}
        bad = set(value) - allowed
        if bad or ("name" in value and "role" not in value):
            raise StepError(f"target must be a CSS string or one of {sorted(allowed)} (name needs role): {value}")
        return dict(value)
    raise StepError(f"target must be a CSS selector string or an object: {value!r}")


def describe(spec):
    if "css" in spec:
        return spec["css"]
    if "role" in spec:
        return f"{spec['role']} {spec.get('name', '')!r}".strip()
    key = next(iter(spec))
    return f"{key} {spec[key]!r}"


def default_label(kind, step):
    if kind in TARGETED:
        spec = target_spec(step[kind])
        name = spec.get("name") or spec.get("text") or spec.get("label") or spec.get("placeholder") or describe(spec)
        return {"click": f"Click {name}", "fill": f"Fill {name}", "select": f"Select {step.get('value', '')}"}[kind]
    if kind == "goto":
        return f"Open {step['goto']}"
    if kind == "press":
        return f"Press {step['press']}"
    if kind in ("wait_text", "expect_text"):
        return f"{step[kind]} shows"
    return f"Wait {step['wait_ms']} ms"


def normalize(steps):
    """Validate steps; return [{kind, step, base_step, label, anchor}] with the anchor set on one step."""
    if not isinstance(steps, list) or not steps:
        raise StepError("steps must be a non-empty list")
    out = []
    for raw in steps:
        if not isinstance(raw, dict):
            raise StepError(f"each step must be an object: {raw!r}")
        kind = action_of(raw)
        step = {k: v for k, v in raw.items() if k != "base"}
        base_step = {**step, **(raw.get("base") or {})}
        for s in (step, base_step):
            if action_of(s) != kind:
                raise StepError(f"a base override must keep the action {kind!r}: {json.dumps(raw)}")
            if kind in TARGETED:
                target_spec(s[kind])
            if kind == "fill" and "text" not in s and "text_env" not in s:
                raise StepError(f"fill needs text or text_env: {describe(target_spec(s['fill']))}")
            if kind == "fill" and "text" in s and secret_like(s["fill"], s["text"]):
                raise StepError(f"fill {describe(target_spec(s['fill']))} has a literal value that looks like a "
                                "password or token. Put it in an environment variable and use \"text_env\".")
            if kind == "select" and "value" not in s:
                raise StepError(f"select needs value: {json.dumps(raw)}")
            if kind == "wait_ms" and not isinstance(s["wait_ms"], (int, float)):
                raise StepError(f"wait_ms must be a number: {json.dumps(raw)}")
        out.append({"kind": kind, "step": step, "base_step": base_step,
                     "label": raw.get("label") or default_label(kind, step), "anchor": bool(raw.get("anchor"))})
    if not any(s["anchor"] for s in out):
        pick = [s for s in out if s["kind"] == "click"] or [s for s in out if s["kind"] in VISIBLE] or out
        pick[-1]["anchor"] = True
    return out


def secret_like(target, text):
    """A fill that must use text_env: a password-like target, or a value that looks like a token."""
    if SECRET_TARGET_RE.search(json.dumps(target)):
        return True
    text = str(text)
    if re.search(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.", text) or re.match(r"(?i)(sk|pk|ghp|gho|xox[abp]|AKIA)[-_]", text):
        return True
    return (len(text) >= 20 and " " not in text and re.search(r"[A-Za-z]", text) is not None
            and re.search(r"\d", text) is not None)


def from_click(click):
    """The single-click scenario form as one step, so both forms share one recorder."""
    step = {"click": click["change_selector"], "label": click.get("label") or "Click", "anchor": True}
    if click.get("base_selector"):
        step["base"] = {"click": click["base_selector"]}
    return normalize([step])


def expect_texts(scenario, flow):
    texts = []
    for value in ((scenario.get("click") or {}).get("expect_text"), scenario.get("expect_text")):
        texts += [value] if isinstance(value, str) else list(value or [])
    texts += [s["step"]["expect_text"] for s in flow if s["kind"] == "expect_text"]
    return list(dict.fromkeys(texts))


def public(flow):
    """Steps as they may appear in a manifest: no fill value is ever shown."""
    out = []
    for s in flow:
        step = dict(s["step"])
        if s["kind"] == "fill":
            step["text"] = SECRET
        out.append({"label": s["label"], "anchor": s["anchor"], **step})
    return out


class Runner:
    """Plays a normalized flow on one side through ab (the current thread's session)."""

    def __init__(self, ab, side, base_url, move_ms=800, outline_ms=900, strict=True, on_page=None, watch=()):
        self.ab, self.side, self.base_url = ab, side, base_url.rstrip("/")
        self.move_ms, self.outline_ms, self.strict = move_ms, outline_ms, strict
        self.on_page = on_page
        self.seen = {t: False for t in watch}
        self.events = []

    def resolve(self, value):
        spec = target_spec(value)
        out = self.ab.eval_js(f"window.__proveit.resolve({json.dumps(spec)})").strip()
        try:
            sel = json.loads(out)
        except ValueError:
            sel = out
        sel = sel if isinstance(sel, str) else ""
        if not sel:
            raise StepError(f"{self.side}: no visible element for {describe(spec)}")
        return sel

    def text_visible(self, text):
        return self.ab.has_visible_text(text)

    def poll(self, text, timeout_ms):
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self.text_visible(text):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(POLL_S)

    def watch_all(self):
        for text in [t for t, found in self.seen.items() if not found]:
            self.seen[text] = self.text_visible(text)

    def tail(self, ms):
        deadline = time.monotonic() + ms / 1000
        while time.monotonic() < deadline:
            self.watch_all()
            time.sleep(POLL_S if self.seen else max(0, deadline - time.monotonic()))

    def aim_and_tap(self, sel):
        self.ab.eval_js(f"window.__proveit.aim({json.dumps(sel)}, {self.move_ms})")
        time.sleep(self.move_ms / 1000 + 0.005)
        self.ab.eval_js(f"window.__proveit.tap({json.dumps(sel)}, {self.outline_ms})")
        time.sleep(TAP_TO_ACT_S)

    def run_step(self, item):
        kind = item["kind"]
        step = item["step"] if self.side == "change" else item["base_step"]
        ev = {"label": item["label"], "kind": kind, "anchor": item["anchor"], "start": time.monotonic(), "ok": True}
        act = None
        try:
            if kind == "goto":
                url = step["goto"] if "://" in step["goto"] else self.base_url + "/" + step["goto"].lstrip("/")
                self.ab.ab("open", url)
                act = time.monotonic()
                if self.on_page:
                    self.on_page()
            elif kind == "click":
                sel = self.resolve(step["click"])
                self.aim_and_tap(sel)
                act = time.monotonic()
                self.ab.ab("click", sel)
                self.ab.eval_js("window.__proveit && window.__proveit.away()")
            elif kind == "fill":
                sel = self.resolve(step["fill"])
                text = os.environ.get(step["text_env"], "") if "text_env" in step else str(step["text"])
                if "text_env" in step and not text:
                    raise StepError(f"fill text_env {step['text_env']} is not set")
                self.aim_and_tap(sel)
                act = time.monotonic()
                try:
                    self.ab.ab("fill", sel, text, secret=True)
                except RuntimeError:
                    raise StepError(f"fill {describe(target_spec(step['fill']))} failed") from None
            elif kind == "select":
                sel = self.resolve(step["select"])
                self.aim_and_tap(sel)
                act = time.monotonic()
                self.ab.ab("select", sel, step["value"])
            elif kind == "press":
                if step.get("target"):
                    self.ab.ab("focus", self.resolve(step["target"]))
                act = time.monotonic()
                self.ab.ab("press", step["press"])
            elif kind == "wait_ms":
                time.sleep(step["wait_ms"] / 1000)
            elif kind in ("wait_text", "expect_text"):
                text = step[kind]
                default = DEFAULT_WAIT_TEXT_MS if kind == "wait_text" else DEFAULT_EXPECT_MS
                found = self.poll(text, step.get("timeout_ms", default))
                act = time.monotonic() if found else None
                ev["found"] = found
                if text in self.seen:
                    self.seen[text] = self.seen[text] or found
                if not found:
                    ev["ok"] = False
                    ev["error"] = f"{text!r} did not show within {step.get('timeout_ms', default)} ms"
        except (StepError, RuntimeError) as exc:
            ev["ok"], ev["error"] = False, str(exc).splitlines()[0]
            if self.strict:
                raise StepError(f"{self.side} step {len(self.events) + 1} ({item['label']}): {exc}") from exc
        ev["act"] = act or time.monotonic()
        ev["end"] = time.monotonic()
        self.events.append(ev)
        if kind not in ("wait_text", "expect_text"):
            self.watch_all()
        return ev

    def run(self, flow):
        """Play every step. Change side (strict): a failed action stops the run. Base side: a failed
        action is recorded and the flow goes on. A text that does not show is recorded, never raised."""
        for item in flow:
            self.run_step(item)
        return self.events


def relative_events(events):
    """Times in seconds from the start of the first visible step, which is when the video first moves."""
    first = next((e for e in events if e["kind"] in VISIBLE and e["ok"]), events[0] if events else None)
    t0 = first["start"] if first else 0
    out = []
    for e in events:
        r = {k: v for k, v in e.items() if k not in ("start", "act", "end")}
        r.update(start_s=round(e["start"] - t0, 3), act_s=round(e["act"] - t0, 3), end_s=round(e["end"] - t0, 3))
        out.append(r)
    anchor = next((r for r in out if r["anchor"]), out[-1] if out else None)
    return out, (anchor["act_s"] if anchor else 0.0)


def keyframes(events, anchor_s, settle_rel=None):
    """Storyboard specs "Label@seconds-from-anchor", one per step that shows something."""
    specs = []
    first = next((e for e in events if e["kind"] in VISIBLE and e["ok"]), None)
    if first:
        specs.append(f"Start@{first['start_s'] - anchor_s - 0.3:.3f}")
    for i, e in enumerate(events):
        if not e["ok"] or e["kind"] == "wait_ms":
            continue
        if e["kind"] == "click":
            nxt = events[i + 1]["start_s"] if i + 1 < len(events) else e["act_s"] + KEYFRAME_AFTER_CLICK_S
            t = min(e["act_s"] + KEYFRAME_AFTER_CLICK_S, max(e["act_s"] + 0.05, nxt - 0.02))
        elif e["kind"] in ("wait_text", "expect_text"):
            t = e["end_s"] + 0.1
        else:
            t = e["end_s"] + 0.1
        specs.append(f"{e['label'].replace('@', ' at ')}@{t - anchor_s:.3f}")
    if settle_rel is not None and specs and settle_rel - float(specs[-1].rpartition("@")[2]) > 0.3:
        specs.append("Settled@settle")
    return specs[:MAX_KEYFRAMES - 1] + specs[-1:] if len(specs) > MAX_KEYFRAMES else specs
