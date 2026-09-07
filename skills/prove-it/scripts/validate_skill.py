#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    errors: list[str] = []
    skill = root / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        errors.append("SKILL.md is missing YAML frontmatter")
        frontmatter = ""
    else:
        frontmatter = text.split("\n---\n", 1)[0][4:]

    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if re.match(r"^[a-zA-Z][a-zA-Z0-9-]*:", line):
            key, value = line.split(":", 1)
            fields[key] = value.strip().strip('"')
    name = fields.get("name", "")
    description = fields.get("description", "")
    if name != root.name:
        errors.append(f"frontmatter name {name!r} must match directory {root.name!r}")
    if not NAME_RE.fullmatch(name):
        errors.append(f"invalid skill name: {name!r}")
    if not description or len(description) > 1024:
        errors.append(f"description length must be 1..1024, got {len(description)}")
    if len(text.splitlines()) > 500:
        errors.append("SKILL.md exceeds the recommended 500 lines")

    for markdown in [skill, *sorted((root / "references").glob("*.md")), root / "README.md"]:
        body = markdown.read_text(encoding="utf-8")
        for target in LINK_RE.findall(body):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#", 1)[0]
            resolved = (markdown.parent / clean).resolve()
            if not resolved.exists():
                errors.append(f"broken link in {markdown.relative_to(root)}: {target}")

    for config in (root / "assets").glob("*.json"):
        try:
            json.loads(config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON in {config.relative_to(root)}: {exc}")

    for script_name in ("prove-it", "prove.py", "self_test.py"):
        script = root / "scripts" / script_name
        if not script.exists():
            errors.append(f"missing script: scripts/{script_name}")
        elif not (script.stat().st_mode & 0o111):
            errors.append(f"script is not executable: scripts/{script_name}")

    compile_result = subprocess.run(
        [sys.executable, "-S", "-m", "py_compile", str(root / "scripts" / "prove.py")],
        text=True,
        capture_output=True,
    )
    if compile_result.returncode:
        errors.append(f"prove.py does not compile: {compile_result.stderr.strip()}")

    if not errors and args.self_test:
        test = subprocess.run([sys.executable, str(root / "scripts" / "self_test.py")], text=True, capture_output=True)
        if test.returncode:
            errors.append(f"self-test failed:\n{test.stdout}\n{test.stderr}")
        else:
            print(test.stdout.strip())

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("prove-it skill validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
