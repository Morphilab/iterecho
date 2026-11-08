"""Fail when `.pre-commit-config.yaml` revs drift from the installed linters.

Why this exists: the `dev` extra is intentionally unpinned — uv resolves one
version per supported Python (3.8..3.14), frozen in `uv.lock` — while
pre-commit runs fixed revisions. The two only agree on the Python used by the
CI lint job, so this check runs there (`uv run --no-sync ...`, which puts the
environment's binaries on PATH) and locally from an activated venv.

Usage:
    python .github/scripts/check_tool_pins.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / ".pre-commit-config.yaml"
SEMVER = re.compile(r"\d+\.\d+\.\d+")

# tool -> (repository fragment identifying its block in the config, CLI args)
TOOLS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ruff": ("ruff-pre-commit", ("--version",)),
    "black": ("psf/black", ("--version",)),
    "isort": ("pycqa/isort", ("--version-number",)),
}


def pinned_rev(repo_fragment: str) -> str:
    """Return the `rev:` of the hook repo whose `repo:` line contains *repo_fragment*."""
    lines = CONFIG.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("- repo:") and repo_fragment in line:
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip()
                if stripped.startswith("rev:"):
                    return stripped.split(":", 1)[1].strip()
                if stripped.startswith("- repo:"):
                    break
    raise SystemExit(f"error: no `rev:` found for repo fragment {repo_fragment!r} in {CONFIG}")


def installed_version(tool: str, args: tuple[str, ...]) -> str:
    """Return the installed version of *tool*, parsed from its own output."""
    executable = shutil.which(tool)
    if executable is None:
        raise SystemExit(f"error: {tool} is not on PATH (activate the dev environment first)")
    result = subprocess.run([executable, *args], capture_output=True, text=True, check=False)
    output = (result.stdout or result.stderr).strip()
    match = SEMVER.search(output)
    if result.returncode != 0 or match is None:
        raise SystemExit(f"error: could not read {tool} version from {output!r}")
    return match.group(0)


def main() -> int:
    failures: list[str] = []
    print(f"{'tool':<8} {'installed':<12} {'pre-commit rev':<14} status")
    for tool, (repo_fragment, args) in TOOLS.items():
        installed = installed_version(tool, args)
        pinned = pinned_rev(repo_fragment)
        pinned_match = SEMVER.search(pinned)
        agrees = pinned_match is not None and pinned_match.group(0) == installed
        if not agrees:
            failures.append(f"{tool}: installed {installed} != pre-commit rev {pinned}")
        print(f"{tool:<8} {installed:<12} {pinned:<14} {'ok' if agrees else 'DRIFT'}")
    if failures:
        print("\npre-commit revisions drifted from the linters CI runs:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "Update `.pre-commit-config.yaml` `rev:` values (and the comments there) to match.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
