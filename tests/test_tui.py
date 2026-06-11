from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from iterecho.tui import run_tui


def _answers(*lines: str) -> StringIO:
    return StringIO("\n".join(lines) + "\n")


def test_tui_default_concatenate(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),  # base_dir
        "n",  # unsafe (default=False, explicitly "n")
        ".txt,.log",  # extensions
        "",  # mode (default=concatenate)
        "",  # output_dir (none)
        "",  # output_extension (default=.txt)
        "y",  # recursive (default=True)
        "",  # max_file_size (default=100M)
        "n",  # overwrite (default=False)
        "out",  # output_prefix
        "",  # output_file (none)
        "y",  # start processing
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.base_dir == tmp_path.resolve()
    assert config.mode == "concatenate"
    assert ".txt" in config.extensions
    assert ".log" in config.extensions
    assert config.output_dir is None
    assert config.output_extension == ".txt"
    assert config.recursive is True
    assert config.unsafe is False
    assert config.overwrite is False
    assert config.output_prefix == "out"
    assert config.output_file is None


def test_tui_copy_mode(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "y",  # unsafe
        ".bin",
        "copy",  # mode
        str(tmp_path / "output"),
        ".bin",
        "n",  # recursive
        "10M",
        "y",  # overwrite
        "y",  # follow_symlinks
        "y",  # start
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.mode == "copy"
    assert config.unsafe is True
    assert config.extensions == [".bin"]
    assert config.output_dir == (tmp_path / "output").resolve()
    assert config.recursive is False
    assert config.max_file_size == 10 * 1024 * 1024
    assert config.overwrite is True
    assert config.follow_symlinks is True


def test_tui_chunk_mode(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "n",
        ".txt",
        "chunk",  # mode
        "",  # output_dir
        "",
        "n",  # recursive
        "1M",  # max_file_size
        "y",  # overwrite
        "500K",  # chunk_size
        "part",  # chunk prefix
        "n",  # follow_symlinks
        "y",  # start
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.mode == "chunk"
    assert config.chunk_size == 500 * 1024
    assert config.output_prefix == "part"
    assert config.follow_symlinks is False


def test_tui_cancels_at_confirm(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "n",
        ".txt",
        "",
        "",
        "",
        "y",
        "",
        "n",
        "out",
        "",
        "n",  # start processing → cancelled
    )
    with patch("sys.stdin", inputs), pytest.raises((typer.Exit, SystemExit)):
        run_tui()


def test_tui_retries_on_invalid_path(tmp_path: Path):
    inputs = _answers(
        "/nonexistent/path",
        str(tmp_path),  # retry with valid path
        "n",
        ".txt",
        "concatenate",
        "",
        "",
        "y",
        "",
        "n",
        "out",
        "",
        "y",
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.base_dir == tmp_path.resolve()


def test_tui_retries_on_invalid_mode(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "n",
        ".txt",
        "invalid_mode",
        "concatenate",  # valid retry
        "",
        "",
        "y",
        "",
        "n",
        "out",
        "",
        "y",
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.mode == "concatenate"


def test_tui_retries_on_bad_size(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "n",
        ".txt",
        "concatenate",
        "",
        "",
        "y",
        "bad_size",
        "50M",  # valid retry
        "n",
        "out",
        "",
        "y",
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.max_file_size == 50 * 1024 * 1024


def test_tui_retries_on_bad_chunk_size(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "n",
        ".txt",
        "chunk",
        "",
        "",
        "y",
        "50M",
        "n",
        "bad_chunk",
        "10M",  # valid retry
        "out",
        "y",
        "y",
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert config.mode == "chunk"
    assert config.chunk_size == 10 * 1024 * 1024


def test_tui_extensions_without_dot(tmp_path: Path):
    inputs = _answers(
        str(tmp_path),
        "n",
        "txt,log",  # no dots → normalized
        "",
        "",
        "",
        "y",
        "",
        "n",
        "out",
        "",
        "y",
    )
    with patch("sys.stdin", inputs):
        config = run_tui()

    assert ".txt" in config.extensions
    assert ".log" in config.extensions
