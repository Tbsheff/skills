import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401

import auth  # noqa: E402
import build  # noqa: E402
import redact  # noqa: E402
import steps  # noqa: E402


class StepsTest(unittest.TestCase):
    def test_normalize_picks_last_click_as_anchor(self):
        flow = steps.normalize([{"fill": "#a", "text": "x"}, {"click": "#b"}, {"click": {"role": "button", "name": "Save"}},
                                {"wait_text": "Saved"}])
        self.assertEqual([f["anchor"] for f in flow], [False, False, True, False])

    def test_explicit_anchor_and_base_override(self):
        flow = steps.normalize([{"click": "#new", "base": {"click": "button.old"}, "anchor": True}, {"click": "#b"}])
        self.assertTrue(flow[0]["anchor"])
        self.assertFalse(flow[1]["anchor"])
        self.assertEqual(flow[0]["base_step"]["click"], "button.old")
        self.assertEqual(flow[0]["step"]["click"], "#new")

    def test_invalid_steps(self):
        for bad in ([], [{"click": "#a", "fill": "#b"}], [{"fill": "#a"}], [{"select": "#a"}],
                    [{"click": {"name": "Save"}}], [{"click": "#a", "base": {"fill": "#a", "text": "x"}}],
                    [{"hover": "#a"}]):
            with self.assertRaises(steps.StepError, msg=bad):
                steps.normalize(bad)

    def test_single_click_form(self):
        flow = steps.from_click({"change_selector": "#save", "base_selector": "button.save", "label": "Click Save"})
        self.assertEqual(len(flow), 1)
        self.assertEqual(flow[0]["base_step"]["click"], "button.save")
        self.assertEqual(flow[0]["label"], "Click Save")

    def test_expect_texts_merge(self):
        s = {"click": {"expect_text": "A"}, "expect_text": ["B"]}
        flow = steps.normalize([{"click": "#x"}, {"expect_text": "C"}, {"expect_text": "A"}])
        self.assertEqual(steps.expect_texts(s, flow), ["A", "B", "C"])

    def test_public_masks_secrets(self):
        flow = steps.normalize([{"fill": "#password", "text_env": "X"}, {"fill": "#name", "text": "Sam"}])
        out = steps.public(flow)
        self.assertEqual([o["text"] for o in out], [steps.SECRET, steps.SECRET])

    def test_relative_events_and_keyframes(self):
        flow = steps.normalize([{"wait_ms": 100}, {"fill": "#a", "text": "x"}, {"click": "#b"}, {"wait_text": "Saved"}])
        t = 100.0
        events = [
            {"label": "w", "kind": "wait_ms", "anchor": False, "ok": True, "start": t, "act": t + .1, "end": t + .1},
            {"label": "Fill", "kind": "fill", "anchor": False, "ok": True, "start": t + .1, "act": t + 1, "end": t + 1},
            {"label": "Save", "kind": "click", "anchor": True, "ok": True, "start": t + 1, "act": t + 2, "end": t + 2},
            {"label": "Saved", "kind": "wait_text", "anchor": False, "ok": True, "start": t + 2, "act": t + 2.5,
             "end": t + 2.5},
        ]
        rel, anchor = steps.relative_events(events)
        self.assertAlmostEqual(rel[1]["start_s"], 0.0)
        self.assertAlmostEqual(anchor, 1.9)
        specs = steps.keyframes(rel, anchor, settle_rel=2.0)
        names = [s.rpartition("@")[0] for s in specs]
        self.assertEqual(names, ["Start", "Fill", "Save", "Saved", "Settled"])
        self.assertLess(float(specs[0].rpartition("@")[2]), 0)
        self.assertEqual(len(flow), 4)

    def test_keyframes_skip_failed(self):
        rel = [{"label": "Click", "kind": "click", "anchor": True, "ok": False, "start_s": 0, "act_s": 1, "end_s": 1}]
        self.assertEqual(steps.keyframes(rel, 1.0), [])


