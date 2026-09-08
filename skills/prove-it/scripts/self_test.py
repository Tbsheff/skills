#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import pathlib
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


def read_comments(path: pathlib.Path) -> list[dict[str, object]]:
    return json.loads(path.read_text()) if path.exists() else []


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="prove-it-self-test-") as tmp:
        root = pathlib.Path(tmp)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
body_file = pathlib.Path(os.environ.get("FAKE_GH_BODY_FILE", "/tmp/fake-gh-body.md"))
comments_file = pathlib.Path(os.environ.get("FAKE_GH_COMMENTS_FILE", "/tmp/fake-gh-comments.json"))
head_file_raw = os.environ.get("FAKE_GH_HEAD_FILE", "")
head_file = pathlib.Path(head_file_raw) if head_file_raw else None
head = head_file.read_text().strip() if head_file and head_file.exists() else os.environ.get("FAKE_GH_HEAD", "")

def comments():
    return json.loads(comments_file.read_text()) if comments_file.exists() else []

def save(items):
    comments_file.write_text(json.dumps(items))

if args == ["--version"]:
    print("gh version 9.9.9")
    raise SystemExit(0)
if args[:3] == ["pr", "comment", "--help"]:
    print("--attach <file>\n--body-file <file>")
    raise SystemExit(0)
if args[:2] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner": "test/prove-it"}))
    raise SystemExit(0)
if args[:2] == ["pr", "view"]:
    print(json.dumps({
        "number": 42,
        "url": "https://github.com/test/prove-it/pull/42",
        "title": "Test proof",
        "headRefOid": head,
        "headRefName": "feature",
        "baseRefName": "main",
        "isDraft": False,
        "state": "OPEN",
    }))
    raise SystemExit(0)
if args[:2] == ["pr", "comment"]:
    body_path = pathlib.Path(args[args.index("--body-file") + 1])
    body = body_path.read_text()
    i = 0
    while i < len(args):
        if args[i] == "--attach":
            rel = args[i + 1].split("#", 1)[0]
            url = "https://github.com/user-attachments/assets/" + pathlib.Path(rel).name
            if pathlib.Path(rel).suffix.lower() in {".mp4", ".mov", ".webm"}:
                body = body.replace("![](./" + rel + ")", url)
                body = body.replace("![](" + rel + ")", url)
            else:
                body = body.replace("](./" + rel + ")", "](" + url + ")")
                body = body.replace("](" + rel + ")", "](" + url + ")")
            i += 2
        else:
            i += 1
    items = comments()
    comment_id = 9000 + len(items) + 1
    url = f"https://github.com/test/prove-it/pull/42#issuecomment-{comment_id}"
    items.append({"id": comment_id, "body": body, "html_url": url})
    save(items)
    head_after = os.environ.get("FAKE_GH_HEAD_AFTER_COMMENT", "")
    if head_file and head_after:
        head_file.write_text(head_after)
    print(url)
    raise SystemExit(int(os.environ.get("FAKE_GH_COMMENT_EXIT", "0")))
if args and args[0] == "api":
    if "--method" in args and args[args.index("--method") + 1] == "PATCH":
        endpoint = args[args.index("--method") + 2]
        comment_id = int(endpoint.rsplit("/", 1)[1])
        payload = json.loads(pathlib.Path(args[args.index("--input") + 1]).read_text())
        items = comments()
        for item in items:
            if int(item["id"]) == comment_id:
                item["body"] = payload["body"]
                save(items)
                print(json.dumps(item))
                raise SystemExit(0)
        raise SystemExit(4)
    endpoint = args[-1]
    if "/issues/comments/" in endpoint:
        comment_id = int(endpoint.rsplit("/", 1)[1])
        for item in comments():
            if int(item["id"]) == comment_id:
                print(json.dumps(item))
                raise SystemExit(0)
        raise SystemExit(4)
    if "/issues/42/comments" in endpoint:
        value = comments()
        print(json.dumps([value] if "--slurp" in args else value))
        raise SystemExit(0)
