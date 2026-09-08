#!/usr/bin/env python3
"""Small, dependency-free evidence recorder for the Prove It Claude skill."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import html
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Sequence

TOOL_VERSION = "1.8.0"
SCHEMA_VERSION = 3
TEMP_RUN_MAX_AGE_HOURS = 1.0

DEFAULT_BUDGETS = {
    "max_claims": 3,
    "max_commands": 3,
    "max_screenshots": 2,
    "max_videos": 1,
    "max_diagrams": 1,
    "max_video_seconds": 30.0,
}

EXPANDED_BUDGETS = {
    "max_claims": 6,
    "max_commands": 8,
    "max_screenshots": 5,
    "max_videos": 2,
    "max_diagrams": 2,
    "max_video_seconds": 90.0,
}

TEXT_EVIDENCE_TYPES = {"command", "test", "http", "database", "log", "console", "errors", "file"}
IMAGE_EVIDENCE_TYPES = {"screenshot", "diagram"}
VIDEO_EVIDENCE_TYPES = {"video"}
MEDIA_EVIDENCE_TYPES = IMAGE_EVIDENCE_TYPES | VIDEO_EVIDENCE_TYPES
ALL_EVIDENCE_TYPES = TEXT_EVIDENCE_TYPES | MEDIA_EVIDENCE_TYPES | {"trace", "har"}
VISUAL_CLAIM_METHODS = {"browser", "screenshot", "video"}
VISUAL_PROOF_RECOMMENDATIONS = {"browser", "screenshot", "mixed"}

SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret)\b(\s*[:=]\s*)[^\s,;]+"), r"\1\2[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_TOKEN]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"), r"\1[REDACTED]@"),
]

STRONG_SECRET_DETECTORS: list[tuple[str, re.Pattern[str]]] = [
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("API token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("Authorization header", re.compile(r"(?i)authorization\s*:\s*(?:bearer|basic)\s+(?!\[REDACTED\])\S+")),
]

FRONTEND_EXTENSIONS = {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less", ".html", ".htm"}
CODE_EXTENSIONS = {".ts", ".js", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h"}
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".adoc", ".txt"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".lock"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def redact(text: str) -> str:
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def truncate(text: str, limit: int = 200_000) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = limit // 2
    tail = limit - head
    return text[:head] + "\n\n[... output truncated by prove-it ...]\n\n" + text[-tail:], True


def slug(value: str, fallback: str = "evidence") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return (value or fallback)[:72]


def parse_code_ref(value: str) -> tuple[str, int | None, int | None]:
    """Parse repo-relative path, path:start-end, or path#Lstart-Lend."""
    raw = value.strip()
    if not raw:
        raise RuntimeError("Code reference cannot be empty")

    path_text = raw
    start: int | None = None
    end: int | None = None
    hash_match = re.fullmatch(r"(.+?)#L(\d+)(?:-L(\d+))?", raw)
    colon_match = re.fullmatch(r"(.+?):(\d+)(?:-(\d+))?", raw)
    if hash_match:
        path_text = hash_match.group(1)
        start = int(hash_match.group(2))
        end = int(hash_match.group(3) or hash_match.group(2))
    elif colon_match:
        path_text = colon_match.group(1)
        start = int(colon_match.group(2))
        end = int(colon_match.group(3) or colon_match.group(2))

    normalized = pathlib.PurePosixPath(path_text.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts or str(normalized) in {"", "."}:
        raise RuntimeError(f"Code reference must be a repo-relative path: {value}")
    if start is not None and (start < 1 or end is None or end < start):
        raise RuntimeError(f"Invalid line range in code reference: {value}")
    return normalized.as_posix(), start, end


def normalize_code_ref(value: str) -> str:
    path, start, end = parse_code_ref(value)
    if start is None:
        return path
    return f"{path}:{start}" if start == end else f"{path}:{start}-{end}"


def add_proof_scope(manifest: dict[str, Any], refs: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    scope = manifest.setdefault("proof_scope", {}).setdefault("files", [])
    for value in refs:
        ref = normalize_code_ref(value)
        normalized.append(ref)
        path, _, _ = parse_code_ref(ref)
        if path not in scope:
            scope.append(path)
    return normalized


def shell_join(argv: Sequence[str]) -> str:
    return shlex.join(list(argv))


def run_capture(
    argv: Sequence[str] | str,
    *,
    cwd: pathlib.Path | None = None,
    timeout: float = 30,
    shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        shell=shell,
        executable="/bin/bash" if shell else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def git(repo: pathlib.Path, *args: str, check: bool = True) -> str:
    cp = run_capture(["git", *args], cwd=repo, timeout=30)
    if check and cp.returncode != 0:
        raise RuntimeError(redact(cp.stderr.strip() or cp.stdout.strip() or f"git {' '.join(args)} failed"))
    return cp.stdout.strip()


def repo_root(path: str | pathlib.Path = ".") -> pathlib.Path:
    path = pathlib.Path(path).resolve()
    cp = run_capture(["git", "rev-parse", "--show-toplevel"], cwd=path, timeout=10)
    if cp.returncode != 0:
        raise RuntimeError(f"Not inside a git repository: {path}")
    return pathlib.Path(cp.stdout.strip()).resolve()


def git_dir(repo: pathlib.Path) -> pathlib.Path:
    raw = git(repo, "rev-parse", "--path-format=absolute", "--git-dir")
    return pathlib.Path(raw).resolve()


def try_git(repo: pathlib.Path, *args: str) -> str | None:
    try:
        value = git(repo, *args)
        return value or None
    except RuntimeError:
        return None


def load_project_config(repo: pathlib.Path) -> tuple[dict[str, Any], str | None]:
    for candidate in (repo / ".claude" / "prove-it.json", repo / ".prove-it.json"):
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Invalid Prove It config at {candidate}: {exc}") from exc
            if not isinstance(data, dict):
                raise RuntimeError(f"Prove It config must be a JSON object: {candidate}")
            return data, str(candidate.relative_to(repo))
    return {}, None


def choose_base(repo: pathlib.Path, explicit: str | None, config: dict[str, Any]) -> str | None:
    def exists(ref: str) -> bool:
        return run_capture(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo, timeout=10).returncode == 0

    if explicit:
        if not exists(explicit):
            raise RuntimeError(f"Requested base ref does not exist: {explicit}")
        return explicit

    env_base = os.environ.get("PROVE_IT_BASE")
    if env_base:
        if not exists(env_base):
            raise RuntimeError(f"PROVE_IT_BASE ref does not exist: {env_base}")
        return env_base

    cfg_base = config.get("base")
    if isinstance(cfg_base, str):
        if not exists(cfg_base):
            raise RuntimeError(f"Configured base ref does not exist: {cfg_base}")
        return cfg_base

    candidates: list[str] = []
    upstream = try_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if upstream:
        candidates.append(upstream)
    candidates.extend(["origin/main", "origin/master", "main", "master"])

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if exists(candidate):
            return candidate
    return None


def parse_name_status(text: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith("R") or code.startswith("C"):
            if len(parts) >= 3:
                files.append({"status": code[0], "path": parts[2], "previous_path": parts[1]})
        elif len(parts) >= 2:
            files.append({"status": code[0], "path": parts[1]})
    return files


def parse_numstat(text: str) -> dict[str, dict[str, int | None]]:
    stats: dict[str, dict[str, int | None]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path = parts[0], parts[1], parts[-1]
        stats[path] = {
            "added": int(added_raw) if added_raw.isdigit() else None,
            "deleted": int(deleted_raw) if deleted_raw.isdigit() else None,
        }
    return stats


def is_test_path(path: str) -> bool:
    lower = path.lower()
    name = pathlib.PurePosixPath(lower).name
    return (
        any(part in {"test", "tests", "__tests__", "spec", "specs", "e2e", "fixtures"} for part in pathlib.PurePosixPath(lower).parts)
        or ".test." in name
        or ".spec." in name
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_test.go")
    )


def classify_path(path: str) -> set[str]:
    p = pathlib.PurePosixPath(path)
    lower = path.lower()
    parts = set(p.parts)
    suffix = p.suffix.lower()
    categories: set[str] = set()

    if is_test_path(path):
        categories.add("tests")
        return categories

    if suffix in DOC_EXTENSIONS or p.name.lower().startswith(("readme", "license", "changelog", "contributing")) or "docs" in parts:
        categories.add("docs")

    if suffix in CONFIG_EXTENSIONS or p.name.lower() in {
        "dockerfile",
        "makefile",
        "package.json",
        "pyproject.toml",
        "cargo.toml",
        "go.mod",
        "tsconfig.json",
    } or any(part in {".github", ".circleci", "config", "configs"} for part in parts):
        categories.add("config")

    frontend_parts = {"app", "pages", "components", "ui", "views", "templates", "public", "static", "web", "frontend", "client"}
    backend_parts = {"server", "api", "backend", "services", "service", "controllers", "controller", "routes", "models", "workers", "worker", "jobs", "job"}
    database_parts = {"database", "databases", "db", "migrations", "migration", "prisma"}

    if suffix in FRONTEND_EXTENSIONS or bool(parts & frontend_parts):
        categories.add("frontend")

    if bool(parts & backend_parts) or (suffix in {".py", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs"} and "frontend" not in categories):
        categories.add("backend")

    if bool(parts & database_parts) or "schema.prisma" in lower or "/migrations/" in f"/{lower}/":
        categories.add("database")
        categories.add("backend")

    if re.search(r"(^|/)(auth|authz|authorization|permissions?|security|billing|payments?|identity|crypto)(/|$)", lower):
        categories.add("security")

    if suffix in CODE_EXTENSIONS and not ({"frontend", "backend"} & categories):
        categories.add("library")

    if not categories:
        categories.add("other")
    return categories


def parse_added_lines(diff_text: str) -> dict[str, str]:
    """Collect added diff lines by destination path without reading whole files."""
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            result.setdefault(current, [])
        elif line.startswith("+++ /dev/null"):
            current = None
        elif current and line.startswith("+") and not line.startswith("+++"):
            result[current].append(line[1:])
    return {path: "\n".join(lines) for path, lines in result.items()}


def augment_from_added_content(path: str, categories: set[str], added_text: str) -> set[str]:
    """Detect UI embedded in server-rendered code without broad file-content scans."""
    if not added_text or "frontend" in categories or is_test_path(path):
        return categories
    suffix = pathlib.PurePosixPath(path).suffix.lower()
    if suffix not in CODE_EXTENSIONS:
        return categories
    html_tags = re.findall(
        r"<(?:html|head|body|main|section|article|div|form|button|input|select|textarea|script|style|h[1-6]|p|a)\b",
        added_text,
        flags=re.IGNORECASE,
    )
    server_html_signal = re.search(
        r"HTMLResponse|render_template|text/html|template\.(?:render|execute)|content_type\s*=\s*['\"]text/html",
        added_text,
        flags=re.IGNORECASE,
    )
    browser_behavior_signal = re.search(
        r"document\.|addEventListener\(|fetch\(|querySelector\(|innerHTML|textContent",
        added_text,
        flags=re.IGNORECASE,
    )
    if len(html_tags) >= 2 and (server_html_signal or browser_behavior_signal or re.search(r"<(?:script|style)\b", added_text, re.I)):
        categories.add("frontend")
    return categories


def scan_changes(repo: pathlib.Path, base: str | None, include_worktree: bool = False) -> dict[str, Any]:
    head = try_git(repo, "rev-parse", "HEAD")
    branch = try_git(repo, "branch", "--show-current") or "detached"
    merge_base: str | None = None
    file_map: dict[str, dict[str, Any]] = {}
    added_by_file: dict[str, str] = {}

    if head and base:
        merge_base = try_git(repo, "merge-base", "HEAD", base)
        if merge_base:
            name_status = git(repo, "diff", "--name-status", "--find-renames", f"{merge_base}..HEAD")
            numstat = parse_numstat(git(repo, "diff", "--numstat", f"{merge_base}..HEAD"))
            added_by_file.update(parse_added_lines(git(repo, "diff", "--unified=0", f"{merge_base}..HEAD")))
            for item in parse_name_status(name_status):
                path = item["path"]
                file_map[path] = {**item, **numstat.get(path, {})}
    elif head:
        parent = try_git(repo, "rev-parse", "HEAD^")
        if parent:
            merge_base = parent
            name_status = git(repo, "diff", "--name-status", "--find-renames", f"{parent}..HEAD")
            numstat = parse_numstat(git(repo, "diff", "--numstat", f"{parent}..HEAD"))
            added_by_file.update(parse_added_lines(git(repo, "diff", "--unified=0", f"{parent}..HEAD")))
            for item in parse_name_status(name_status):
                path = item["path"]
                file_map[path] = {**item, **numstat.get(path, {})}

    if include_worktree:
        if head:
            name_status = git(repo, "diff", "--name-status", "--find-renames", "HEAD")
            numstat = parse_numstat(git(repo, "diff", "--numstat", "HEAD"))
            working_added = parse_added_lines(git(repo, "diff", "--unified=0", "HEAD"))
            for changed_path, changed_text in working_added.items():
                added_by_file[changed_path] = (added_by_file.get(changed_path, "") + "\n" + changed_text).strip()
            for item in parse_name_status(name_status):
                path = item["path"]
                existing = file_map.get(path, {})
                file_map[path] = {**existing, **item, **numstat.get(path, {}), "working_tree": True}
        untracked = git(repo, "ls-files", "--others", "--exclude-standard", check=False)
        for path in untracked.splitlines():
            if path.strip():
                file_map[path] = {"status": "A", "path": path, "working_tree": True, "untracked": True}

    files: list[dict[str, Any]] = []
    surfaces: set[str] = set()
    additions = 0
    deletions = 0
    binary_files = 0
    for path in sorted(file_map):
        item = file_map[path]
        category_set = classify_path(path)
        category_set = augment_from_added_content(path, category_set, added_by_file.get(path, ""))
        categories = sorted(category_set)
        item["categories"] = categories
        surfaces.update(categories)
        if isinstance(item.get("added"), int):
            additions += int(item["added"])
        else:
            binary_files += 1 if "added" in item else 0
        if isinstance(item.get("deleted"), int):
            deletions += int(item["deleted"])
        files.append(item)

    code_surfaces = surfaces - {"docs", "config", "tests", "other"}
    frontend_files = [f for f in files if "frontend" in f["categories"]]
    backend_files = [f for f in files if {"backend", "database", "library"} & set(f["categories"])]

    if not files or not code_surfaces:
        recommendation = "none"
    elif frontend_files and backend_files:
        recommendation = "mixed"
    elif frontend_files:
        static_only = all(pathlib.PurePosixPath(f["path"]).suffix.lower() in {".css", ".scss", ".sass", ".less", ".html", ".htm"} for f in frontend_files)
        recommendation = "screenshot" if static_only else "browser"
    else:
        recommendation = "backend"

    line_delta = additions + deletions
    high_risk = bool(surfaces & {"security", "database"})
    if high_risk or len(files) > 40 or line_delta > 1200:
        risk = "high"
    elif ("frontend" in surfaces and bool(surfaces & {"backend", "library"})) or len(files) > 15 or line_delta > 400:
        risk = "medium"
    else:
        risk = "normal"

    dirty = bool(git(repo, "status", "--porcelain", check=False))
    return {
        "base": base,
        "merge_base": merge_base,
        "head": head,
        "branch": branch,
        "dirty": dirty,
        "files": files,
        "file_count": len(files),
        "additions": additions,
        "deletions": deletions,
        "binary_file_count": binary_files,
        "surfaces": sorted(surfaces),
        "risk": risk,
        "recommended_proof": recommendation,
    }


def atomic_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_manifest(run_dir: pathlib.Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"No manifest found at {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid manifest at {manifest_path}: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported manifest schema: {data.get('schema_version')}")
    return data


def save_manifest(run_dir: pathlib.Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    atomic_json(run_dir / "manifest.json", manifest)


def claim_by_id(manifest: dict[str, Any], claim_id: str) -> dict[str, Any]:
    for claim in manifest.get("claims", []):
        if claim.get("id") == claim_id:
            return claim
    raise RuntimeError(f"Unknown claim: {claim_id}")


def prune_old_temp_runs(max_age_hours: float = TEMP_RUN_MAX_AGE_HOURS) -> None:
    """Best-effort cleanup of abandoned Prove It temp runs."""
    root = pathlib.Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_hours * 3600
    for candidate in root.glob("prove-it-pr-*"):
        try:
            if not candidate.is_dir() or candidate.stat().st_mtime >= cutoff:
                continue
            manifest = candidate / "manifest.json"
            if not manifest.exists():
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("tool", {}).get("name") != "prove-it":
                continue
            shutil.rmtree(candidate)
        except (OSError, json.JSONDecodeError):
            continue


def default_run_dir(repo: pathlib.Path, head: str | None, dirty: bool, pr_number: int | None = None) -> pathlib.Path:
    prune_old_temp_runs()
    ref = (head or "no-head")[:8]
    prefix = f"prove-it-pr-{pr_number or 'local'}-{ref}-"
    return pathlib.Path(tempfile.mkdtemp(prefix=prefix)).resolve()


def gh_json(repo: pathlib.Path, args: Sequence[str], timeout: float = 20.0) -> dict[str, Any]:
    gh_path = shutil.which("gh")
    if not gh_path:
        raise RuntimeError("GitHub CLI (gh) is required to target and publish proof to a pull request")
    cp = run_capture([gh_path, *args], cwd=repo, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(redact(cp.stderr.strip() or cp.stdout.strip() or f"gh {' '.join(args)} failed"))
    try:
        value = json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned invalid JSON for {' '.join(args)}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"gh returned unexpected JSON for {' '.join(args)}")
    return value


def resolve_pr(repo: pathlib.Path, selector: str | None = None) -> dict[str, Any]:
    args = ["pr", "view"]
    if selector and selector != "current":
        args.append(str(selector))
    args.extend(["--json", "number,url,title,headRefOid,headRefName,baseRefName,isDraft,state"])
    pr = gh_json(repo, args)
    repo_info = gh_json(repo, ["repo", "view", "--json", "nameWithOwner"])
    local_repo = str(repo_info.get("nameWithOwner") or "")
    pr_url = str(pr.get("url") or "")
    parsed = urllib.parse.urlparse(pr_url)
    parts = [part for part in parsed.path.split("/") if part]
    url_repo = "/".join(parts[:2]) if len(parts) >= 4 and parts[2] == "pull" else ""
    if url_repo and local_repo and url_repo.casefold() != local_repo.casefold():
        raise RuntimeError(f"PR {pr_url} belongs to {url_repo}, but the current repository is {local_repo}")
    pr["repo"] = local_repo or url_repo
    return pr


def manifest_capture_sha(manifest: dict[str, Any]) -> str:
    target = manifest.get("target_pr") or {}
    return str(
        manifest.get("capture", {}).get("sha")
        or target.get("headRefOid")
        or manifest.get("change", {}).get("head")
        or ""
    )


def proof_scope_files(manifest: dict[str, Any]) -> set[str]:
    explicit = manifest.get("proof_scope", {}).get("files", [])
    files = {str(path) for path in explicit if isinstance(path, str) and path}
    if files:
        return files
    return {
        str(item.get("path"))
        for item in manifest.get("change", {}).get("files", [])
        if isinstance(item, dict) and item.get("path")
    }


def commit_exists(repo: pathlib.Path, sha: str) -> bool:
    if not sha:
        return False
    return run_capture(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo, timeout=10).returncode == 0


def fetch_pr_head(repo: pathlib.Path, pr_number: int, sha: str) -> bool:
    if commit_exists(repo, sha):
        return True
    attempts = [
        ["git", "fetch", "--quiet", "--no-tags", "origin", f"pull/{pr_number}/head"],
        ["git", "fetch", "--quiet", "--no-tags", "origin", sha],
    ]
    for command in attempts:
        cp = run_capture(command, cwd=repo, timeout=60)
        if cp.returncode == 0 and commit_exists(repo, sha):
            return True
    return False


def classify_pr_relationship(
    repo: pathlib.Path,
    manifest: dict[str, Any],
    current_pr: dict[str, Any],
) -> dict[str, Any]:
    capture_sha = manifest_capture_sha(manifest)
    current_sha = str(current_pr.get("headRefOid") or "")
    result: dict[str, Any] = {
        "kind": "unknown",
        "capture_sha": capture_sha,
        "head_at_publish": current_sha,
        "checked_at": utc_now(),
        "changed_files": [],
        "overlapping_files": [],
    }
    if capture_sha and current_sha == capture_sha:
        result["kind"] = "exact"
        return result
    if not capture_sha or not current_sha:
        return result
    if not fetch_pr_head(repo, int(current_pr.get("number") or 0), current_sha):
        return result

    ancestor = run_capture(
        ["git", "merge-base", "--is-ancestor", capture_sha, current_sha],
        cwd=repo,
        timeout=15,
    )
    if ancestor.returncode == 1:
        result["kind"] = "diverged"
        return result
    if ancestor.returncode != 0:
        return result

    changed = [
        line.strip()
        for line in git(repo, "diff", "--name-only", capture_sha, current_sha, check=False).splitlines()
        if line.strip()
    ]
    scope = proof_scope_files(manifest)
    overlap = sorted(scope.intersection(changed))
    result["changed_files"] = changed
    result["overlapping_files"] = overlap
    result["kind"] = "advanced-related" if overlap else "advanced-unrelated"
    return result


def pr_base_ref(repo: pathlib.Path, pr: dict[str, Any]) -> str:
    name = str(pr.get("baseRefName") or "")
    if not name:
        raise RuntimeError("Could not determine pull request base branch")
    for candidate in (f"origin/{name}", name):
        if run_capture(["git", "rev-parse", "--verify", "--quiet", candidate], cwd=repo, timeout=10).returncode == 0:
            return candidate
    raise RuntimeError(f"Pull request base branch is not available locally: {name}. Fetch it and rerun /prove-it.")


def resolved_budgets(config: dict[str, Any], mode: str) -> dict[str, Any]:
    budgets = dict(EXPANDED_BUDGETS if mode == "expanded" else DEFAULT_BUDGETS)
    cfg = config.get("budgets")
    if isinstance(cfg, dict):
        for key in budgets:
            value = cfg.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                budgets[key] = value
    return budgets


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_artifact_path(run_dir: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"Evidence path must be inside run directory after import: {path}") from exc


def import_artifact(run_dir: pathlib.Path, source: pathlib.Path, evidence_type: str, label: str, copy: bool = True) -> pathlib.Path:
    source = source.resolve()
    if not source.exists() or not source.is_file():
        raise RuntimeError(f"Evidence file does not exist: {source}")
    try:
        source.relative_to(run_dir.resolve())
        return source
    except ValueError:
        if not copy:
            raise RuntimeError("Evidence outside the run directory requires copying; omit --no-copy")

    group = "frontend" if evidence_type in MEDIA_EVIDENCE_TYPES or evidence_type in {"console", "errors", "trace", "har"} else "backend"
    dest_dir = run_dir / group
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{slug(label)}{source.suffix.lower()}"
    counter = 2
    while dest.exists() and sha256_file(dest) != sha256_file(source):
        dest = dest_dir / f"{slug(label)}-{counter}{source.suffix.lower()}"
        counter += 1
    if not dest.exists():
        shutil.copy2(source, dest)
    return dest


def png_dimensions(path: pathlib.Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
        if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", header[16:24])
    except OSError:
        return None
    return None


def video_duration(path: pathlib.Path) -> float | None:
    if not command_exists("ffprobe"):
        return None
    cp = run_capture(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=15,
    )
    if cp.returncode != 0:
        return None
    try:
        return round(float(cp.stdout.strip()), 3)
    except ValueError:
        return None


def evidence_metadata(path: pathlib.Path, evidence_type: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if evidence_type in IMAGE_EVIDENCE_TYPES and path.suffix.lower() == ".png":
        dims = png_dimensions(path)
        if dims:
            metadata["width"] = dims[0]
            metadata["height"] = dims[1]
    elif evidence_type == "video":
        duration = video_duration(path)
        if duration is not None:
            metadata["duration_seconds"] = duration
    return metadata


def make_evidence(
    *,
    run_dir: pathlib.Path,
    evidence_type: str,
    label: str,
    path: pathlib.Path,
    status: str,
    observed: str | None = None,
    details: dict[str, Any] | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": f"E{int(time.time() * 1000)}-{os.getpid()}",
        "type": evidence_type,
        "label": redact(label),
        "status": status,
        "path": relative_artifact_path(run_dir, path),
        "created_at": utc_now(),
        "metadata": evidence_metadata(path, evidence_type),
    }
    if observed:
        item["observed"] = redact(observed)
    if details:
        item["details"] = details
    if role:
        item["role"] = role
    return item


def update_claim_from_proof(claim: dict[str, Any], passed: bool, observed: str) -> None:
    claim["status"] = "passed" if passed else "failed"
    claim["observed"] = redact(observed)
    claim["verified_at"] = utc_now()


def cmd_scan(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    config, _ = load_project_config(repo)
    base = choose_base(repo, args.base, config)
    result = scan_changes(repo, base, include_worktree=args.working_tree)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Base: {result['base'] or '(none)'}")
        print(f"Files: {result['file_count']} (+{result['additions']} -{result['deletions']})")
        print(f"Surfaces: {', '.join(result['surfaces']) or 'none'}")
        print(f"Risk: {result['risk']}")
        print(f"Recommended proof: {result['recommended_proof']}")
        for item in result["files"]:
            print(f"  {item['status']} {item['path']} [{', '.join(item['categories'])}]")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    config, config_path = load_project_config(repo)

    target_pr: dict[str, Any] | None = None
    if args.pr:
        target_pr = resolve_pr(repo, None if args.pr == "current" else args.pr)
        remote_head = str(target_pr.get("headRefOid") or "")
        local_head = try_git(repo, "rev-parse", "HEAD") or ""
        if not remote_head or local_head != remote_head:
            raise RuntimeError(
                f"Local HEAD {local_head[:8] or '(none)'} does not match PR #{target_pr.get('number')} head "
                f"{remote_head[:8] or '(unknown)'}. Check out the PR head, pull latest, and rerun /prove-it."
            )
        if git(repo, "status", "--porcelain", check=False):
            raise RuntimeError("PR proof requires a clean working tree so evidence matches the pushed PR head")

    base_hint = args.base
    if target_pr and not base_hint:
        base_hint = pr_base_ref(repo, target_pr)
    base = choose_base(repo, base_hint, config)
    changes = scan_changes(repo, base, include_worktree=args.working_tree)
    out = pathlib.Path(args.out).expanduser().resolve() if args.out else default_run_dir(
        repo, changes.get("head"), changes.get("dirty", False), int(target_pr["number"]) if target_pr else None
    )
    out.mkdir(parents=True, exist_ok=True)
    for subdir in ("backend", "frontend"):
        (out / subdir).mkdir(exist_ok=True)

    run_id = out.name
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "prove-it", "version": TOOL_VERSION},
        "run": {
            "id": run_id,
            "title": redact(args.title or (str(target_pr.get("title")) if target_pr else "Implementation proof")),
            "created_at": utc_now(),
            "repo_root": str(repo),
            "artifact_dir": str(out),
            "ephemeral": args.out is None,
            "mode": args.mode,
            "config_path": config_path,
        },
        "target_pr": target_pr,
        "capture": {
            "sha": changes.get("head"),
            "started_at": utc_now(),
            "worktree_clean_at_start": not changes.get("dirty", False),
        },
        "change": changes,
        "budgets": resolved_budgets(config, args.mode),
        "review_path": [],
        "proof_scope": {"files": []},
        "claims": [],
        "notes": [],
        "summary": {"status": "pending", "passed": 0, "failed": 0, "not_proven": 0, "skipped": 0},
    }
    save_manifest(out, manifest)
    print(str(out))
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    claims = manifest.setdefault("claims", [])
    max_claims = int(manifest.get("budgets", {}).get("max_claims", DEFAULT_BUDGETS["max_claims"]))
    if len(claims) >= max_claims and not args.force:
        raise RuntimeError(f"Claim budget exhausted ({max_claims}). Use --force only for an intentionally expanded proof.")
    claim_id = args.id or f"C{len(claims) + 1}"
    if any(c.get("id") == claim_id for c in claims):
        raise RuntimeError(f"Claim already exists: {claim_id}")
    claim = {
        "id": claim_id,
        "text": redact(args.text),
        "expected": redact(args.expected),
        "method": args.method,
        "priority": args.priority,
        "status": "pending",
        "evidence": [],
        "created_at": utc_now(),
    }
    code_refs = add_proof_scope(manifest, args.code or [])
    if code_refs:
        claim["code"] = code_refs
    claims.append(claim)
    save_manifest(run_dir, manifest)
    print(claim_id)
    return 0


def cmd_review_step(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    steps = manifest.setdefault("review_path", [])
    if len(steps) >= 5 and not args.force:
        raise RuntimeError("Review path already has 5 steps. Use --force only when the extra step is necessary.")
    code_refs = add_proof_scope(manifest, args.code or [])
    steps.append(
        {
            "position": len(steps) + 1,
            "text": redact(args.text),
            "code": code_refs,
        }
    )
    save_manifest(run_dir, manifest)
    print(len(steps))
    return 0


def execute_with_timeout(
    command: Sequence[str] | str,
    *,
    cwd: pathlib.Path,
    timeout: float,
    shell: bool,
) -> tuple[int, str, str, bool, float]:
    started = time.monotonic()
    try:
        cp = run_capture(command, cwd=cwd, timeout=timeout, shell=shell)
        return cp.returncode, cp.stdout, cp.stderr, False, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode(errors="replace") if exc.stdout else "")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode(errors="replace") if exc.stderr else "")
        return 124, stdout, stderr, True, time.monotonic() - started


def cmd_run(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    claim = claim_by_id(manifest, args.claim)
    repo = pathlib.Path(manifest["run"]["repo_root"])
    cwd = (repo / args.cwd).resolve() if args.cwd else repo
    try:
        cwd.relative_to(repo.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Command cwd must stay within the repository: {cwd}") from exc

    if args.command:
        command: Sequence[str] | str = args.command
        shell = True
        display_command = args.command
    else:
        argv = list(args.argv or [])
        if argv and argv[0] == "--":
            argv = argv[1:]
        if not argv:
            raise RuntimeError("Provide a command after -- or use --command")
        command = argv
        shell = False
        display_command = shell_join(argv)

    returncode, stdout, stderr, timed_out, duration = execute_with_timeout(command, cwd=cwd, timeout=args.timeout, shell=shell)
    stdout, stdout_truncated = truncate(redact(stdout))
    stderr, stderr_truncated = truncate(redact(stderr))
    display_command = redact(display_command)

    passed = returncode == args.expect_exit and not timed_out
    assertion_lines = [f"exit == {args.expect_exit}: {'PASS' if returncode == args.expect_exit else 'FAIL'}"]
    combined = stdout + "\n" + stderr
    for expected in args.expect_output or []:
        ok = expected in combined
        passed = passed and ok
        assertion_lines.append(f"output contains {expected!r}: {'PASS' if ok else 'FAIL'}")
    for rejected in args.reject_output or []:
        ok = rejected not in combined
        passed = passed and ok
        assertion_lines.append(f"output excludes {rejected!r}: {'PASS' if ok else 'FAIL'}")
    if timed_out:
        assertion_lines.append(f"completed within {args.timeout}s: FAIL")

    log_dir = run_dir / "backend"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{args.claim.lower()}-{slug(args.label)}.txt"
    body = "\n".join(
        [
            f"$ {display_command}",
            f"cwd: {cwd}",
            f"duration_seconds: {duration:.3f}",
            f"exit_code: {returncode}",
            f"timed_out: {str(timed_out).lower()}",
            "assertions:",
            *[f"- {line}" for line in assertion_lines],
            "",
            "--- stdout ---",
            stdout.rstrip(),
            "",
            "--- stderr ---",
            stderr.rstrip(),
            "",
        ]
    )
    log_path.write_text(body, encoding="utf-8")

    observed = args.observed or (
        one_line(claim.get("text"), 180) if passed else f"{args.label} failed with exit {returncode}."
    )
    evidence = make_evidence(
        run_dir=run_dir,
        evidence_type=args.kind,
        label=args.label,
        path=log_path,
        status="passed" if passed else "failed",
        observed=observed,
        details={
            "command": display_command,
            "cwd": str(cwd.relative_to(repo)),
            "exit_code": returncode,
            "expected_exit": args.expect_exit,
            "duration_seconds": round(duration, 3),
            "timed_out": timed_out,
            "assertions": assertion_lines,
            "output_truncated": stdout_truncated or stderr_truncated,
        },
    )
    claim.setdefault("evidence", []).append(evidence)
    if args.proves:
        update_claim_from_proof(claim, passed, observed)
    save_manifest(run_dir, manifest)
    print(json.dumps({"passed": passed, "exit_code": returncode, "path": evidence["path"]}))
    return 0 if passed else 1


def parse_header(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise RuntimeError(f"Header must be NAME: VALUE: {value}")
    name, val = value.split(":", 1)
    return name.strip(), val.strip()


def dotted_get(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def parse_expected_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_http(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    claim = claim_by_id(manifest, args.claim)

    parsed = urllib.parse.urlparse(args.url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.hostname not in local_hosts and not args.allow_remote:
        raise RuntimeError("Remote HTTP proof is disabled by default. Use a local/dev URL or pass --allow-remote intentionally.")

    headers = dict(parse_header(value) for value in (args.header or []))
    env_header_sources: dict[str, str] = {}
    for mapping in args.header_env or []:
        if "=" not in mapping:
            raise RuntimeError(f"--header-env must be HEADER=ENV_VAR: {mapping}")
        header_name, env_name = mapping.split("=", 1)
        header_name = header_name.strip()
        env_name = env_name.strip()
        if not header_name or not env_name:
            raise RuntimeError(f"--header-env must be HEADER=ENV_VAR: {mapping}")
        value = os.environ.get(env_name)
        if value is None:
            raise RuntimeError(f"Environment variable is not set: {env_name}")
        headers[header_name] = value
        env_header_sources[header_name] = env_name
    data: bytes | None = None
    if args.data is not None:
        data = args.data.encode("utf-8")
    elif args.data_file:
        data = pathlib.Path(args.data_file).read_bytes()
    req = urllib.request.Request(args.url, data=data, headers=headers, method=args.method.upper())

    started = time.monotonic()
    response_headers: dict[str, str] = {}
    response_body = b""
    error: str | None = None
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as response:
            status = int(response.status)
            response_headers = dict(response.headers.items())
            response_body = response.read(args.max_bytes + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        response_headers = dict(exc.headers.items()) if exc.headers else {}
        response_body = exc.read(args.max_bytes + 1)
    except Exception as exc:  # network errors need to be evidence, not a stack trace
        status = 0
        error = f"{type(exc).__name__}: {exc}"
    duration = time.monotonic() - started
    truncated_body = len(response_body) > args.max_bytes
    response_body = response_body[: args.max_bytes]
    body_text = redact(response_body.decode("utf-8", errors="replace"))

    passed = status in args.expect_status
    assertions = [f"status in {args.expect_status}: {'PASS' if passed else 'FAIL'}"]
    for expected in args.expect_body or []:
        ok = expected in body_text
        passed = passed and ok
        assertions.append(f"body contains {expected!r}: {'PASS' if ok else 'FAIL'}")

    parsed_json: Any = None
    if args.expect_json:
        try:
            parsed_json = json.loads(body_text)
        except json.JSONDecodeError:
            passed = False
            assertions.append("response is valid JSON: FAIL")
        else:
            assertions.append("response is valid JSON: PASS")
            for expression in args.expect_json:
                if "=" not in expression:
                    raise RuntimeError(f"--expect-json must be path=value: {expression}")
                key, raw_expected = expression.split("=", 1)
                expected_value = parse_expected_value(raw_expected)
                try:
                    actual_value = dotted_get(parsed_json, key)
                    ok = actual_value == expected_value
                except KeyError:
                    actual_value = "[missing]"
                    ok = False
                passed = passed and ok
                assertions.append(f"json {key} == {expected_value!r}: {'PASS' if ok else 'FAIL'} (actual {actual_value!r})")
    if error:
        passed = False
        assertions.append(f"request completed: FAIL ({error})")

    log_dir = run_dir / "backend"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{args.claim.lower()}-{slug(args.label)}.txt"
    safe_headers = {
        k: (f"[FROM_ENV:{env_header_sources[k]}]" if k in env_header_sources else redact(f"{k}: {v}").split(":", 1)[1].strip())
        for k, v in headers.items()
    }
    safe_response_headers = {k: redact(f"{k}: {v}").split(":", 1)[1].strip() for k, v in response_headers.items()}
    body = "\n".join(
        [
            f"{args.method.upper()} {redact(args.url)}",
            f"duration_seconds: {duration:.3f}",
            f"status: {status}",
            f"error: {redact(error) if error else ''}",
            f"request_headers: {json.dumps(safe_headers, sort_keys=True)}",
            f"response_headers: {json.dumps(safe_response_headers, sort_keys=True)}",
            "assertions:",
            *[f"- {line}" for line in assertions],
            "",
            "--- response body ---",
            body_text,
            "\n[truncated]" if truncated_body else "",
        ]
    )
    log_path.write_text(body, encoding="utf-8")

    request_path = urllib.parse.urlparse(args.url).path or "/"
    observed = args.observed or f"{args.method.upper()} {request_path} returned {status}."
    evidence = make_evidence(
        run_dir=run_dir,
        evidence_type="http",
        label=args.label,
        path=log_path,
        status="passed" if passed else "failed",
        observed=observed,
        details={
            "method": args.method.upper(),
            "url": redact(args.url),
            "status": status,
            "expected_status": args.expect_status,
            "duration_seconds": round(duration, 3),
            "assertions": assertions,
            "body_truncated": truncated_body,
        },
    )
    claim.setdefault("evidence", []).append(evidence)
    if args.proves:
        update_claim_from_proof(claim, passed, observed)
    save_manifest(run_dir, manifest)
    print(json.dumps({"passed": passed, "status": status, "path": evidence["path"]}))
    return 0 if passed else 1


def cmd_add(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    claim = claim_by_id(manifest, args.claim)
    evidence_type = args.type
    if evidence_type not in ALL_EVIDENCE_TYPES:
        raise RuntimeError(f"Unsupported evidence type: {evidence_type}")
    if args.role and evidence_type not in MEDIA_EVIDENCE_TYPES:
        raise RuntimeError("--role is only valid for screenshots, videos, and diagrams")
    if evidence_type == "diagram" and args.proves:
        raise RuntimeError("A diagram can explain a claim but cannot prove runtime behavior; omit --proves")
    imported = import_artifact(run_dir, pathlib.Path(args.path), evidence_type, args.label, copy=not args.no_copy)
    passed = not args.failed
    evidence = make_evidence(
        run_dir=run_dir,
        evidence_type=evidence_type,
        label=args.label,
        path=imported,
        status="passed" if passed else "failed",
        observed=args.observed,
        role=args.role,
    )
    claim.setdefault("evidence", []).append(evidence)
    if args.proves:
        update_claim_from_proof(claim, passed, args.observed or args.label)
    save_manifest(run_dir, manifest)
    print(evidence["path"])
    return 0 if passed else 1


def cmd_status(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    claim = claim_by_id(manifest, args.claim)
    claim["status"] = args.status
    if args.observed:
        claim["observed"] = redact(args.observed)
    claim["verified_at"] = utc_now()
    save_manifest(run_dir, manifest)
    print(args.status)
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    manifest.setdefault("notes", []).append({"at": utc_now(), "text": redact(args.text)})
    save_manifest(run_dir, manifest)
    return 0


def visual_text_lines(value: Any, width: int = 34, max_lines: int = 3, break_long_words: bool = False) -> list[str]:
    clean = " ".join(str(value or "").split())
    wrapped = textwrap.wrap(
        clean,
        width=width,
        break_long_words=break_long_words,
        break_on_hyphens=break_long_words,
    ) or ["—"]
    selected = wrapped[:max_lines]
    if len(wrapped) > max_lines:
        selected[-1] = selected[-1].rstrip(".,;:") + "…"
    return selected


def svg_text_block(x: int, y: int, lines: list[str], fill: str = "#172033") -> str:
    return "".join(
        f'<text x="{x}" y="{y + index * 24}" fill="{fill}" font-size="17" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{html.escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def backend_visual_rows(manifest: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    review_path = [str(step.get("text") or "") for step in manifest.get("review_path", []) if isinstance(step, dict)]
    fallback_path = " → ".join(value for value in review_path if value)
    for claim in manifest.get("claims", []):
        if not isinstance(claim, dict) or claim.get("status") == "skipped":
            continue
        code = [normalize_code_ref(str(value)) for value in claim.get("code", []) if str(value).strip()]
        path = " → ".join(code[:2]) or fallback_path or str(claim.get("method") or "runtime check")
        rows.append(
            {
                "behavior": str(claim.get("text") or claim.get("expected") or "Behavior checked"),
                "path": path,
                "result": str(claim.get("observed") or claim.get("expected") or "No result recorded"),
                "status": str(claim.get("status") or "pending"),
            }
        )
        if len(rows) == 3:
            break
    return rows


def render_backend_visual(manifest: dict[str, Any], rows: list[dict[str, str]]) -> str:
    row_height = 154
    height = 154 + row_height * len(rows)
    capture_sha = manifest_capture_sha(manifest)[:8] or "unknown"
    status_colors = {"passed": "#13795b", "failed": "#c23b3b", "not_proven": "#a15c00", "pending": "#6b7280"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">',
        f'<rect width="1200" height="{height}" rx="24" fill="#f7f8fb"/>',
        '<text x="48" y="52" fill="#172033" font-size="28" font-weight="700" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">Backend behavior</text>',
        f'<text x="48" y="82" fill="#667085" font-size="15" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">captured at {html.escape(capture_sha)}</text>',
        '<text x="52" y="126" fill="#667085" font-size="13" font-weight="700" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">BEHAVIOR CHECKED</text>',
        '<text x="424" y="126" fill="#667085" font-size="13" font-weight="700" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">CODE PATH</text>',
        '<text x="794" y="126" fill="#667085" font-size="13" font-weight="700" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">OBSERVED RESULT</text>',
    ]
    for index, row in enumerate(rows):
        top = 142 + index * row_height
        text_y = top + 42
        color = status_colors.get(row["status"], "#6b7280")
        parts.extend(
            [
                f'<rect x="48" y="{top}" width="304" height="126" rx="14" fill="#ffffff" stroke="#d8deea"/>',
                f'<rect x="418" y="{top}" width="304" height="126" rx="14" fill="#ffffff" stroke="#d8deea"/>',
                f'<rect x="788" y="{top}" width="364" height="126" rx="14" fill="#ffffff" stroke="{color}" stroke-width="2"/>',
                f'<path d="M364 {top + 63} H406" stroke="#98a2b3" stroke-width="2"/><path d="M396 {top + 55} L406 {top + 63} L396 {top + 71}" fill="none" stroke="#98a2b3" stroke-width="2"/>',
                f'<path d="M734 {top + 63} H776" stroke="#98a2b3" stroke-width="2"/><path d="M766 {top + 55} L776 {top + 63} L766 {top + 71}" fill="none" stroke="#98a2b3" stroke-width="2"/>',
                svg_text_block(66, text_y, visual_text_lines(row["behavior"], 29)),
                svg_text_block(436, text_y, visual_text_lines(row["path"], 29, break_long_words=True)),
                svg_text_block(806, text_y, visual_text_lines(row["result"], 35), color),
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def cmd_visualize(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    rows = backend_visual_rows(manifest)
    if not rows:
        raise RuntimeError("No backend claim results are available to visualize")
    output = run_dir / "frontend" / "backend-behavior.svg"
    output.parent.mkdir(exist_ok=True)
    output.write_text(render_backend_visual(manifest, rows), encoding="utf-8")
    first_claim = next(claim for claim in manifest.get("claims", []) if isinstance(claim, dict) and claim.get("status") != "skipped")
    evidence = [
        item
        for item in first_claim.get("evidence", [])
        if not (
            isinstance(item, dict)
            and isinstance(item.get("details"), dict)
            and item["details"].get("generated_by") == "prove-it"
        )
    ]
    evidence.append(
        make_evidence(
            run_dir=run_dir,
            evidence_type="diagram",
            label="Backend behavior",
            path=output,
            status="passed",
            observed="Backend behavior map generated from the recorded checks.",
            details={"generated_by": "prove-it"},
            role="detail",
        )
    )
    first_claim["evidence"] = evidence
    save_manifest(run_dir, manifest)
    print(relative_artifact_path(run_dir, output))
    return 0


def scan_for_secrets(path: pathlib.Path) -> list[str]:
    try:
        if path.stat().st_size > 2_000_000:
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings: list[str] = []
    for label, pattern in STRONG_SECRET_DETECTORS:
        if pattern.search(text):
            findings.append(label)
    return findings


def validate_manifest(run_dir: pathlib.Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    counts = {"passed": 0, "failed": 0, "not_proven": 0, "skipped": 0, "pending": 0}
    evidence_counts: dict[str, int] = {}
    command_count = 0
    max_video_duration = 0.0

    capture_sha = manifest_capture_sha(manifest)
    if not capture_sha:
        errors.append("capture SHA is missing")

    review_path = manifest.get("review_path", [])
    if not isinstance(review_path, list):
        errors.append("review_path must be an array")
        review_path = []
    if len(review_path) > 5:
        warnings.append(f"review path exceeds 5 steps: {len(review_path)}")
    for index, step in enumerate(review_path, start=1):
        if not isinstance(step, dict) or not str(step.get("text") or "").strip():
            errors.append(f"review step {index} is missing text")
            continue
        for code_ref in step.get("code", []):
            try:
                parse_code_ref(str(code_ref))
            except RuntimeError as exc:
                errors.append(f"review step {index}: {exc}")

    claims = manifest.get("claims", [])
    if not isinstance(claims, list):
        errors.append("claims must be an array")
        claims = []
    ids: set[str] = set()
    for claim in claims:
        cid = str(claim.get("id", ""))
        if not cid:
            errors.append("claim missing id")
        elif cid in ids:
            errors.append(f"duplicate claim id: {cid}")
        ids.add(cid)
        status = claim.get("status", "pending")
        if status not in counts:
            errors.append(f"{cid}: invalid status {status}")
        else:
            counts[status] += 1
        if status == "passed" and not claim.get("evidence") and claim.get("method") != "static":
            warnings.append(f"{cid}: marked passed without evidence")
        evidence_types = {
            str(item.get("type") or "")
            for item in claim.get("evidence", [])
            if isinstance(item, dict)
        }
        method = str(claim.get("method") or "")
        if status == "passed" and method == "browser" and not evidence_types.intersection({"screenshot", "video"}):
            errors.append(f"{cid}: browser claim is marked passed without a screenshot or video")
        if status == "passed" and method == "screenshot" and "screenshot" not in evidence_types:
            errors.append(f"{cid}: screenshot claim is marked passed without screenshot evidence")
        if status == "passed" and method == "video" and "video" not in evidence_types:
            errors.append(f"{cid}: video claim is marked passed without video evidence")
        for code_ref in claim.get("code", []):
            try:
                parse_code_ref(str(code_ref))
            except RuntimeError as exc:
                errors.append(f"{cid}: {exc}")
        for evidence in claim.get("evidence", []):
            etype = evidence.get("type", "unknown")
            evidence_counts[etype] = evidence_counts.get(etype, 0) + 1
            details = evidence.get("details", {})
            if details.get("command") or etype == "http":
                command_count += 1
            rel = evidence.get("path")
            if not rel:
                errors.append(f"{cid}: evidence missing path")
                continue
            path = (run_dir / rel).resolve()
            try:
                path.relative_to(run_dir.resolve())
            except ValueError:
                errors.append(f"{cid}: evidence path escapes run directory: {rel}")
                continue
            if not path.exists():
                errors.append(f"{cid}: evidence file missing: {rel}")
                continue
            expected_hash = evidence.get("metadata", {}).get("sha256")
            if expected_hash and sha256_file(path) != expected_hash:
                errors.append(f"{cid}: evidence hash mismatch: {rel}")
            if etype == "video":
                duration = evidence.get("metadata", {}).get("duration_seconds")
                if isinstance(duration, (int, float)):
                    max_video_duration = max(max_video_duration, float(duration))
                elif command_exists("ffprobe"):
                    warnings.append(f"{cid}: could not determine video duration: {rel}")
            for finding in scan_for_secrets(path):
                errors.append(f"{cid}: possible {finding} in {rel}")

    recommendation = str(manifest.get("change", {}).get("recommended_proof") or "none")
    if recommendation in VISUAL_PROOF_RECOMMENDATIONS:
        visual_claims = [claim for claim in claims if str(claim.get("method") or "") in VISUAL_CLAIM_METHODS]
        if not visual_claims:
            errors.append(
                "UI-facing change has no visual claim. Add a browser, screenshot, or video claim; "
                "if the real UI cannot be reached, mark that claim not_proven and state why."
            )
    if recommendation == "backend" and claims and not evidence_counts.get("diagram"):
        warnings.append("Backend proof has no behavior diagram. Run `prove-it visualize --dir <proof-dir>`; publish will generate it if omitted.")

    budgets = manifest.get("budgets", DEFAULT_BUDGETS)
    if len(claims) > int(budgets.get("max_claims", DEFAULT_BUDGETS["max_claims"])):
        warnings.append(f"claim budget exceeded: {len(claims)}")
    if command_count > int(budgets.get("max_commands", DEFAULT_BUDGETS["max_commands"])):
        warnings.append(f"command budget exceeded: {command_count}")
    if evidence_counts.get("screenshot", 0) > int(budgets.get("max_screenshots", DEFAULT_BUDGETS["max_screenshots"])):
        warnings.append(f"screenshot budget exceeded: {evidence_counts.get('screenshot', 0)}")
    if evidence_counts.get("video", 0) > int(budgets.get("max_videos", DEFAULT_BUDGETS["max_videos"])):
        warnings.append(f"video budget exceeded: {evidence_counts.get('video', 0)}")
    if evidence_counts.get("diagram", 0) > int(budgets.get("max_diagrams", DEFAULT_BUDGETS["max_diagrams"])):
        warnings.append(f"diagram budget exceeded: {evidence_counts.get('diagram', 0)}")
    max_allowed_duration = float(budgets.get("max_video_seconds", DEFAULT_BUDGETS["max_video_seconds"]))
    if max_video_duration > max_allowed_duration:
        warnings.append(f"video exceeds duration budget: {max_video_duration:.1f}s > {max_allowed_duration:.1f}s")

    relationship = manifest.get("relationship")
    if relationship is not None:
        valid_relationships = {"exact", "advanced-unrelated", "advanced-related", "diverged", "unknown"}
        kind = relationship.get("kind") if isinstance(relationship, dict) else None
        if kind not in valid_relationships:
            errors.append(f"invalid commit relationship: {kind}")

    if counts["failed"]:
        status = "failed"
    elif counts["pending"] or counts["not_proven"]:
        status = "partial"
    elif claims and counts["passed"] + counts["skipped"] == len(claims):
        status = "passed"
    else:
        status = "no-proof"

    return {
        "status": status,
        "claims": len(claims),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "not_proven": counts["not_proven"] + counts["pending"],
        "skipped": counts["skipped"],
        "evidence": evidence_counts,
        "commands": command_count,
        "longest_video_seconds": max_video_duration,
        "errors": errors,
        "warnings": warnings,
    }


def cmd_validate(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    result = validate_manifest(run_dir, manifest)
    manifest["summary"] = {k: v for k, v in result.items() if k not in {"errors", "warnings"}}
    manifest["validation"] = {"at": utc_now(), "errors": result["errors"], "warnings": result["warnings"]}
    save_manifest(run_dir, manifest)
    print(json.dumps(result, indent=2))
    if result["errors"]:
        return 1
    if args.strict and result["status"] != "passed" and result["status"] != "no-proof":
        return 1
    return 0


def status_label(status: str) -> str:
    return {
        "passed": "Verified",
        "failed": "Failed",
        "not_proven": "Not proved",
        "pending": "Not proved",
        "skipped": "Skipped",
    }.get(status, "Not proved")


def evidence_role(evidence: dict[str, Any]) -> str:
    explicit = str(evidence.get("role") or "")
    if explicit in {"primary", "before", "after", "final", "detail"}:
        return explicit
    hint = f"{evidence.get('label', '')} {evidence.get('path', '')}".casefold()
    for role in ("before", "after", "final"):
        if role in hint:
            return role
    if evidence.get("type") == "video":
        return "primary"
    return "detail"


def markdown_alt(value: str) -> str:
    return re.sub(r"[\[\]\r\n]+", " ", value).strip() or "Prove It visual"


def bounded_excerpt(text: str, *, max_lines: int = 6, max_chars: int = 700) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    selected: list[str] = []
    used = 0
    for line in lines:
        clean = redact(line)
        remaining = max_chars - used
        if remaining <= 0 or len(selected) >= max_lines:
            break
        if len(clean) > remaining:
            clean = clean[: max(1, remaining - 3)].rstrip() + "..."
        selected.append(clean)
        used += len(clean)
    if len(lines) > len(selected) and selected:
        selected[-1] = selected[-1].rstrip(".") + "..."
    return selected


def evidence_excerpt(run_dir: pathlib.Path, evidence: dict[str, Any]) -> list[str]:
    rel = str(evidence.get("path") or "")
    if not rel:
        return []
    path = (run_dir / rel).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    etype = str(evidence.get("type") or "")
    if etype == "http" and "--- response body ---" in text:
        text = text.split("--- response body ---", 1)[1]
    elif "--- stdout ---" in text:
        text = text.split("--- stdout ---", 1)[1]
        if "--- stderr ---" in text:
            text = text.split("--- stderr ---", 1)[0]
    else:
        return []
    return bounded_excerpt(text)


def receipt_lines(run_dir: pathlib.Path, evidence: dict[str, Any]) -> list[str]:
    etype = str(evidence.get("type") or "evidence")
    details = evidence.get("details") if isinstance(evidence.get("details"), dict) else {}
    lines: list[str] = []

    if etype == "http":
        parsed = urllib.parse.urlparse(str(details.get("url") or ""))
        target = parsed.path or "/"
        lines.append(f"{details.get('method', 'HTTP')} {target}")
        lines.append(f"status: {details.get('status', 'unknown')}")
    else:
        lines.append(f"result: {str(evidence.get('status') or 'unknown')}")
        if "exit_code" in details:
            lines.append(f"exit: {details.get('exit_code')}")

    assertions = [str(value) for value in details.get("assertions", []) if str(value).strip()]
    for assertion in assertions[:4]:
        lines.append(f"assert: {assertion}")
    if len(assertions) > 4:
        lines.append(f"assert: {len(assertions) - 4} more checks recorded")

    excerpt = evidence_excerpt(run_dir, evidence)
    if excerpt:
        lines.append("output:")
        lines.extend(f"  {line}" for line in excerpt)
    return lines


def proof_comment_marker(manifest: dict[str, Any]) -> str:
    run_id = slug(str(manifest.get("run", {}).get("id") or "proof-run"), "proof-run")
    capture_sha = manifest_capture_sha(manifest)
    return f"<!-- prove-it:run id={run_id} capture-sha={capture_sha} -->"


def compact_command(command: str, limit: int = 160) -> str:
    command = " ".join(command.split())
    if len(command) <= limit:
        return command
    return command[: limit - 1].rstrip() + "…"


def commit_markdown(manifest: dict[str, Any], sha: str) -> str:
    short = sha[:8] if sha else "unknown"
    target = manifest.get("target_pr") or {}
    repo_name = str(target.get("repo") or "")
    if repo_name and sha:
        return f"[`{short}`](https://github.com/{repo_name}/commit/{sha})"
    return f"`{short}`"


def code_ref_markdown(manifest: dict[str, Any], value: str) -> str:
    path, start, end = parse_code_ref(value)
    label = normalize_code_ref(value)
    target = manifest.get("target_pr") or {}
    repo_name = str(target.get("repo") or "")
    sha = manifest_capture_sha(manifest)
    if not repo_name or not sha:
        return f"`{label}`"
    encoded_path = urllib.parse.quote(path, safe="/")
    anchor = ""
    if start is not None:
        anchor = f"#L{start}" if start == end else f"#L{start}-L{end}"
    return f"[`{label}`](https://github.com/{repo_name}/blob/{sha}/{encoded_path}{anchor})"


def code_refs_markdown(manifest: dict[str, Any], refs: Iterable[str]) -> str:
    values = [code_ref_markdown(manifest, str(value)) for value in refs]
    return "<br>".join(values) if values else "—"


def one_line(value: Any, limit: int = 180) -> str:
    text = redact(" ".join(str(value or "").split()))
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def relationship_lines(manifest: dict[str, Any]) -> list[str]:
    relationship = manifest.get("relationship")
    capture_sha = manifest_capture_sha(manifest)
    target = manifest.get("target_pr") or {}
    if not isinstance(relationship, dict):
        relationship = {
            "kind": "exact",
            "capture_sha": capture_sha,
            "head_at_publish": str(target.get("headRefOid") or capture_sha),
            "changed_files": [],
            "overlapping_files": [],
        }

    kind = str(relationship.get("kind") or "unknown")
    current_sha = str(relationship.get("head_at_publish") or "")
    capture = commit_markdown(manifest, capture_sha)
    current = commit_markdown(manifest, current_sha)
    status = str(manifest.get("summary", {}).get("status") or "no-proof")

    if status == "failed":
        lead = f"Tested on {capture} and hit a failure."
    elif status == "partial":
        lead = f"Tested on {capture}, but I couldn't check everything."
    elif status == "passed":
        lead = f"Tested on {capture}."
    else:
        lead = f"I couldn't get a useful runtime check on {capture}."

    freshness = ""
    if kind != "exact":
        lead += f" The PR is now {current}."
        if kind == "advanced-unrelated":
            freshness = "I didn't rerun the latest head. None of the files I checked changed afterward."
        elif kind == "advanced-related":
            overlap = [str(path) for path in relationship.get("overlapping_files", [])]
            named = ", ".join(f"`{path}`" for path in overlap[:3])
            if len(overlap) > 3:
                named += f", and {len(overlap) - 3} more"
            freshness = "I didn't rerun the latest head."
            freshness += f" {named} changed afterward." if named else " Files I checked changed afterward."
        elif kind == "diverged":
            freshness = "The PR no longer contains the commit I tested."
        else:
            freshness = "I couldn't tell how the current head relates to the commit I tested."

    lines = [
        "<!-- prove-it:relationship:start -->",
        lead,
    ]

    seen: set[str] = set()
    for claim in [claim for claim in manifest.get("claims", []) if isinstance(claim, dict)][:3]:
        value = one_line(claim.get("observed") or claim.get("expected") or claim.get("text"), limit=180)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        lines.append("") if len(seen) == 1 else None
        lines.append(f"- {value}")

    if freshness:
        lines.extend(["", freshness])

    lines.append("<!-- prove-it:relationship:end -->")
    return lines


def cmd_render(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    validation = validate_manifest(run_dir, manifest)
    manifest["summary"] = {k: v for k, v in validation.items() if k not in {"errors", "warnings"}}
    manifest["validation"] = {"at": utc_now(), "errors": validation["errors"], "warnings": validation["warnings"]}
    save_manifest(run_dir, manifest)

    claims = [claim for claim in manifest.get("claims", []) if isinstance(claim, dict)]
    media: list[dict[str, Any]] = []
    diagnostics: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for claim in claims:
        for item in claim.get("evidence", []):
            if not isinstance(item, dict):
                continue
            etype = str(item.get("type") or "")
            if etype in MEDIA_EVIDENCE_TYPES:
                enriched = dict(item)
                enriched["claim_id"] = claim.get("id")
                enriched["claim_text"] = claim.get("text")
                media.append(enriched)
            elif etype in {"console", "errors", "trace", "har"}:
                diagnostics.append((claim, item))

    videos = [item for item in media if item.get("type") == "video"]
    screenshots = [item for item in media if item.get("type") == "screenshot"]
    diagrams = [item for item in media if item.get("type") == "diagram"]

    lines: list[str] = [
        proof_comment_marker(manifest),
        "## QA",
        "",
        *relationship_lines(manifest),
    ]

    # Show real product artifacts immediately. Headings are unnecessary when the
    # media already explains its shape.
    for item in videos:
        lines.extend(["", f"![](./{item['path']})"])

    before = [item for item in screenshots if evidence_role(item) == "before"]
    after = [item for item in screenshots if evidence_role(item) == "after"]
    paired_paths: set[str] = set()
    if before and after:
        left, right = before[0], after[0]
        paired_paths.update({str(left["path"]), str(right["path"])})
        lines.extend(
            [
                "",
                "| Before | After |",
                "|:---:|:---:|",
                f"| ![{markdown_alt(str(left.get('label') or 'Before'))}](./{left['path']}) | ![{markdown_alt(str(right.get('label') or 'After'))}](./{right['path']}) |",
            ]
        )

    for item in [item for item in screenshots if str(item.get("path")) not in paired_paths]:
        label = markdown_alt(str(item.get("label") or "Screenshot"))
        lines.extend(["", f"![{label}](./{item['path']})"])

    for item in diagrams:
        label = markdown_alt(str(item.get("label") or "Diagram"))
        lines.extend(["", f"![{label}](./{item['path']})"])

    notes = [one_line(item.get("text"), limit=240) for item in manifest.get("notes", []) if isinstance(item, dict) and item.get("text")]
    if notes:
        lines.extend(["", notes[0]])

    runtime_items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for claim in claims:
        for item in claim.get("evidence", []):
            if (
                isinstance(item, dict)
                and str(item.get("type") or "") not in MEDIA_EVIDENCE_TYPES | {"console", "errors", "trace", "har"}
            ):
                runtime_items.append((claim, item))

    review_path = [step for step in manifest.get("review_path", []) if isinstance(step, dict)]
    code_refs: list[str] = []
    for claim in claims:
        for ref in claim.get("code", []):
            normalized = normalize_code_ref(str(ref))
            if normalized not in code_refs:
                code_refs.append(normalized)

    extra_notes = notes[1:]
    has_details = bool(runtime_items or review_path or code_refs or diagnostics or extra_notes or validation["warnings"])
    if has_details:
        lines.extend(["", "<details>", "<summary>What I ran</summary>", ""])

        multiple_runtime = len(runtime_items) > 1
        for _claim, item in runtime_items:
            item_details = item.get("details") if isinstance(item.get("details"), dict) else {}
            command = one_line(item_details.get("command"), limit=220)
            if multiple_runtime:
                lines.append(f"**{one_line(item.get('label') or item.get('type') or 'Check', 100)}**")
                lines.append("")
            if command:
                lines.append(f"`{compact_command(command, 220)}`")
            block = receipt_lines(run_dir, item)
            if block:
                if command:
                    lines.append("")
                lines.extend(["```text", *block, "```"] )
            lines.append("")

        if review_path:
            steps = [one_line(step.get("text"), limit=90).rstrip(".") for step in review_path if step.get("text")]
            if steps:
                lines.append("Path: " + " → ".join(steps))
                lines.append("")

        if code_refs:
            lines.extend([f"Code: {code_refs_markdown(manifest, code_refs)}", ""])

        if diagnostics:
            for _claim, item in diagnostics:
                etype = str(item.get("type") or "diagnostic")
                if etype == "console" and item.get("metadata", {}).get("bytes") == 0:
                    lines.append("Console: no new output")
                elif etype == "errors" and item.get("metadata", {}).get("bytes") == 0:
                    lines.append("Page errors: none")
                else:
                    lines.append(f"{one_line(item.get('label') or etype, 80)}: {one_line(item.get('observed') or item.get('status'), 180)}")
            lines.append("")

        for note in extra_notes:
            lines.append(note)
        for warning in validation["warnings"]:
            lines.append(one_line(warning, 240))
        if extra_notes or validation["warnings"]:
            lines.append("")

        while lines and lines[-1] == "":
            lines.pop()
        lines.extend(["", "</details>"])

    lines.extend(["", "<!-- prove-it:end -->"])
    (run_dir / "proof.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    attachments: list[str] = []
    for rel in [str(item.get("path") or "") for item in media]:
        if rel and rel not in attachments:
            attachments.append(rel)
    atomic_json(run_dir / "attachments.json", {"files": attachments})

    print(str(run_dir / "proof.md"))
    return 1 if validation["errors"] else 0

def gh_supports_comment_attach(repo: pathlib.Path) -> bool:
    gh_path = shutil.which("gh")
    if not gh_path:
        return False
    try:
        cp = run_capture([gh_path, "pr", "comment", "--help"], cwd=repo, timeout=8)
    except subprocess.TimeoutExpired:
        return False
    return cp.returncode == 0 and "--attach" in (cp.stdout + cp.stderr)


def gh_json_value(repo: pathlib.Path, args: Sequence[str], timeout: float = 20.0) -> Any:
    gh_path = shutil.which("gh")
    if not gh_path:
        raise RuntimeError("GitHub CLI (gh) is required to publish proof")
    cp = run_capture([gh_path, *args], cwd=repo, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(redact(cp.stderr.strip() or cp.stdout.strip() or f"gh {' '.join(args)} failed"))
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned invalid JSON for {' '.join(args)}") from exc


def flatten_comments(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "body" in value and "id" in value:
            found.append(value)
    elif isinstance(value, list):
        for item in value:
            found.extend(flatten_comments(item))
    return found


def comment_id_from_output(output: str) -> int | None:
    matches = re.findall(r"#issuecomment-(\d+)", output)
    return int(matches[-1]) if matches else None


def fetch_comment(repo: pathlib.Path, repo_name: str, comment_id: int) -> dict[str, Any]:
    value = gh_json_value(repo, ["api", f"repos/{repo_name}/issues/comments/{comment_id}"])
    if not isinstance(value, dict):
        raise RuntimeError(f"GitHub returned an invalid comment payload for {comment_id}")
    return value


def find_published_comment(
    repo: pathlib.Path,
    repo_name: str,
    pr_number: int,
    manifest: dict[str, Any],
    command_output: str,
) -> dict[str, Any] | None:
    comment_id = comment_id_from_output(command_output)
    if comment_id is not None:
        try:
            return fetch_comment(repo, repo_name, comment_id)
        except RuntimeError:
            pass

    marker = proof_comment_marker(manifest)
    try:
        value = gh_json_value(
            repo,
            ["api", "--paginate", "--slurp", f"repos/{repo_name}/issues/{pr_number}/comments?per_page=100"],
            timeout=60,
        )
    except RuntimeError:
        return None
    for comment in reversed(flatten_comments(value)):
        if marker in str(comment.get("body") or ""):
            return comment
    return None


def update_comment_body(
    repo: pathlib.Path,
    repo_name: str,
    comment_id: int,
    body: str,
    run_dir: pathlib.Path,
    timeout: float,
) -> dict[str, Any]:
    payload = run_dir / "comment-update.json"
    atomic_json(payload, {"body": body})
    value = gh_json_value(
        repo,
        ["api", "--method", "PATCH", f"repos/{repo_name}/issues/comments/{comment_id}", "--input", str(payload)],
        timeout=timeout,
    )
    if not isinstance(value, dict):
        raise RuntimeError("GitHub returned an invalid updated-comment payload")
    return value


def unresolved_attachment_refs(body: str, attachments: Iterable[str]) -> list[str]:
    unresolved: list[str] = []
    for rel in attachments:
        if f"](./{rel})" in body or f"]({rel})" in body or f"![](./{rel})" in body or f"![]({rel})" in body:
            unresolved.append(rel)
    return unresolved


def resolve_publish_target(
    run_dir: pathlib.Path,
    manifest: dict[str, Any],
    selector: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target = manifest.get("target_pr")
    if not isinstance(target, dict) or not target.get("number"):
        raise RuntimeError("This proof run is not bound to a pull request. Re-run /prove-it against an existing PR.")
    repo = pathlib.Path(manifest["run"]["repo_root"]).resolve()
    expected_number = int(target["number"])
    if selector and selector != "current":
        current = resolve_pr(repo, selector)
        if int(current.get("number", -1)) != expected_number:
            raise RuntimeError(f"Proof targets PR #{expected_number}, not PR #{current.get('number')}")
    else:
        current = resolve_pr(repo, str(expected_number))
    expected_repo = target.get("repo")
    if expected_repo and current.get("repo") != expected_repo:
        raise RuntimeError(f"Proof targets {expected_repo} but current PR resolved in {current.get('repo')}")
    capture_sha = manifest_capture_sha(manifest)
    local_head = try_git(repo, "rev-parse", "HEAD") or ""
    if not capture_sha or local_head != capture_sha:
        raise RuntimeError(
            f"Local HEAD moved after capture: expected {capture_sha[:8] or '(unknown)'}, "
            f"found {local_head[:8] or '(none)'}. Check out the captured commit or rerun /prove-it."
        )
    if git(repo, "status", "--porcelain", check=False):
        raise RuntimeError("Working tree changed after proof capture; clean it or rerun /prove-it before attaching evidence")
    if str(current.get("state") or "OPEN").upper() != "OPEN":
        raise RuntimeError(f"PR #{expected_number} is not open")
    relationship = classify_pr_relationship(repo, manifest, current)
    return current, relationship


def safe_cleanup_run(run_dir: pathlib.Path) -> None:
    run_dir = run_dir.resolve()
    manifest = load_manifest(run_dir)
    if manifest.get("tool", {}).get("name") != "prove-it":
        raise RuntimeError(f"Refusing to delete non-Prove-It directory: {run_dir}")
    recorded = pathlib.Path(str(manifest.get("run", {}).get("artifact_dir", ""))).resolve()
    if recorded != run_dir:
        raise RuntimeError(f"Manifest artifact directory mismatch; refusing cleanup: {run_dir}")
    if run_dir == pathlib.Path(run_dir.anchor):
        raise RuntimeError("Refusing to delete filesystem root")
    shutil.rmtree(run_dir)


def replace_relationship_block(body: str, manifest: dict[str, Any]) -> str:
    replacement = "\n".join(relationship_lines(manifest))
    pattern = re.compile(
        r"(?ms)^<!-- prove-it:relationship:start -->[ \t]*\n.*?^<!-- prove-it:relationship:end -->[ \t]*"
    )
    if not pattern.search(body):
        raise RuntimeError("Published Prove It section is missing its relationship block")
    return pattern.sub(replacement, body, count=1)


def cmd_publish(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    recommendation = str(manifest.get("change", {}).get("recommended_proof") or "none")
    has_visual = any(
        isinstance(item, dict) and str(item.get("type") or "") in MEDIA_EVIDENCE_TYPES
        for claim in manifest.get("claims", [])
        if isinstance(claim, dict)
        for item in claim.get("evidence", [])
    )
    if recommendation == "backend" and manifest.get("claims") and not has_visual:
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_visualize(argparse.Namespace(dir=str(run_dir)))
        manifest = load_manifest(run_dir)
    repo = pathlib.Path(manifest["run"]["repo_root"]).resolve()
    current_pr, relationship = resolve_publish_target(run_dir, manifest, args.pr)
    manifest["relationship"] = relationship
    save_manifest(run_dir, manifest)
    validation = validate_manifest(run_dir, manifest)
    if validation["errors"]:
        raise RuntimeError("Proof contains validation errors and cannot be published: " + "; ".join(validation["errors"]))
    if not gh_supports_comment_attach(repo):
        raise RuntimeError("Installed GitHub CLI does not support `gh pr comment --attach`; upgrade gh before publishing proof")

    with contextlib.redirect_stdout(io.StringIO()):
        render_rc = cmd_render(argparse.Namespace(dir=str(run_dir)))
    if render_rc != 0:
        raise RuntimeError("Proof rendering failed validation")

    # cmd_render persists the final summary used by the at-a-glance callout.
    # Reload before a later head refresh so relationship updates do not overwrite it
    # with the pre-render pending summary held by this function.
    manifest = load_manifest(run_dir)
    body_path = run_dir / "proof.md"
    attachments_data = json.loads((run_dir / "attachments.json").read_text(encoding="utf-8"))
    attachments = [str(item) for item in attachments_data.get("files", [])]
    gh_path = shutil.which("gh")
    assert gh_path is not None
    repo_name = str(current_pr.get("repo") or manifest.get("target_pr", {}).get("repo") or "")
    command = [
        gh_path,
        "pr",
        "comment",
        str(current_pr["number"]),
        "--repo",
        repo_name,
        "--body-file",
        str(body_path),
    ]
    for rel in attachments:
        candidate = (run_dir / rel).resolve()
        try:
            candidate.relative_to(run_dir)
        except ValueError as exc:
            raise RuntimeError(f"Attachment path escapes proof directory: {rel}") from exc
        if not candidate.exists():
            raise RuntimeError(f"Attachment missing before publish: {rel}")
        command.extend(["--attach", rel])

    cp = run_capture(command, cwd=run_dir, timeout=args.timeout)
    output = redact((cp.stdout + "\n" + cp.stderr).strip())
    comment = find_published_comment(
        repo,
        repo_name,
        int(current_pr["number"]),
        manifest,
        output,
    )
    if comment is None:
        if cp.returncode != 0:
            raise RuntimeError(f"gh pr comment failed and no proof comment was found: {output}")
        raise RuntimeError("gh pr comment returned success but the published proof comment could not be found")

    comment_id = int(comment.get("id") or 0)
    body = str(comment.get("body") or "")
    unresolved = unresolved_attachment_refs(body, attachments)
    if unresolved:
        outcome = "failed" if cp.returncode != 0 else "returned success"
        raise RuntimeError(
            f"gh pr comment {outcome}, but local attachment references remain in the comment: " + ", ".join(unresolved)
        )
    if proof_comment_marker(manifest) not in body or "<!-- prove-it:end -->" not in body:
        raise RuntimeError("The published comment is missing its Prove It run marker")

    # The PR may advance while media uploads. Edit this exact comment only to
    # refresh relationship text; keep GitHub's rewritten attachment URLs intact.
    updated_pr = resolve_pr(repo, str(current_pr["number"]))
    if str(updated_pr.get("headRefOid") or "") != str(relationship.get("head_at_publish") or ""):
        final_relationship = classify_pr_relationship(repo, manifest, updated_pr)
        manifest["relationship"] = final_relationship
        save_manifest(run_dir, manifest)
        body = replace_relationship_block(body, manifest)
        comment = update_comment_body(repo, repo_name, comment_id, body, run_dir, args.timeout)
        body = str(comment.get("body") or "")
        unresolved = unresolved_attachment_refs(body, attachments)
        if unresolved:
            raise RuntimeError("Refreshing the SHA relationship restored local attachment references: " + ", ".join(unresolved))

    relationship = manifest.get("relationship", relationship)
    comment_url = str(comment.get("html_url") or "")
    if not comment_url and output.strip():
        comment_url = output.strip().splitlines()[-1]
    result = {
        "pr": updated_pr.get("number"),
        "pr_url": updated_pr.get("url"),
        "comment_url": comment_url,
        "status": validation.get("status"),
        "attachments": len(attachments),
        "captured_sha": manifest_capture_sha(manifest),
        "head_at_publish": relationship.get("head_at_publish"),
        "relationship": relationship.get("kind"),
        "cleaned_up": not args.keep,
    }
    if args.keep:
        result["proof_dir"] = str(run_dir)
        print(json.dumps(result, indent=2))
    else:
        safe_cleanup_run(run_dir)
        print(json.dumps(result, indent=2))
        if comment_url:
            print(comment_url)
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    safe_cleanup_run(run_dir)
    print(f"Deleted {run_dir}")
    return 0

def version_output(command: str, args: list[str], timeout: float = 5) -> dict[str, Any]:
    path = shutil.which(command)
    if not path:
        return {"available": False}
    try:
        cp = run_capture([path, *args], timeout=timeout)
        output = (cp.stdout or cp.stderr).strip().splitlines()
        return {"available": True, "path": path, "version": output[0] if output else "unknown", "exit_code": cp.returncode}
    except subprocess.TimeoutExpired:
        return {"available": True, "path": path, "version": "timed out"}


def cmd_doctor(args: argparse.Namespace) -> int:
    result: dict[str, Any] = {
        "python": {"available": True, "version": sys.version.split()[0], "path": sys.executable},
        "git": version_output("git", ["--version"]),
        "agent_browser": version_output("agent-browser", ["--version"]),
        "ffprobe": version_output("ffprobe", ["-version"]),
        "gh": version_output("gh", ["--version"]),
    }
    if result["gh"]["available"]:
        try:
            cp = run_capture([result["gh"]["path"], "pr", "comment", "--help"], timeout=8)
            result["gh"]["supports_comment_attach"] = "--attach" in (cp.stdout + cp.stderr)
        except subprocess.TimeoutExpired:
            result["gh"]["supports_comment_attach"] = False
    else:
        result["gh"]["supports_comment_attach"] = False
    print(json.dumps(result, indent=2))
    required_ok = result["git"]["available"] and result["python"]["available"] and result["gh"]["available"]
    return 0 if required_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prove.py", description="Record concise, reviewer-facing implementation proof.")
    parser.add_argument("--version", action="version", version=f"prove-it {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    scan = sub.add_parser("scan", help="Classify the current diff and recommend the cheapest proof mode.")
    scan.add_argument("--repo", default=".")
    scan.add_argument("--base")
    scan.add_argument("--working-tree", action="store_true")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=cmd_scan)

    init = sub.add_parser("init", help="Create a proof run and manifest.")
    init.add_argument("--repo", default=".")
    init.add_argument("--base")
    init.add_argument("--working-tree", action="store_true")
    init.add_argument("--pr", nargs="?", const="current", help="Bind the run to an existing PR number/URL; omit value to use current branch PR.")
    init.add_argument("--out", help="Override ephemeral temp storage; mainly for tests/debugging.")
    init.add_argument("--title")
    init.add_argument("--mode", choices=["fast", "expanded"], default="fast")
    init.set_defaults(func=cmd_init)

    claim = sub.add_parser("claim", help="Add an observable claim to a proof run.")
    claim.add_argument("--dir", required=True)
    claim.add_argument("--id")
    claim.add_argument("--text", required=True)
    claim.add_argument("--expected", required=True)
    claim.add_argument("--method", choices=["test", "http", "command", "browser", "screenshot", "video", "database", "log", "static"], required=True)
    claim.add_argument("--priority", choices=["must", "should"], default="must")
    claim.add_argument("--code", action="append", help="Repo-relative code reference: path, path:line-line, or path#Lline-Lline.")
    claim.add_argument("--force", action="store_true")
    claim.set_defaults(func=cmd_claim)

    review = sub.add_parser("review-step", help="Add one reviewer-oriented reading step and its code references.")
    review.add_argument("--dir", required=True)
    review.add_argument("--text", required=True)
    review.add_argument("--code", action="append")
    review.add_argument("--force", action="store_true")
    review.set_defaults(func=cmd_review_step)

    run = sub.add_parser("run", help="Run a targeted command and capture its evidence.")
    run.add_argument("--dir", required=True)
    run.add_argument("--claim", required=True)
    run.add_argument("--kind", choices=["command", "test", "database", "log"], default="command")
    run.add_argument("--label", required=True)
    run.add_argument("--cwd")
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--expect-exit", type=int, default=0)
    run.add_argument("--expect-output", action="append")
    run.add_argument("--reject-output", action="append")
    run.add_argument("--observed")
    run.add_argument("--proves", action="store_true", help="Mark the claim from this command; use only when the command asserts the exact claim.")
    group = run.add_mutually_exclusive_group()
    group.add_argument("--command", help="Shell command string; use only when shell syntax is required.")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run)

    http = sub.add_parser("http", help="Make a direct HTTP assertion and capture request/response evidence.")
    http.add_argument("--dir", required=True)
    http.add_argument("--claim", required=True)
    http.add_argument("--label", required=True)
    http.add_argument("--url", required=True)
    http.add_argument("--method", default="GET")
    http.add_argument("--header", action="append")
    http.add_argument("--header-env", action="append", help="Read a sensitive header from an environment variable: HEADER=ENV_VAR")
    data = http.add_mutually_exclusive_group()
    data.add_argument("--data")
    data.add_argument("--data-file")
    http.add_argument("--expect-status", type=int, action="append", default=[])
    http.add_argument("--expect-body", action="append")
    http.add_argument("--expect-json", action="append", help="Assert a dotted JSON path: key.path=value")
    http.add_argument("--timeout", type=float, default=15)
    http.add_argument("--max-bytes", type=int, default=200_000)
    http.add_argument("--allow-remote", action="store_true")
    http.add_argument("--observed")
    http.add_argument("--proves", action="store_true")
    http.set_defaults(func=cmd_http)

    add = sub.add_parser("add", help="Import a screenshot, video, trace, HAR, or text artifact.")
    add.add_argument("--dir", required=True)
    add.add_argument("--claim", required=True)
    add.add_argument("--type", required=True, choices=sorted(ALL_EVIDENCE_TYPES))
    add.add_argument("--path", required=True)
    add.add_argument("--label", required=True)
    add.add_argument("--observed")
    add.add_argument(
        "--role",
        choices=["primary", "before", "after", "final", "detail"],
        help="Presentation role for screenshots, videos, and diagrams.",
    )
    add.add_argument("--proves", action="store_true")
    add.add_argument("--failed", action="store_true")
    add.add_argument("--no-copy", action="store_true")
    add.set_defaults(func=cmd_add)

    status = sub.add_parser("status", help="Set a claim's final status and observation.")
    status.add_argument("--dir", required=True)
    status.add_argument("--claim", required=True)
    status.add_argument("--status", choices=["passed", "failed", "not_proven", "skipped"], required=True)
    status.add_argument("--observed")
    status.set_defaults(func=cmd_status)

    note = sub.add_parser("note", help="Add a redacted run note.")
    note.add_argument("--dir", required=True)
    note.add_argument("--text", required=True)
    note.set_defaults(func=cmd_note)

    visualize = sub.add_parser("visualize", help="Generate an evidence-backed backend behavior diagram.")
    visualize.add_argument("--dir", required=True)
    visualize.set_defaults(func=cmd_visualize)

    validate = sub.add_parser("validate", help="Check integrity, budgets, secrets, and claim status.")
    validate.add_argument("--dir", required=True)
    validate.add_argument("--strict", action="store_true")
    validate.set_defaults(func=cmd_validate)

    render = sub.add_parser("render", help="Create proof.md and attachment metadata.")
    render.add_argument("--dir", required=True)
    render.set_defaults(func=cmd_render)


    publish = sub.add_parser("publish", help="Post one self-contained proof comment with gh, then delete temp artifacts by default.")
    publish.add_argument("--dir", required=True)
    publish.add_argument("--pr", help="Optional PR number/URL; must match the PR bound at init.")
    publish.add_argument("--timeout", type=float, default=180)
    publish.add_argument("--keep", action="store_true", help="Keep the temporary proof directory after successful upload for debugging.")
    publish.set_defaults(func=cmd_publish)

    cleanup = sub.add_parser("cleanup", help="Delete a Prove It run directory safely.")
    cleanup.add_argument("--dir", required=True)
    cleanup.set_defaults(func=cmd_cleanup)

    doctor = sub.add_parser("doctor", help="Check local proof dependencies and gh attachment support.")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "subcommand", None) == "http" and not args.expect_status:
        args.expect_status = [200]
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        eprint(f"prove-it: {exc}")
        return 2
    except KeyboardInterrupt:
        eprint("prove-it: interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
