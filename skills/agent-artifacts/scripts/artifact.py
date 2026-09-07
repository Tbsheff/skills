#!/usr/bin/env python3
"""Run Agent Artifacts from an installed command or a source checkout."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    executable = shutil.which("agent-artifacts") or shutil.which("artifacts")
    if executable and Path(executable).resolve() != Path(sys.argv[0]).resolve():
        return subprocess.call([executable, *sys.argv[1:]])

    here = Path(__file__).resolve()
    for parent in here.parents:
        source = parent / "src"
        package = source / "agent_artifacts"
        if package.is_dir():
            sys.path.insert(0, os.fspath(source))
            from agent_artifacts.cli import main as cli_main
            return cli_main(sys.argv[1:])

    print(
        "Agent Artifacts engine not found. Install the repository with "
        "`python3 -m pip install .` or run this skill from its source checkout.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
