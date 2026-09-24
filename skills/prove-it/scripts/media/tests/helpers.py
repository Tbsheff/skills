import os
import subprocess
import sys
import tempfile

MEDIA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("", "shared", "ui"):
    path = os.path.join(MEDIA, sub) if sub else MEDIA
    if path not in sys.path:
        sys.path.insert(0, path)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()


def make_repo(files, message="first"):
    repo = tempfile.mkdtemp(prefix="pi-test-repo-")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    commit(repo, files, message)
    return repo


def commit(repo, files, message):
    for rel, text in files.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")
