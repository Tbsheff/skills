#!/usr/bin/env python3
"""Small, dependency-free evidence recorder for the Prove It Claude skill."""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fnmatch
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
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Sequence

TOOL_VERSION = "1.1.0"
SCHEMA_VERSION = 1

DEFAULT_BUDGETS = {
    "max_claims": 3,
    "max_commands": 3,
    "max_screenshots": 2,
    "max_videos": 1,
    "max_video_seconds": 30.0,
}

EXPANDED_BUDGETS = {
    "max_claims": 6,
    "max_commands": 8,
    "max_screenshots": 5,
    "max_videos": 2,
    "max_video_seconds": 90.0,
}

TEXT_EVIDENCE_TYPES = {"command", "test", "http", "database", "log", "console", "errors", "file"}
MEDIA_EVIDENCE_TYPES = {"screenshot", "video"}
ALL_EVIDENCE_TYPES = TEXT_EVIDENCE_TYPES | MEDIA_EVIDENCE_TYPES | {"trace", "har"}

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


def prune_old_temp_runs(max_age_hours: float = 24.0) -> None:
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
    args.extend(["--json", "number,url,title,body,headRefOid,headRefName,baseRefName,isDraft"])
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
    if evidence_type == "screenshot":
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
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": f"E{int(time.time() * 1000)}-{os.getpid()}",
        "type": evidence_type,
        "label": label,
        "status": status,
        "path": relative_artifact_path(run_dir, path),
        "created_at": utc_now(),
        "metadata": evidence_metadata(path, evidence_type),
    }
    if observed:
        item["observed"] = redact(observed)
    if details:
        item["details"] = details
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
            "title": args.title or (str(target_pr.get("title")) if target_pr else "Implementation proof"),
            "created_at": utc_now(),
            "repo_root": str(repo),
            "artifact_dir": str(out),
            "ephemeral": args.out is None,
            "mode": args.mode,
            "config_path": config_path,
        },
        "target_pr": target_pr,
        "change": changes,
        "budgets": resolved_budgets(config, args.mode),
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
    claims.append(
        {
            "id": claim_id,
            "text": args.text,
            "expected": args.expected,
            "method": args.method,
            "priority": args.priority,
            "status": "pending",
            "evidence": [],
            "created_at": utc_now(),
        }
    )
    save_manifest(run_dir, manifest)
    print(claim_id)
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
        f"{args.label} passed in {duration:.2f}s" if passed else f"{args.label} failed with exit {returncode}"
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

    observed = args.observed or (f"{args.method.upper()} returned {status} and matched all assertions" if passed else f"{args.method.upper()} returned {status}; an assertion failed")
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
    imported = import_artifact(run_dir, pathlib.Path(args.path), evidence_type, args.label, copy=not args.no_copy)
    passed = not args.failed
    evidence = make_evidence(
        run_dir=run_dir,
        evidence_type=evidence_type,
        label=args.label,
        path=imported,
        status="passed" if passed else "failed",
        observed=args.observed,
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

    budgets = manifest.get("budgets", DEFAULT_BUDGETS)
    if len(claims) > int(budgets.get("max_claims", DEFAULT_BUDGETS["max_claims"])):
        warnings.append(f"claim budget exceeded: {len(claims)}")
    if command_count > int(budgets.get("max_commands", DEFAULT_BUDGETS["max_commands"])):
        warnings.append(f"command budget exceeded: {command_count}")
    if evidence_counts.get("screenshot", 0) > int(budgets.get("max_screenshots", DEFAULT_BUDGETS["max_screenshots"])):
        warnings.append(f"screenshot budget exceeded: {evidence_counts.get('screenshot', 0)}")
    if evidence_counts.get("video", 0) > int(budgets.get("max_videos", DEFAULT_BUDGETS["max_videos"])):
        warnings.append(f"video budget exceeded: {evidence_counts.get('video', 0)}")
    max_allowed_duration = float(budgets.get("max_video_seconds", DEFAULT_BUDGETS["max_video_seconds"]))
    if max_video_duration > max_allowed_duration:
        warnings.append(f"video exceeds duration budget: {max_video_duration:.1f}s > {max_allowed_duration:.1f}s")

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


def status_icon(status: str) -> str:
    return {"passed": "✅", "failed": "❌", "not_proven": "⚠️", "pending": "⚠️", "skipped": "➖"}.get(status, "⚠️")


def evidence_label(evidence: dict[str, Any]) -> str:
    etype = evidence.get("type", "evidence")
    label = str(evidence.get("label", etype))
    if etype == "screenshot":
        return f"[Screenshot](./{evidence['path']})"
    if etype == "video":
        return f"[Short demo](./{evidence['path']})"
    details = evidence.get("details", {})
    if etype == "http" and details.get("status"):
        return f"{label} (`{details.get('status')}`)"
    return label


def compact_command(command: str, limit: int = 160) -> str:
    command = " ".join(command.split())
    if len(command) <= limit:
        return command
    return command[: limit - 1].rstrip() + "…"


def html_report(run_dir: pathlib.Path, manifest: dict[str, Any], validation: dict[str, Any]) -> str:
    claims_html: list[str] = []
    for claim in manifest.get("claims", []):
        evidence_html: list[str] = []
        for evidence in claim.get("evidence", []):
            path = html.escape(evidence.get("path", ""), quote=True)
            label = html.escape(evidence.get("label", evidence.get("type", "Evidence")))
            observed = html.escape(evidence.get("observed", ""))
            etype = evidence.get("type")
            if etype == "screenshot":
                content = f'<a href="{path}"><img loading="lazy" src="{path}" alt="{label}"></a>'
            elif etype == "video":
                content = f'<video controls preload="metadata" src="{path}"></video>'
            else:
                details = evidence.get("details", {})
                command = html.escape(str(details.get("command", "")))
                content = f"<code>{command}</code>" if command else f'<a href="{path}">Open local evidence</a>'
            evidence_html.append(f'<div class="evidence"><strong>{label}</strong><p>{observed}</p>{content}</div>')
        claims_html.append(
            "".join(
                [
                    f'<section class="claim {html.escape(claim.get("status", "pending"))}">',
                    f'<header><span>{status_icon(claim.get("status", "pending"))}</span><div><h2>{html.escape(claim.get("text", ""))}</h2>',
                    f'<p class="expected">Expected: {html.escape(claim.get("expected", ""))}</p></div></header>',
                    f'<p class="observed">{html.escape(claim.get("observed", "Not yet proven"))}</p>',
                    "".join(evidence_html),
                    "</section>",
                ]
            )
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(manifest['run'].get('title', 'Prove It'))}</title>
<style>
:root {{ color-scheme: light dark; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
body {{ max-width: 1040px; margin: 0 auto; padding: 40px 24px 80px; background: #f5f5f7; color: #1d1d1f; }}
.hero {{ background: white; border-radius: 22px; padding: 28px 32px; box-shadow: 0 8px 30px #0000000d; margin-bottom: 18px; }}
.hero h1 {{ margin: 0 0 8px; font-size: 32px; }} .meta {{ color:#6e6e73; }}
.claim {{ background:white; border-radius:18px; padding:24px; margin:14px 0; border-left:5px solid #86868b; box-shadow:0 5px 20px #0000000a; }}
.claim.passed {{ border-left-color:#34c759; }} .claim.failed {{ border-left-color:#ff3b30; }} .claim.not_proven,.claim.pending {{ border-left-color:#ff9f0a; }}
.claim header {{ display:flex; gap:12px; align-items:flex-start; }} .claim h2 {{ margin:0; font-size:20px; }} .expected,.meta {{ font-size:14px; }}
.observed {{ font-weight:600; }} .evidence {{ margin-top:18px; padding-top:18px; border-top:1px solid #d2d2d7; }}
img,video {{ display:block; width:100%; max-height:620px; object-fit:contain; margin-top:12px; border-radius:12px; background:#000; }}
code {{ display:block; white-space:pre-wrap; overflow:auto; padding:12px; background:#f0f0f2; border-radius:10px; }}
@media (prefers-color-scheme: dark) {{ body {{ background:#111; color:#f5f5f7; }} .hero,.claim {{ background:#1c1c1e; }} .meta,.expected {{ color:#a1a1a6; }} code {{ background:#2c2c2e; }} .evidence {{ border-color:#38383a; }} }}
</style></head><body>
<div class="hero"><h1>{html.escape(manifest['run'].get('title', 'Implementation proof'))}</h1>
<p class="meta">{validation['passed']}/{validation['claims']} claims proven · {html.escape(manifest['run'].get('mode','fast'))} mode · {html.escape(manifest['change'].get('head','')[:8])}</p></div>
{''.join(claims_html) or '<section class="claim"><h2>No runtime proof required</h2></section>'}
</body></html>"""


def cmd_render(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    validation = validate_manifest(run_dir, manifest)
    manifest["summary"] = {k: v for k, v in validation.items() if k not in {"errors", "warnings"}}
    manifest["validation"] = {"at": utc_now(), "errors": validation["errors"], "warnings": validation["warnings"]}
    save_manifest(run_dir, manifest)

    lines: list[str] = ["<!-- prove-it:start -->", "## Prove It", ""]
    if validation["status"] == "passed":
        lines.append(f"**{validation['passed']}/{validation['claims']} claims proven.**")
    elif validation["status"] == "no-proof":
        lines.append("**No runtime proof was required for this change.**")
    else:
        lines.append(f"**{validation['passed']}/{validation['claims']} claims proven; {validation['failed']} failed; {validation['not_proven']} not proven.**")
    if manifest.get("claims"):
        lines.extend(["", "| Claim | Result | Evidence |", "|---|---:|---|"])

    media: list[dict[str, Any]] = []
    for claim in manifest.get("claims", []):
        evidence = claim.get("evidence", [])
        primary = [item for item in evidence if item.get("type") not in {"console", "errors", "log", "file", "trace", "har"}]
        evidence_text = ", ".join(evidence_label(item) for item in primary) or "—"
        claim_text = str(claim.get("text", "")).replace("|", "\\|")
        lines.append(f"| {claim_text} | {status_icon(claim.get('status', 'pending'))} | {evidence_text} |")
        media.extend(item for item in evidence if item.get("type") in MEDIA_EVIDENCE_TYPES)

    for claim in manifest.get("claims", []):
        observed = claim.get("observed")
        non_media = [e for e in claim.get("evidence", []) if e.get("type") not in MEDIA_EVIDENCE_TYPES]
        if not observed and not non_media:
            continue
        lines.extend(["", "<details>", f"<summary>{status_icon(claim.get('status','pending'))} {claim.get('id')}: {claim.get('text')}</summary>", ""])
        if observed:
            lines.append(f"**Observed:** {observed}")
            lines.append("")
        for item in non_media:
            details = item.get("details", {})
            if details.get("command"):
                command = compact_command(str(details["command"]))
                lines.append(f"- {item.get('label')}: `{command}` → exit `{details.get('exit_code')}` in `{details.get('duration_seconds')}s`")
            elif item.get("type") == "http":
                parsed = urllib.parse.urlparse(str(details.get("url", "")))
                target = parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
                lines.append(f"- {item.get('label')}: `{details.get('method', 'HTTP')} {target}` → `{details.get('status')}` in `{details.get('duration_seconds')}s`")
            elif item.get("type") == "console" and item.get("metadata", {}).get("bytes") == 0:
                lines.append("- Browser console: no output")
            elif item.get("type") == "errors" and item.get("metadata", {}).get("bytes") == 0:
                lines.append("- Page errors: none")
            else:
                lines.append(f"- {item.get('label')}: {item.get('observed', item.get('status'))}")
        lines.extend(["", "</details>"])

    screenshots = [item for item in media if item.get("type") == "screenshot"]
    videos = [item for item in media if item.get("type") == "video"]
    if screenshots:
        featured = screenshots[0]
        lines.extend(["", "### Key state", "", f"![{featured.get('label','Screenshot')}](./{featured['path']})"])
    if videos:
        featured = videos[0]
        lines.extend(["", f"[Watch the short interaction demo](./{featured['path']})"])

    if validation["warnings"]:
        lines.extend(["", "<details>", "<summary>Proof warnings</summary>", ""])
        lines.extend(f"- {warning}" for warning in validation["warnings"])
        lines.extend(["", "</details>"])

    lines.extend(["", "<!-- prove-it:end -->"])
    (run_dir / "proof.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (run_dir / "report.html").write_text(html_report(run_dir, manifest, validation), encoding="utf-8")

    attachments = []
    for item in media:
        path = item.get("path")
        if path and path not in attachments:
            attachments.append(path)
    atomic_json(run_dir / "attachments.json", {"files": attachments})
    attach_lines = ["#!/usr/bin/env bash", "# Source from this proof directory so gh can rewrite local media references.", "PROVE_IT_ATTACH=("]
    attach_lines.extend(f"  --attach {shlex.quote(path)}" for path in attachments)
    attach_lines.append(")")
    attachments_script = run_dir / "attachments.sh"
    attachments_script.write_text("\n".join(attach_lines) + "\n", encoding="utf-8")
    attachments_script.chmod(0o755)

    print(str(run_dir / "proof.md"))
    return 1 if validation["errors"] else 0


def cmd_compose(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    base_body = pathlib.Path(args.body).read_text(encoding="utf-8").rstrip()
    proof = (run_dir / "proof.md").read_text(encoding="utf-8").strip()
    out = pathlib.Path(args.out).resolve() if args.out else run_dir / "pr-body.md"

    pattern = re.compile(r"(?ms)^<!-- prove-it:start -->[ \t]*\n.*?^<!-- prove-it:end -->[ \t]*(?:\n|\Z)")
    match = pattern.search(base_body)
    if match:
        before = base_body[: match.start()].rstrip()
        after = base_body[match.end() :].lstrip()
        pieces = [part for part in (before, proof, after) if part]
        composed = "\n\n".join(pieces)
    else:
        composed = base_body + ("\n\n" if base_body else "") + proof
    out.write_text(composed.rstrip() + "\n", encoding="utf-8")
    print(str(out))
    return 0



def gh_supports_pr_attach(repo: pathlib.Path) -> bool:
    gh_path = shutil.which("gh")
    if not gh_path:
        return False
    try:
        cp = run_capture([gh_path, "pr", "edit", "--help"], cwd=repo, timeout=8)
    except subprocess.TimeoutExpired:
        return False
    return cp.returncode == 0 and "--attach" in (cp.stdout + cp.stderr)


def assert_fresh_pr_target(run_dir: pathlib.Path, manifest: dict[str, Any], selector: str | None = None) -> dict[str, Any]:
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
    expected_head = str(target.get("headRefOid") or manifest.get("change", {}).get("head") or "")
    current_head = str(current.get("headRefOid") or "")
    local_head = try_git(repo, "rev-parse", "HEAD") or ""
    if not expected_head or current_head != expected_head or local_head != expected_head:
        raise RuntimeError(
            f"Proof is stale: expected PR head {expected_head[:8] or '(unknown)'}, "
            f"GitHub has {current_head[:8] or '(unknown)'}, local HEAD is {local_head[:8] or '(none)'}. Rerun /prove-it."
        )
    if git(repo, "status", "--porcelain", check=False):
        raise RuntimeError("Working tree changed after proof capture; rerun /prove-it before attaching evidence")
    return current


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


def cmd_publish(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.dir).resolve()
    manifest = load_manifest(run_dir)
    repo = pathlib.Path(manifest["run"]["repo_root"]).resolve()
    current_pr = assert_fresh_pr_target(run_dir, manifest, args.pr)
    validation = validate_manifest(run_dir, manifest)
    if validation["errors"]:
        raise RuntimeError("Proof contains validation errors and cannot be published: " + "; ".join(validation["errors"]))
    if not gh_supports_pr_attach(repo):
        raise RuntimeError("Installed GitHub CLI does not support `gh pr edit --attach`; upgrade gh before publishing proof")

    with contextlib.redirect_stdout(io.StringIO()):
        render_rc = cmd_render(argparse.Namespace(dir=str(run_dir)))
    if render_rc != 0:
        raise RuntimeError("Proof rendering failed validation")

    base_body_path = run_dir / "pr-body-existing.md"
    base_body_path.write_text(str(current_pr.get("body") or ""), encoding="utf-8")
    body_path = run_dir / "pr-body.md"
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_compose(argparse.Namespace(dir=str(run_dir), body=str(base_body_path), out=str(body_path)))

    attachments_data = json.loads((run_dir / "attachments.json").read_text(encoding="utf-8"))
    attachments = [str(item) for item in attachments_data.get("files", [])]
    gh_path = shutil.which("gh")
    assert gh_path is not None
    command = [
        gh_path, "pr", "edit", str(current_pr["number"]),
        "--repo", str(current_pr.get("repo") or manifest.get("target_pr", {}).get("repo")),
        "--body-file", str(body_path),
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
    if cp.returncode != 0:
        raise RuntimeError(f"gh pr edit failed after attempting proof upload: {output}")

    updated = resolve_pr(repo, str(current_pr["number"]))
    body = str(updated.get("body") or "")
    unresolved = [rel for rel in attachments if f"](./{rel})" in body or f"]({rel})" in body]
    if unresolved:
        raise RuntimeError("GitHub CLI returned success but local attachment references remain in PR body: " + ", ".join(unresolved))
    if "<!-- prove-it:start -->" not in body or "<!-- prove-it:end -->" not in body:
        raise RuntimeError("GitHub CLI returned success but the PR body does not contain the Prove It section")

    result = {
        "pr": updated.get("number"),
        "url": updated.get("url"),
        "status": validation.get("status"),
        "attachments": len(attachments),
        "cleaned_up": not args.keep,
    }
    if args.keep:
        result["proof_dir"] = str(run_dir)
        print(json.dumps(result, indent=2))
    else:
        url = str(updated.get("url") or "")
        safe_cleanup_run(run_dir)
        print(json.dumps(result, indent=2))
        if url:
            print(url)
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
            cp = run_capture([result["gh"]["path"], "pr", "edit", "--help"], timeout=8)
            result["gh"]["supports_attach"] = "--attach" in (cp.stdout + cp.stderr)
        except subprocess.TimeoutExpired:
            result["gh"]["supports_attach"] = False
    else:
        result["gh"]["supports_attach"] = False
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
    claim.add_argument("--force", action="store_true")
    claim.set_defaults(func=cmd_claim)

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

    validate = sub.add_parser("validate", help="Check integrity, budgets, secrets, and claim status.")
    validate.add_argument("--dir", required=True)
    validate.add_argument("--strict", action="store_true")
    validate.set_defaults(func=cmd_validate)

    render = sub.add_parser("render", help="Create proof.md, report.html, and attachment metadata.")
    render.add_argument("--dir", required=True)
    render.set_defaults(func=cmd_render)

    compose = sub.add_parser("compose", help="Append proof.md to an existing PR body.")
    compose.add_argument("--dir", required=True)
    compose.add_argument("--body", required=True)
    compose.add_argument("--out")
    compose.set_defaults(func=cmd_compose)

    publish = sub.add_parser("publish", help="Attach rendered proof to the existing PR with gh, then delete temp artifacts by default.")
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
