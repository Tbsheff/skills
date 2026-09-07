#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import sys
import tempfile

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
PROVE = SKILL_DIR / "scripts" / "prove.py"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def run(*args: str, cwd: pathlib.Path | None = None, expect: int = 0) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run([sys.executable, "-S", str(PROVE), *args], cwd=cwd, text=True, capture_output=True)
    if cp.returncode != expect:
        raise AssertionError(
            f"command failed ({cp.returncode}, expected {expect}): {' '.join(args)}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
        )
    return cp


def git(repo: pathlib.Path, *args: str) -> None:
    cp = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if cp.returncode:
        raise AssertionError(cp.stderr)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="prove-it-self-test-") as tmp:
        root = pathlib.Path(tmp)

        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_gh = fake_bin / "gh"
        fake_gh_source = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
body_file = pathlib.Path(os.environ.get("FAKE_GH_BODY_FILE", "/tmp/fake-gh-body.md"))
head = os.environ.get("FAKE_GH_HEAD", "")
if args == ["--version"]:
    print("gh version 9.9.9")
    raise SystemExit(0)
if args[:3] == ["pr", "edit", "--help"]:
    print("--attach <file>\n--body-file <file>")
    raise SystemExit(0)
if args[:2] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner": "test/prove-it"}))
    raise SystemExit(0)
if args[:2] == ["pr", "view"]:
    body = body_file.read_text() if body_file.exists() else "## What\n\nTest PR.\n"
    print(json.dumps({
        "number": 42, "url": "https://github.com/test/prove-it/pull/42", "title": "Test proof",
        "body": body, "headRefOid": head, "headRefName": "feature", "baseRefName": "main", "isDraft": False
    }))
    raise SystemExit(0)
if args[:2] == ["pr", "edit"]:
    body_path = pathlib.Path(args[args.index("--body-file") + 1])
    body = body_path.read_text()
    i = 0
    while i < len(args):
        if args[i] == "--attach":
            rel = args[i + 1].split("#", 1)[0]
            url = "https://github.com/user-attachments/assets/" + pathlib.Path(rel).name
            body = body.replace("](./" + rel + ")", "](" + url + ")")
            body = body.replace("](" + rel + ")", "](" + url + ")")
            i += 2
        else:
            i += 1
    body_file.write_text(body)
    print("https://github.com/test/prove-it/pull/42")
    raise SystemExit(0)
