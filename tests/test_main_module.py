from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_python_m_iterecho_reports_version() -> None:
    """`python -m iterecho` is the fallback entry point documented in README."""
    result = subprocess.run(
        [sys.executable, "-m", "iterecho", "--version"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "IterEcho v" in result.stdout


def test_runpy_entry_point_reports_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Exercise the same entry point in-process."""
    old_argv = sys.argv
    sys.argv = ["iterecho", "--version"]
    try:
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("iterecho.__main__", run_name="__main__")
    finally:
        sys.argv = old_argv

    assert excinfo.value.code in (None, 0)
    assert "IterEcho v" in capsys.readouterr().out
