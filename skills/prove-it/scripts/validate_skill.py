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
    parser = argparse.ArgumentParser(
        description="Validate the prove-it skill.",
        usage="validate_skill.py [SKILL_DIR] [--self-test]",
    )
    parser.add_argument("skill_dir", nargs="?", help="Skill directory. Default: the directory that holds this script.")
    parser.add_argument("--self-test", action="store_true", help="Also run scripts/self_test.py.")
    args = parser.parse_args()

    root = pathlib.Path(args.skill_dir).expanduser().resolve() if args.skill_dir else pathlib.Path(__file__).resolve().parent.parent
    if root.is_file():
        root = root.parent
    if not (root / "SKILL.md").is_file():
        parser.error(f"no SKILL.md in {root}; pass the skill directory, for example: validate_skill.py ~/.agents/skills/prove-it")
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
    if fields.get("disable-model-invocation") == "true":
        errors.append("prove-it must allow model invocation")
    if fields.get("context") != "fork":
        errors.append("prove-it must run with context: fork")

    openai_config = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "allow_implicit_invocation: true" not in openai_config:
        errors.append("agents/openai.yaml must allow implicit invocation")

    skill_lines = len(text.splitlines())
    skill_words = len(text.split())
    if skill_lines > 120:
        errors.append(f"SKILL.md exceeds the local 120-line context budget: {skill_lines}")
    if skill_words > 700:
        errors.append(f"SKILL.md exceeds the local 700-word context budget: {skill_words}")
    if "—" in text:
        errors.append("SKILL.md contains an em dash; use plain punctuation")
    for phrase in (
        "it is important to note",
        "in order to",
        "serves as",
        "not just",
        "seamlessly",
        "robust",
        "leverage",
    ):
        if phrase in text.casefold():
            errors.append(f"SKILL.md contains filler or AI-style wording: {phrase!r}")

    reference_files = sorted((root / "references").glob("*.md"))
    for reference in reference_files:
        if len(reference.read_text(encoding="utf-8").splitlines()) > 160:
            errors.append(f"reference is too large for on-demand loading: {reference.relative_to(root)}")

    for markdown in [skill, *reference_files, root / "README.md"]:
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

    for tool in ("shared/house.py", "shared/house.css", "ui/build.py", "ui/cursor.js", "backend/capture.py", "backend/render.py"):
        if not (root / "scripts" / "media" / tool).exists():
            errors.append(f"missing media tool: scripts/media/{tool}")

    for script in [root / "scripts" / "prove.py", *sorted((root / "scripts" / "media").rglob("*.py"))]:
        compile_result = subprocess.run(
            [sys.executable, "-S", "-c", "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')", str(script)],
            text=True,
            capture_output=True,
        )
        if compile_result.returncode:
            errors.append(f"{script.relative_to(root)} does not compile: {compile_result.stderr.strip()}")

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