print("unsupported fake gh args: " + repr(args), file=sys.stderr)
raise SystemExit(2)
"""
        fake_gh.write_text(fake_gh_source, encoding="utf-8")
        fake_gh.chmod(0o755)
        os.environ["PATH"] = str(fake_bin) + os.pathsep + os.environ.get("PATH", "")
        os.environ["FAKE_GH_BODY_FILE"] = str(root / "fake-pr-body.md")

        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "prove-it@example.test")
        git(repo, "config", "user.name", "Prove It Test")
        (repo / "index.js").write_text("export const add = (a, b) => a + b;\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "base")
        git(repo, "branch", "-M", "main")
        git(repo, "checkout", "-qb", "feature")
        (repo / "index.js").write_text("export const add = (a, b) => Number(a) + Number(b);\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "handle numeric strings")

        scan = json.loads(run("scan", "--repo", str(repo), "--base", "main", "--json").stdout)
        assert scan["recommended_proof"] == "backend", scan
        assert scan["file_count"] == 1, scan

        proof_dir = root / "proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(proof_dir), "--title", "Numeric string addition")
        run(
            "claim", "--dir", str(proof_dir), "--text", "Numeric strings are added numerically.",
            "--expected", "add('2', '3') returns 5.", "--method", "test"
        )
        run(
            "run", "--dir", str(proof_dir), "--claim", "C1", "--kind", "test",
            "--label", "Focused Node assertion", "--expect-output", "PASS", "--proves", "--",
            "node", "--input-type=module", "-e", "import('./index.js').then(m=>{if(m.add('2','3')!==5)process.exit(1);console.log('PASS')})",
        )
        run(
            "claim", "--dir", str(proof_dir), "--text", "The final state is visible.",
            "--expected", "A screenshot artifact is present.", "--method", "screenshot"
        )
        png = root / "final.png"
        png.write_bytes(PNG_1X1)
        run(
            "add", "--dir", str(proof_dir), "--claim", "C2", "--type", "screenshot",
            "--path", str(png), "--label", "Final state", "--observed", "The final state rendered.", "--proves"
        )
        run(
            "run", "--dir", str(proof_dir), "--claim", "C1", "--kind", "log",
            "--label", "Redaction probe", "--expect-output", "Authorization", "--",
            "node", "-e", "console.log('Authorization: Bearer definitely-secret-value')",
        )

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("X-Prove-It") != "safe-header-value":
                    self.send_response(403)
                    self.end_headers()
                    return
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            os.environ["PROVE_IT_TEST_HEADER"] = "safe-header-value"
            run(
                "claim", "--dir", str(proof_dir), "--text", "Sensitive headers can be supplied without command-line values.",
                "--expected", "The local request receives the environment-backed header.", "--method", "http"
            )
            run(
                "http", "--dir", str(proof_dir), "--claim", "C3", "--label", "Header environment assertion",
                "--url", f"http://127.0.0.1:{httpd.server_port}/",
                "--header-env", "X-Prove-It=PROVE_IT_TEST_HEADER",
                "--expect-status", "200", "--expect-json", "ok=true", "--proves"
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        run("validate", "--dir", str(proof_dir), "--strict")
        run("render", "--dir", str(proof_dir))

        base_body = root / "base-body.md"
        base_body.write_text(
            "## What\n\nChange behavior.\n\n## Proof\n\nOld proof.\n\n## References\n\n- #1\n",
            encoding="utf-8",
        )
        composed = root / "composed.md"
        run("compose", "--dir", str(proof_dir), "--body", str(base_body), "--out", str(composed))
        composed_text = composed.read_text(encoding="utf-8")
        assert composed_text.count("<!-- prove-it:start -->") == 1, composed_text
        assert composed_text.count("<!-- prove-it:end -->") == 1, composed_text
        assert "Old proof" in composed_text, "human-authored Proof section must be preserved"
        assert "## Prove It" in composed_text, composed_text
        assert "## References" in composed_text, composed_text

        bad_base = run("scan", "--repo", str(repo), "--base", "does-not-exist", expect=2)
        assert "does not exist" in bad_base.stderr

        manifest = json.loads((proof_dir / "manifest.json").read_text())
        assert manifest["summary"]["status"] == "passed", manifest["summary"]
        assert (proof_dir / "proof.md").exists()
        assert (proof_dir / "report.html").exists()
        attachments = json.loads((proof_dir / "attachments.json").read_text())
        assert attachments["files"] == ["frontend/final-state.png"], attachments
        log = (proof_dir / "backend" / "c1-focused-node-assertion.txt").read_text()
        assert "PASS" in log
        redaction_log = (proof_dir / "backend" / "c1-redaction-probe.txt").read_text()
        assert "definitely-secret-value" not in redaction_log
        assert "[REDACTED]" in redaction_log
        http_log = (proof_dir / "backend" / "c3-header-environment-assertion.txt").read_text()
        assert "safe-header-value" not in http_log

        screenshot = proof_dir / "frontend" / "final-state.png"
        original = screenshot.read_bytes()
        screenshot.write_bytes(original + b"tampered")
        tamper = run("validate", "--dir", str(proof_dir), expect=1)
        assert "hash mismatch" in tamper.stdout
        screenshot.write_bytes(original)
        run("validate", "--dir", str(proof_dir), "--strict")

        # Human-invoked PR mode uses ephemeral temp storage and gh pr edit --attach.
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        os.environ["FAKE_GH_HEAD"] = head
        ephemeral = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Human invoked proof").stdout.strip())
        assert ephemeral.exists(), ephemeral
        git_path = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-dir"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        assert not str(ephemeral).startswith(str(pathlib.Path(git_path).resolve())), (ephemeral, git_path)
        run(
            "claim", "--dir", str(ephemeral), "--text", "The PR proof screenshot is available to reviewers.",
            "--expected", "A screenshot is attached to the existing PR.", "--method", "screenshot"
        )
        publish_png = root / "publish.png"
        publish_png.write_bytes(PNG_1X1)
        run(
            "add", "--dir", str(ephemeral), "--claim", "C1", "--type", "screenshot",
            "--path", str(publish_png), "--label", "Reviewer state", "--observed", "Screenshot captured.", "--proves"
        )
        run("publish", "--dir", str(ephemeral))
        assert not ephemeral.exists(), "successful publish should remove ephemeral proof directory"
        published_body = pathlib.Path(os.environ["FAKE_GH_BODY_FILE"]).read_text()
        assert "## Prove It" in published_body, published_body
        assert "<!-- prove-it:start -->" in published_body, published_body
        assert "github.com/user-attachments/assets/" in published_body, published_body
        assert "./frontend/" not in published_body, published_body

        # Dirty worktrees are rejected before a PR-bound run begins.
        (repo / "dirty.tmp").write_text("dirty", encoding="utf-8")
        dirty = run("init", "--repo", str(repo), "--pr", "current", expect=2)
        assert "clean working tree" in dirty.stderr, dirty.stderr
        (repo / "dirty.tmp").unlink()

        # PR head changes invalidate a run before publication.
        stale = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Stale proof").stdout.strip())
        os.environ["FAKE_GH_HEAD"] = "f" * 40
        stale_publish = run("publish", "--dir", str(stale), expect=2)
        assert "Proof is stale" in stale_publish.stderr, stale_publish.stderr
        os.environ["FAKE_GH_HEAD"] = head
        run("cleanup", "--dir", str(stale))

        docs_repo = root / "docs-repo"
        docs_repo.mkdir()
        git(docs_repo, "init", "-q")
        git(docs_repo, "config", "user.email", "prove-it@example.test")
        git(docs_repo, "config", "user.name", "Prove It Test")
        (docs_repo / "README.md").write_text("one\n", encoding="utf-8")
        git(docs_repo, "add", ".")
        git(docs_repo, "commit", "-qm", "base")
        git(docs_repo, "branch", "-M", "main")
        git(docs_repo, "checkout", "-qb", "docs")
        (docs_repo / "README.md").write_text("one\ntwo\n", encoding="utf-8")
        git(docs_repo, "add", ".")
        git(docs_repo, "commit", "-qm", "docs")
        docs_scan = json.loads(run("scan", "--repo", str(docs_repo), "--base", "main", "--json").stdout)
        assert docs_scan["recommended_proof"] == "none", docs_scan
        docs_proof = root / "docs-proof"
        run("init", "--repo", str(docs_repo), "--base", "main", "--out", str(docs_proof))
        run("validate", "--dir", str(docs_proof), "--strict")
        run("render", "--dir", str(docs_proof))
        docs_markdown = (docs_proof / "proof.md").read_text()
        assert "No runtime proof was required" in docs_markdown
        assert "| Claim |" not in docs_markdown

        print("prove-it self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
