import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import commit, git, make_repo  # noqa: E402

import draft  # noqa: E402
import scenario  # noqa: E402
import wtcache  # noqa: E402


class DraftTest(unittest.TestCase):
    def setUp(self):
        pkg = {"name": "@acme/web", "scripts": {"dev": "next dev --port ${WEB_PORT:-3000}", "test": "vitest run"}}
        self.repo = make_repo({
            "pnpm-lock.yaml": "lockfileVersion: 9\n",
            "package.json": json.dumps({"name": "root", "private": True}),
            "apps/web/package.json": json.dumps(pkg),
            "apps/web/app/(main)/settings/[id]/page.tsx": "export default function P() { return <main/> }\n",
            "apps/web/app/(main)/settings/[id]/_components/form.tsx": "export function F() { return <p>Old</p> }\n",
            "apps/web/app/api/orders/route.ts": "export async function GET() {}\n",
            "apps/web/components/save-bar.tsx": "export function SaveBar() { return <b>Save</b> }\n",
            "apps/web/app/(main)/billing/page.tsx": "import { SaveBar } from '@/components/save-bar'\n",
        })
        self.base = git(self.repo, "rev-parse", "HEAD")
        commit(self.repo, {
            "apps/web/app/(main)/settings/[id]/_components/form.tsx":
                "export function F() { return <p>Old</p><div role=\"status\">Profile saved</div> }\n",
            "apps/web/app/api/orders/route.ts": "export async function GET() {}\nexport const POST = 1\n",
            "apps/web/components/save-bar.tsx": "export function SaveBar() { return <b>Save now</b> }\n",
            "apps/web/lib/x.test.ts": "test('x', () => {})\n",
        }, "change")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_next_monorepo(self):
        s = draft.draft(self.repo, self.base)
        routes = [r["route"] for r in s["draft"]["routes"]]
        self.assertEqual(routes[0], "/settings/[id]")
        self.assertIn("/billing", routes)
        self.assertEqual(s["ui"]["path"], "/settings/[id]")
        self.assertTrue(any("dynamic segment" in t for t in s["todo"]))
        self.assertEqual(s["ui"]["serve"]["env"], {"WEB_PORT": "{port}"})
        self.assertIn("pnpm --filter @acme/web dev", s["ui"]["serve"]["cmd"])
        handlers = {(a["method"], a["path"]) for a in s["draft"]["api_handlers"]}
        self.assertEqual(handlers, {("GET", "/api/orders"), ("POST", "/api/orders")})
        self.assertEqual(s["ui"]["steps"][-1]["expect_text"], "Profile saved")
        self.assertIn("vitest run lib/x.test.ts", s["backend"]["tests"]["command"])
        self.assertEqual(s["backend"]["tests"]["copy_from_change"], ["apps/web/lib/x.test.ts"])
        self.assertTrue(s["todo"])

    def test_workspace_installs_instead_of_linking(self):
        commit(self.repo, {"pnpm-workspace.yaml": "packages: ['apps/*']\n"}, "ws")
        os.makedirs(os.path.join(self.repo, "node_modules"), exist_ok=True)
        s = draft.draft(self.repo, self.base)
        self.assertEqual(s["ui"]["setup"]["command"], "pnpm install --frozen-lockfile --offline")
        self.assertFalse([p for p in s["ui"]["setup"]["link_from_change"] if "node_modules" in p])

    def test_default_base_and_non_ancestor_warning(self):
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "checkout", "-q", "-b", "feature")
        commit(self.repo, {"apps/web/app/(main)/billing/page.tsx": "export default 1\n"}, "feature work")
        self.assertEqual(draft.default_base(self.repo), git(self.repo, "rev-parse", "main"))
        git(self.repo, "checkout", "-q", "main")
        other = commit(self.repo, {"README.md": "main moved\n"}, "main only")
        git(self.repo, "checkout", "-q", "feature")
        s = draft.draft(self.repo, other)
        self.assertTrue(any("not an ancestor" in t for t in s["todo"]))

    def test_route_helpers(self):
        self.assertEqual(draft.route_of(["(g)", "a", "[id]"]), ("/a/[id]", True))
        self.assertEqual(draft.route_of(["_private", "a"]), (None, False))
        self.assertEqual(draft.pages_route_for("src/pages/users/index.tsx")["route"], "/users")
        self.assertIsNone(draft.pages_route_for("pages/api/x.ts"))