print("unsupported fake gh args: " + repr(args), file=sys.stderr)
raise SystemExit(2)
''',
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        os.environ["PATH"] = str(fake_bin) + os.pathsep + os.environ.get("PATH", "")
        pr_body_file = root / "fake-pr-body.md"
        pr_body_file.write_text("## What\n\nOriginal PR description.\n")
        comments_file = root / "fake-gh-comments.json"
        comments_file.write_text("[]")
        os.environ["FAKE_GH_BODY_FILE"] = str(pr_body_file)
        os.environ["FAKE_GH_COMMENTS_FILE"] = str(comments_file)

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
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        os.environ["FAKE_GH_HEAD"] = head

        scan = json.loads(run("scan", "--repo", str(repo), "--base", "main", "--json").stdout)
        assert scan["recommended_proof"] == "backend", scan

        # Backend-only proof renders concrete receipts and no decorative graphics.
        backend = root / "backend-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(backend), "--title", "Numeric string addition")
        run(
            "claim", "--dir", str(backend), "--text", "Numeric strings are added numerically.",
            "--expected", "add('2', '3') returns 5.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(backend), "--claim", "C1", "--kind", "test",
            "--label", "Focused Node assertion", "--expect-output", "result=5",
            "--observed", "The executable example returned result=5.", "--proves", "--",
            "node", "--input-type=module", "-e",
            "import('./index.js').then(m=>{const value=m.add('2','3');console.log('result='+value);if(value!==5)process.exit(1)})",
        )
        run("render", "--dir", str(backend))
        backend_md = (backend / "proof.md").read_text()
        assert "## QA" in backend_md and "## QA:" not in backend_md, backend_md
        assert "Tested on" in backend_md, backend_md
        assert "- The executable example returned result=5." in backend_md, backend_md
        assert "### Backend" not in backend_md, backend_md
        assert "output:" in backend_md and "result=5" in backend_md, backend_md
        assert backend_md.index("<details>") < backend_md.index("output:"), backend_md
        assert "What I ran" in backend_md, backend_md
        for phrase in ("Verified on", "Runtime evidence", "Evidence:", "Freshness:", "> [!"):
            assert phrase not in backend_md, backend_md
        assert "claims proven" not in backend_md.casefold(), backend_md
        assert "proof map" not in backend_md.casefold(), backend_md
        assert "- [x]" not in backend_md.casefold(), backend_md
        assert json.loads((backend / "attachments.json").read_text())["files"] == []
        assert not (backend / "visual").exists()

        # Failed and partial runs are plain about what happened.
        failed = root / "failed-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(failed), "--title", "Failed behavior")
        run(
            "claim", "--dir", str(failed), "--text", "Numeric strings return the expected value.",
            "--expected", "The command prints result=5.", "--method", "test", "--code", "index.js:1"
        )
        run(
            "run", "--dir", str(failed), "--claim", "C1", "--kind", "test",
            "--label", "Deliberate failing assertion", "--expect-output", "result=5",
            "--observed", "The command returned result=4.", "--proves", "--",
            "node", "-e", "console.log('result=4')", expect=1,
        )
        run("render", "--dir", str(failed))
        failed_md = (failed / "proof.md").read_text()
        assert "Tested on" in failed_md and "and hit a failure." in failed_md, failed_md
        assert "- The command returned result=4." in failed_md, failed_md

        partial = root / "partial-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(partial), "--title", "Partial behavior")
        run(
            "claim", "--dir", str(partial), "--text", "Concurrent updates preserve the latest reviewer.",
            "--expected", "Two concurrent saves resolve deterministically.", "--method", "test", "--code", "index.js:1"
        )
        run("status", "--dir", str(partial), "--claim", "C1", "--status", "not_proven", "--observed", "Concurrency was not exercised.")
        run("render", "--dir", str(partial))
        partial_md = (partial / "proof.md").read_text()
        assert "Tested on" in partial_md and "but I couldn't check everything." in partial_md, partial_md
        assert "- Concurrency was not exercised." in partial_md, partial_md

        # Full-stack output leads with real media, then causal flow and backend receipt.
        full = root / "full-stack-proof"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(full), "--title", "Reviewer assignment")
        run(
            "claim", "--dir", str(full), "--text", "The assigned reviewer appears in the queue.",
            "--expected", "The queue shows Jane Reviewer after save.", "--method", "browser", "--code", "index.js:1"
        )
        run(
            "claim", "--dir", str(full), "--text", "The selected reviewer is persisted.",
            "--expected", "A fresh read returns reviewerId=reviewer-test.", "--method", "test", "--code", "index.js:1"
        )
        run("review-step", "--dir", str(full), "--text", "The browser saves reviewer-test.", "--code", "index.js:1")
        run("review-step", "--dir", str(full), "--text", "A fresh read returns the same reviewer.", "--code", "index.js:1")
        before = root / "before.png"; before.write_bytes(PNG_1X1)
        after = root / "after.png"; after.write_bytes(PNG_1X1)
        video = root / "demo.webm"; video.write_bytes(b"prove-it-video-fixture")
        run("add", "--dir", str(full), "--claim", "C1", "--type", "screenshot", "--path", str(before), "--label", "Before assignment", "--role", "before", "--observed", "No reviewer is assigned.")
        run("add", "--dir", str(full), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "After assignment", "--role", "after", "--observed", "Jane Reviewer appears in the queue.", "--proves")
        run("add", "--dir", str(full), "--claim", "C1", "--type", "video", "--path", str(video), "--label", "Reviewer assignment flow", "--role", "primary", "--observed", "Saving the assignment updates the queue.")
        run(
            "run", "--dir", str(full), "--claim", "C2", "--kind", "database",
            "--label", "Persisted reviewer", "--expect-output", "reviewerId=reviewer-test",
            "--observed", "A fresh read returned reviewerId=reviewer-test.", "--proves", "--",
            "node", "-e", "console.log('reviewerId=reviewer-test')",
        )
        run("render", "--dir", str(full))
        full_md = (full / "proof.md").read_text()
        assert full_md.index("Tested on") < full_md.index("![](./frontend/reviewer-assignment-flow.webm)"), full_md
        assert full_md.index("![](./frontend/reviewer-assignment-flow.webm)") < full_md.index("| Before | After |"), full_md
        assert "### Demo" not in full_md and "### Backend" not in full_md and "Path I checked" not in full_md, full_md
        assert "- Jane Reviewer appears in the queue." in full_md, full_md
        assert "- A fresh read returned reviewerId=reviewer-test." in full_md, full_md
        assert full_md.index("<details>") < full_md.index("Path: The browser saves reviewer-test → A fresh read returns the same reviewer"), full_md
        for phrase in ("Verified on", "Runtime evidence", "Evidence:", "Freshness:", "> [!", "claims proven"):
            assert phrase not in full_md, full_md
        assert full_md.index("<details>") < full_md.index("result: passed"), full_md
        assert "proof map" not in full_md.casefold(), full_md
        assert "claims proven" not in full_md.casefold(), full_md
        attachments = json.loads((full / "attachments.json").read_text())["files"]
        assert attachments == [
            "frontend/before-assignment.png",
            "frontend/after-assignment.png",
            "frontend/reviewer-assignment-flow.webm",
        ], attachments

        diagram = root / "flow.svg"
        diagram.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>flow</text></svg>')
        bad_diagram = run(
            "add", "--dir", str(full), "--claim", "C2", "--type", "diagram",
            "--path", str(diagram), "--label", "Invalid proof diagram", "--proves", expect=2
        )
        assert "cannot prove runtime behavior" in bad_diagram.stderr

        # Tampering is detected.
        screenshot = full / "frontend" / "after-assignment.png"
        original = screenshot.read_bytes()
        screenshot.write_bytes(original + b"tampered")
        tamper = run("validate", "--dir", str(full), expect=1)
        assert "hash mismatch" in tamper.stdout
        screenshot.write_bytes(original)
        run("validate", "--dir", str(full), "--strict")

        # Publishing creates a dedicated comment and leaves the PR description alone.
        original_pr_body = pr_body_file.read_text()
        published = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Human invoked proof").stdout.strip())
        run(
            "claim", "--dir", str(published), "--text", "The assigned reviewer appears in the queue.",
            "--expected", "The interaction is visible in the comment.", "--method", "browser", "--code", "index.js:1"
        )
        run("add", "--dir", str(published), "--claim", "C1", "--type", "screenshot", "--path", str(before), "--label", "Before reviewer state", "--role", "before", "--observed", "The review is unassigned.")
        run("add", "--dir", str(published), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "After reviewer state", "--role", "after", "--observed", "The assigned reviewer is visible.", "--proves")
        run("add", "--dir", str(published), "--claim", "C1", "--type", "video", "--path", str(video), "--label", "Reviewer assignment flow", "--role", "primary", "--observed", "Assigning the reviewer updates the visible state.")
        publish_stdout = run("publish", "--dir", str(published)).stdout
        result, _ = json.JSONDecoder().raw_decode(publish_stdout)
        assert result["comment_url"].endswith("#issuecomment-9001"), result
        assert not published.exists(), "successful publish should remove its temp directory"
        assert pr_body_file.read_text() == original_pr_body, "publish must not rewrite the PR description"
        comments = read_comments(comments_file)
        assert len(comments) == 1, comments
        comment_body = str(comments[0]["body"])
        assert "### Demo" not in comment_body and "### Before / after" not in comment_body, comment_body
        assert "Tested on" in comment_body and comment_body.index("Tested on") < comment_body.index("github.com/user-attachments/assets/"), comment_body
        assert "| Before | After |" in comment_body, comment_body
        for phrase in ("Verified on", "Runtime evidence", "Evidence:", "Freshness:", "> [!"):
            assert phrase not in comment_body, comment_body
        assert "github.com/user-attachments/assets/" in comment_body, comment_body
        assert "proof map" not in comment_body.casefold(), comment_body
        assert "claims proven" not in comment_body.casefold(), comment_body
        assert "- [x]" not in comment_body.casefold(), comment_body
        assert "### Observed" not in comment_body, comment_body
        assert "./frontend/" not in comment_body, comment_body

        # Each invocation creates another self-contained receipt rather than editing the first.
        second = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Second proof run").stdout.strip())
        run(
            "claim", "--dir", str(second), "--text", "The final state is visible.",
            "--expected", "The screenshot is attached.", "--method", "screenshot", "--code", "index.js:1"
        )
        run("add", "--dir", str(second), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "Final state", "--role", "final", "--observed", "The final state is visible.", "--proves")
        run("publish", "--dir", str(second))
        comments = read_comments(comments_file)
        assert len(comments) == 2, comments
        assert comments[0]["id"] != comments[1]["id"]
        assert "<!-- prove-it:run id=" in str(comments[0]["body"])
        assert "<!-- prove-it:run id=" in str(comments[1]["body"])
        assert str(comments[0]["body"]) != str(comments[1]["body"])
        assert "Human invoked proof" not in str(comments[0]["body"])
        assert "Second proof run" not in str(comments[1]["body"])

        # A later unrelated commit labels point-in-time proof but does not block it.
        point = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Point-in-time proof").stdout.strip())
        run(
            "claim", "--dir", str(point), "--text", "The captured state remains visible.",
            "--expected", "A screenshot from the captured SHA is attached.", "--method", "screenshot", "--code", "index.js:1"
        )
        run("add", "--dir", str(point), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "Captured state", "--role", "final", "--observed", "Captured at the original PR head.", "--proves")
        git(repo, "checkout", "-qb", "future-unrelated")
        (repo / "README.md").write_text("Later unrelated note.\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "add unrelated note")
        future_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
        git(repo, "checkout", "-q", "feature")
        os.environ["FAKE_GH_HEAD"] = future_head
        point_result, _ = json.JSONDecoder().raw_decode(run("publish", "--dir", str(point)).stdout)
        assert point_result["relationship"] == "advanced-unrelated", point_result
        point_body = str(read_comments(comments_file)[-1]["body"])
        assert "The PR is now" in point_body, point_body
        assert "None of the files I checked changed afterward." in point_body, point_body
        assert head[:8] in point_body and future_head[:8] in point_body, point_body

        # If the PR advances during upload, the exact newly-created comment is refreshed.
        os.environ["FAKE_GH_HEAD"] = head
        moving = pathlib.Path(run("init", "--repo", str(repo), "--pr", "current", "--title", "Moving-head proof").stdout.strip())
        run(
            "claim", "--dir", str(moving), "--text", "The captured state survives a head update.",
            "--expected", "The comment retains the media and names both SHAs.", "--method", "screenshot", "--code", "index.js:1"
        )
        run("add", "--dir", str(moving), "--claim", "C1", "--type", "screenshot", "--path", str(after), "--label", "Moving head state", "--role", "final", "--observed", "Captured before upload began.", "--proves")
        head_file = root / "fake-gh-head.txt"
        head_file.write_text(head)
        os.environ["FAKE_GH_HEAD_FILE"] = str(head_file)
        os.environ["FAKE_GH_HEAD_AFTER_COMMENT"] = future_head
        moving_result, _ = json.JSONDecoder().raw_decode(run("publish", "--dir", str(moving)).stdout)
        assert moving_result["relationship"] == "advanced-unrelated", moving_result
        moving_body = str(read_comments(comments_file)[-1]["body"])
        assert "The PR is now" in moving_body, moving_body
        assert future_head[:8] in moving_body, moving_body
        assert "github.com/user-attachments/assets/" in moving_body, moving_body
        assert "./frontend/" not in moving_body, moving_body
        os.environ.pop("FAKE_GH_HEAD_FILE", None)
        os.environ.pop("FAKE_GH_HEAD_AFTER_COMMENT", None)
        head_file.unlink()
        os.environ["FAKE_GH_HEAD"] = head

        # Dirty worktrees and visual claims without media are rejected.
        (repo / "dirty.tmp").write_text("dirty")
        dirty = run("init", "--repo", str(repo), "--pr", "current", expect=2)
        assert "clean working tree" in dirty.stderr
        (repo / "dirty.tmp").unlink()

        missing = root / "missing-visual"
        run("init", "--repo", str(repo), "--base", "main", "--out", str(missing))
        run(
            "claim", "--dir", str(missing), "--text", "The changed interaction is visible.",
            "--expected", "A reviewer can see the interaction.", "--method", "browser"
        )
        run("status", "--dir", str(missing), "--claim", "C1", "--status", "passed", "--observed", "Claimed without media.")
        invalid = run("validate", "--dir", str(missing), expect=1)
        assert "without a screenshot or video" in invalid.stdout

        print("prove-it self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