class VerdictTest(unittest.TestCase):
    def verdict(self, before, after, base, before_ok=False, base_failures=()):
        seen = {("change_before", "Saved"): before, ("change_after", "Saved"): after, ("base_after", "Saved"): base}
        return build.expect_verdict(build.expect_assertions(["Saved"], seen), before_ok, base_failures)[0]

    def test_pass_only_when_absent_on_base_and_before(self):
        self.assertIs(self.verdict(False, True, False), True)

    def test_text_on_base_is_not_proven(self):
        self.assertIsNone(self.verdict(False, True, True))
        self.assertIsNone(self.verdict(True, True, True))

    def test_text_before_flow_is_not_proven(self):
        self.assertIsNone(self.verdict(True, True, False))
        self.assertIs(self.verdict(True, True, False, before_ok=True), True)
        self.assertIsNone(self.verdict(True, True, True, before_ok=True), "base must still differ")

    def test_missing_on_change_fails(self):
        self.assertIs(self.verdict(False, False, False), False)
        self.assertEqual(build.expect_verdict([]), (None, ""))

    def test_failed_base_step_is_not_proven(self):
        self.assertIsNone(self.verdict(False, True, False, base_failures=["Open /settings"]))

    def test_base_step_failures_respects_may_fail(self):
        flow = steps.normalize([{"goto": "/a"}, {"click": "#new", "base": {"may_fail": True}}, {"click": "#b"}])
        events = [{"kind": "goto", "ok": False}, {"kind": "click", "ok": False}, {"kind": "click", "ok": True}]
        self.assertEqual(build.base_step_failures(flow, events), ["Open /a"])


class SecretFillTest(unittest.TestCase):
    def test_refuses_literal_secrets(self):
        for step in ({"fill": "#password", "text": "hunter2"}, {"fill": {"label": "API token"}, "text": "zq9"},
                     {"fill": "#name", "text": "sk-abcdef0123456789"},
                     {"fill": "#name", "text": "a1b2c3d4e5f6g7h8i9j0k1"}):
            with self.assertRaises(steps.StepError) as ctx:
                steps.normalize([step])
            self.assertNotIn(step["text"], str(ctx.exception))
        steps.normalize([{"fill": "#password", "text_env": "APP_PASSWORD"}, {"fill": "#name", "text": "Sam Lee"}])

    def test_fill_failure_hides_value(self):
        os.environ["PI_TEST_SECRET"] = "s3cret-value-123"

        class FakeAb:
            def eval_js(self, code):
                return json.dumps("[data-proveit-id=\"t1\"]") if "resolve" in code else "true"

            def ab(self, *args, secret=False):
                if args[0] == "fill":
                    raise RuntimeError("failed" if secret else f"failed: {args}")
                return ""

            def has_visible_text(self, text):
                return False

        flow = steps.normalize([{"fill": "#pw-field", "text_env": "PI_TEST_SECRET"}])
        runner = steps.Runner(FakeAb(), "base", "http://x", move_ms=0, strict=False)
        runner.run(flow)
        blob = json.dumps(steps.relative_events(runner.events)[0])
        self.assertNotIn("s3cret-value-123", blob)
        self.assertIn("failed", runner.events[0]["error"])
        strict = steps.Runner(FakeAb(), "change", "http://x", move_ms=0, strict=True)
        with self.assertRaises(steps.StepError) as ctx:
            strict.run(flow)
        self.assertNotIn("s3cret-value-123", str(ctx.exception))
        os.environ.pop("PI_TEST_SECRET")

    def test_public_masks_every_fill(self):
        out = steps.public(steps.normalize([{"fill": "#name", "text": "Sam Lee"}]))
        self.assertEqual(out[0]["text"], steps.SECRET)


class MediaPlanTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("PROVE_IT_ALL_MEDIA", None)

    def test_default_is_lazy(self):
        plan = build.media_plan({"refs": {"base": "x", "change": None}, "click": {"change_selector": "#a"}})
        self.assertEqual(plan, set(build.ALWAYS))

    def test_asked_cards(self):
        s = {"refs": {"base": "x", "change": None, "followup": "y"}, "states": {"param": "s", "values": ["a"]},
             "steps": [{"click": "#a"}], "media": ["wipe.gif"]}
        self.assertEqual(build.media_plan(s) - set(build.ALWAYS),
                         {"states.png", "diff-boxes.png", "storyboard.png", "wipe.gif"})

    def test_all_media(self):
        s = {"refs": {"base": "x", "change": None}}
        self.assertEqual(build.media_plan(s, all_media=True), set(build.ALWAYS) | {"wipe.gif", "storyboard.png"})
        os.environ["PROVE_IT_ALL_MEDIA"] = "1"
        try:
            self.assertIn("wipe.gif", build.media_plan(s))
        finally:
            os.environ.pop("PROVE_IT_ALL_MEDIA")

    def test_unknown_name(self):
        with self.assertRaises(RuntimeError):
            build.media_plan({"refs": {}, "media": ["poster.png"]})


class RedactTest(unittest.TestCase):
    def test_auth_values(self):
        out = redact.auth({"url": "http://127.0.0.1:3000/cb?code=1&access_token=abc", "sessionId": "zz",
                           "passed": True, "seen_text": {"Saved": True},
                           "note": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJlMTIz"})
        self.assertNotIn("abc", out["url"])
        self.assertIn("code=1", out["url"])
        self.assertEqual(out["sessionId"], redact.MASK)
        self.assertIs(out["passed"], True)
        self.assertEqual(out["seen_text"], {"Saved": True})
        self.assertNotIn("eyJzdWIi", out["note"])


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pi-test-auth-")
        self.repo = tempfile.mkdtemp(prefix="pi-test-authrepo-")
        os.environ["PROVE_IT_AUTH_DIR"] = self.dir
        self.path = os.path.join(self.dir, "app.json")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"cookies": [{"name": "sid", "value": "s1", "domain": "localhost", "path": "/"}],
                       "origins": [{"origin": "http://localhost:3000", "localStorage": [{"name": "t", "value": "v"}]}]},
                      f)

    def tearDown(self):
        os.environ.pop("PROVE_IT_AUTH_DIR", None)
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_resolve_by_name(self):
        self.assertEqual(auth.resolve({"name": "app"}, self.repo), self.path)

    def test_refuses_credentials_and_repo_paths(self):
        with self.assertRaises(RuntimeError):
            auth.resolve({"name": "app", "password": "x"}, self.repo)
        inside = os.path.join(self.repo, "state.json")
        with open(inside, "w") as f:
            f.write("{}")
        with self.assertRaises(RuntimeError):
            auth.resolve({"state": inside}, self.repo)
        with self.assertRaises(RuntimeError):
            auth.resolve({"name": "missing"}, self.repo)

    def test_refuses_open_permissions(self):
        os.chmod(self.path, 0o644)
        with self.assertRaises(RuntimeError):
            auth.resolve({"name": "app"}, self.repo)

    def test_for_origins(self):
        copy = auth.for_origins(self.path, ["http://127.0.0.1:5001", "http://127.0.0.1:5002"], None)
        try:
            self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o600)
            with open(copy) as f:
                state = json.load(f)
            self.assertEqual(sorted(c["domain"] for c in state["cookies"]), ["127.0.0.1", "localhost"])
            self.assertEqual(sorted(o["origin"] for o in state["origins"]),
                             ["http://127.0.0.1:5001", "http://127.0.0.1:5002"])
        finally:
            auth.discard(copy)
        self.assertFalse(os.path.exists(copy))

    def test_bad_name(self):
        with self.assertRaises(SystemExit):
            auth.state_path("../x")


if __name__ == "__main__":
    unittest.main()