class CheckoutsTest(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp(prefix="pi-test-cache-")
        os.environ["PROVE_IT_CACHE_DIR"] = self.cache
        os.environ.pop("PROVE_IT_NO_CACHE", None)
        self.repo = make_repo({"index.html": "<p>base page</p>\n"})
        self.base = git(self.repo, "rev-parse", "HEAD")
        commit(self.repo, {"index.html": "<p>change page</p>\n"}, "change")
        self.work = tempfile.mkdtemp(prefix="pi-test-work-")

    def tearDown(self):
        for rdir in wtcache.repo_dirs():
            for e in wtcache.entries(rdir):
                wtcache.remove_entry(self.repo, e)
        shutil.rmtree(self.cache, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.work, ignore_errors=True)
        os.environ.pop("PROVE_IT_CACHE_DIR", None)

    def scenario(self, **extra):
        return {"repo": self.repo, "refs": {"base": self.base, "change": None}, "serve": {"static": "."}, "path": "/",
                **extra}

    def body(self, url):
        return urllib.request.urlopen(url, timeout=5).read().decode()

    def test_cached_base_server_is_reused(self):
        s = self.scenario(serve={"static": ".", "keep": True})
        with scenario.Checkouts(s, self.work) as co:
            self.assertIn("base page", self.body(co.url("base")))
            self.assertIn("change page", self.body(co.url("change")))
            port = co.ports["base"]
            self.assertEqual(co.status["base"], "cache_new")
        self.assertIn("base page", self.body(f"http://127.0.0.1:{port}/"), "base server is kept")
        with scenario.Checkouts(s, self.work) as co:
            self.assertEqual(co.status["base"], "cache_hit+server_reused")
            self.assertEqual(co.ports["base"], port)
        subprocess_clear(self.repo)
        with self.assertRaises(OSError):
            self.body(f"http://127.0.0.1:{port}/")

    def test_servers_stop_by_default(self):
        with scenario.Checkouts(self.scenario(), self.work) as co:
            port = co.ports["base"]
            self.assertEqual(co.status["base"], "cache_new")
        with self.assertRaises(OSError):
            self.body(f"http://127.0.0.1:{port}/")

    def test_no_cache_cleans_up(self):
        s = self.scenario()
        with scenario.Checkouts(s, self.work, cache=False) as co:
            port = co.ports["base"]
            self.assertEqual(co.status["base"], "temp")
        with self.assertRaises(OSError):
            self.body(f"http://127.0.0.1:{port}/")
        self.assertEqual(len(git(self.repo, "worktree", "list").splitlines()), 1)

    def test_failed_start_stops_server(self):
        s = self.scenario(serve={"cmd": f"{sys.executable} -c 'import sys; sys.exit(3)' {{port}}"})
        with self.assertRaises(RuntimeError):
            with scenario.Checkouts(s, self.work):
                pass
        for e in wtcache.entries(wtcache.repo_dir(self.repo)):
            self.assertNotIn("server", e.meta)

    def test_reuse_url_marker(self):
        with scenario.Checkouts(self.scenario(), self.work, cache=False) as first:
            user_url = first.origin("change")
            s = self.scenario(reuse_url=user_url, reuse_check={"path": "/", "marker": "change page"})
            with scenario.Checkouts(s, self.work + "/2", cache=False) as co:
                self.assertEqual(co.status["change"], "reuse_url")
                self.assertEqual(co.origin("change"), user_url)
                self.assertEqual(co.caveats, [])
            s = self.scenario(reuse_url=user_url, reuse_check={"path": "/", "marker": "{short_sha}"})
            with scenario.Checkouts(s, self.work + "/3", cache=False) as co:
                self.assertNotEqual(co.status.get("change"), "reuse_url")
                self.assertTrue(co.caveats)
            s = self.scenario(reuse_url=user_url)
            with scenario.Checkouts(s, self.work + "/4", cache=False) as co:
                self.assertEqual(co.status["change"], "reuse_url")
                self.assertIn("did not check", co.caveats[0])


def subprocess_clear(repo):
    for e in wtcache.entries(wtcache.repo_dir(repo)):
        wtcache.remove_entry(repo, e)


if __name__ == "__main__":
    unittest.main()
