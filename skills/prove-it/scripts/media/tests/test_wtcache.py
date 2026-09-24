import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import commit, git, make_repo  # noqa: E402

import procs  # noqa: E402
import wtcache  # noqa: E402


class CacheCase(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp(prefix="pi-test-cache-")
        self.env = {k: os.environ.get(k) for k in ("PROVE_IT_CACHE_DIR", "PROVE_IT_CACHE_MAX", "PROVE_IT_NO_CACHE")}
        os.environ["PROVE_IT_CACHE_DIR"] = self.cache
        os.environ.pop("PROVE_IT_NO_CACHE", None)
        os.environ["PROVE_IT_CACHE_MAX"] = "2"
        self.repo = make_repo({"package-lock.json": "{\"v\": 1}\n", "index.html": "<p>one</p>\n",
                               ".gitignore": "node_modules\ngenerated.txt\n"})
        self.sha1 = git(self.repo, "rev-parse", "HEAD")
        self.log = os.path.join(self.cache, "setup.log")

    def tearDown(self):
        for rdir in wtcache.repo_dirs():
            for e in wtcache.entries(rdir):
                wtcache.remove_entry(self.repo, e)
        shutil.rmtree(self.cache, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def acquire(self, sha, setup=None):
        return wtcache.acquire(self.repo, sha, setup, self.repo, self.log)

    def test_hit_moved_new(self):
        counter = os.path.join(self.cache, "count")
        setup = {"command": f"echo x >> {counter}; mkdir -p node_modules; echo dep > node_modules/dep"}
        e1, s1 = self.acquire(self.sha1, setup)
        self.assertEqual(s1, "new")
        with open(os.path.join(e1.path, "generated.txt"), "w") as f:
            f.write("stale client")
        git(self.repo, "check-ignore", "-q", "node_modules")
        wtcache.release(e1)
        e2, s2 = self.acquire(self.sha1, setup)
        self.assertEqual((s2, e2.id), ("hit", e1.id))
        wtcache.release(e2)
        sha2 = commit(self.repo, {"index.html": "<p>two</p>\n"}, "second")
        e3, s3 = self.acquire(sha2, setup)
        self.assertEqual((s3, e3.id), ("moved", e1.id))
        self.assertEqual(git(e3.path, "rev-parse", "HEAD"), sha2)
        self.assertTrue(os.path.exists(os.path.join(e3.path, "node_modules", "dep")), "ignored deps survive a move")
        self.assertFalse(os.path.exists(os.path.join(e3.path, "generated.txt")), "ignored build output is removed")
        wtcache.release(e3)
        sha3 = commit(self.repo, {"package-lock.json": "{\"v\": 2}\n"}, "deps")
        e4, s4 = self.acquire(sha3, setup)
        self.assertEqual(s4, "new")
        self.assertNotEqual(e4.id, e1.id)
        wtcache.release(e4)
        with open(counter) as f:
            self.assertEqual(len(f.read().split()), 4, "setup runs on every use, so generated code matches the SHA")

    def test_locked_entry_is_not_shared(self):
        e1, _ = self.acquire(self.sha1)
        e2, s2 = self.acquire(self.sha1)
        self.assertEqual(s2, "new")
        self.assertNotEqual(e1.id, e2.id)
        wtcache.release(e1)
        wtcache.release(e2)

    def test_lru_eviction_prunes_git(self):
        shas = [self.sha1]
        for i in range(3):
            shas.append(commit(self.repo, {"package-lock.json": f"{{\"v\": {i + 10}}}\n"}, f"c{i}"))
        ids = []
        for sha in shas:
            e, _ = self.acquire(sha)
            ids.append(e.id)
            wtcache.release(e)
            time.sleep(0.01)
        left = [e.id for e in wtcache.entries(wtcache.repo_dir(self.repo))]
        self.assertEqual(sorted(left), sorted(ids[-2:]))
        listed = git(self.repo, "worktree", "list")
        for gone in ids[:2]:
            self.assertNotIn(gone, listed)

    def test_user_checkout_untouched_and_reset_between_runs(self):
        with open(os.path.join(self.repo, "index.html"), "w") as f:
            f.write("<p>dirty</p>\n")
        e, _ = self.acquire(self.sha1, {"copy_from_change": ["index.html"]})
        with open(os.path.join(e.path, "stray.txt"), "w") as f:
            f.write("left by a test run")
        with open(os.path.join(e.path, "index.html"), "w") as f:
            f.write("changed in base")
        wtcache.release(e)
        e2, s2 = self.acquire(self.sha1)
        self.assertEqual(s2, "new", "a different setup gives a different entry")
        wtcache.release(e2)
        e3, s3 = self.acquire(self.sha1, {"copy_from_change": ["index.html"]})
        self.assertEqual(s3, "hit")
        self.assertFalse(os.path.exists(os.path.join(e3.path, "stray.txt")))
        with open(os.path.join(e3.path, "index.html")) as f:
            self.assertEqual(f.read(), "<p>one</p>\n", "tracked files reset to the commit")
        wtcache.release(e3)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.sha1)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "M index.html")

    def test_kept_server_live_and_dropped(self):
        e, _ = self.acquire(self.sha1)
        port = wtcache_free_port()
        proc = procs.start([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], e.path,
                           dict(os.environ), e.server_log)
        try:
            procs.wait_url(f"http://127.0.0.1:{port}/", proc, e.server_log, 20)
            e.keep_server(proc, port, "k1")
            ready = lambda p: f"http://127.0.0.1:{p}/"  # noqa: E731
            self.assertIsNotNone(e.live_server("k1", ready))
            self.assertIsNone(e.live_server("other-serve-spec", ready))
            e.drop_server()
            proc.wait(timeout=10)
            self.assertIsNone(e.live_server("k1", ready))
        finally:
            procs.stop(proc)
            wtcache.release(e)

    def test_schema_change_gives_new_entry(self):
        e1, _ = self.acquire(self.sha1)
        wtcache.release(e1)
        sha2 = commit(self.repo, {"apps/web/prisma/schema.prisma": "model A { id Int @id }\n"}, "schema")
        e2, s2 = self.acquire(sha2)
        self.assertEqual(s2, "new")
        wtcache.release(e2)

    def test_reused_pid_is_not_killed(self):
        sleeper = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            fake = {"pid": sleeper.pid, "pgid": sleeper.pid, "start": "Mon Jan  1 00:00:00 2001",
                    "cmd": "python3 -m http.server 1"}
            self.assertFalse(wtcache.same_process(fake))
            wtcache.stop_server(fake)
            self.assertIsNone(sleeper.poll(), "a process that only shares the PID must not be killed")
            real = {"pid": sleeper.pid, **wtcache.identity(sleeper.pid)}
            self.assertTrue(wtcache.same_process(real))
            wtcache.stop_server(real)
            sleeper.wait(timeout=10)
        finally:
            if sleeper.poll() is None:
                sleeper.kill()
                sleeper.wait()

    def test_workspace_refuses_node_modules_link(self):
        commit(self.repo, {"pnpm-workspace.yaml": "packages: ['packages/*']\n"}, "ws")
        os.makedirs(os.path.join(self.repo, "node_modules"), exist_ok=True)
        with self.assertRaises(RuntimeError) as ctx:
            procs.prepare_base(tempfile.mkdtemp(), self.repo, {"link_from_change": ["node_modules"]}, self.log)
        self.assertIn("workspace", str(ctx.exception))

    def test_cli_clear(self):
        e, _ = self.acquire(self.sha1)
        wtcache.release(e)
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(wtcache.__file__), "wtcache.py"),
                              "clear", "--repo", self.repo], capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)[0]["done"], "clear")
        self.assertEqual(len(git(self.repo, "worktree", "list").splitlines()), 1)

    def test_disabled(self):
        self.assertFalse(wtcache.enabled({"cache": False}))
        self.assertFalse(wtcache.enabled({}, flag=True))
        os.environ["PROVE_IT_NO_CACHE"] = "1"
        self.assertFalse(wtcache.enabled({}))


def wtcache_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    unittest.main()
