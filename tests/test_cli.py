from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from iterecho.cli import app

runner = CliRunner()


def test_cli_help_succeeds():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "IterEcho" in result.output


def test_cli_version_no_subcommand():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "1.0.1" in result.output


def test_cli_version_with_subcommand(tmp_path: Path):
    result = runner.invoke(app, ["--version", "copy"])
    assert result.exit_code == 0
    assert "1.0.1" in result.output


def test_cli_copy_dry_run(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello")

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "--dry-run",
            "copy",
        ],
    )
    assert result.exit_code == 0


def test_cli_copy_actual(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello")
    out = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "--output-dir",
            str(out),
            "copy",
        ],
    )
    assert result.exit_code == 0
    assert (out / "a.txt").exists()
    assert (out / "a.txt").read_text() == "hello"


def test_cli_concatenate_dry_run(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "--dry-run",
            "concatenate",
        ],
    )
    assert result.exit_code == 0


def test_cli_concatenate_actual(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello ")
    (tmp_path / "b.txt").write_text("world")

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "concatenate",
            "--output-prefix",
            "combined",
        ],
    )
    assert result.exit_code == 0
    out = tmp_path / "combined.txt"
    assert out.exists()
    content = out.read_text()
    assert "hello" in content
    assert "world" in content


def test_cli_chunk_dry_run(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x" * 300)

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "--dry-run",
            "chunk",
        ],
    )
    assert result.exit_code == 0


def test_cli_chunk_actual(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x" * 300)
    (tmp_path / "b.txt").write_text("y" * 300)

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "chunk",
            "--chunk-size",
            "400",
            "--output-prefix",
            "part",
        ],
    )
    assert result.exit_code == 0
    chunks = list(tmp_path.glob("part_*.txt"))
    assert len(chunks) >= 2


def test_cli_no_files_warns(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "copy",
        ],
    )
    assert result.exit_code == 0


def test_cli_unsafe_extension_allowed(tmp_path: Path):
    (tmp_path / "script.py").write_text("print('hello')")
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--unsafe",
            "--extensions",
            ".py",
            "--output-extension",
            ".py",
            "--output-dir",
            str(out),
            "copy",
        ],
    )
    assert result.exit_code == 0
    assert (out / "script.py").exists()


def test_cli_unsafe_extension_blocked_by_default(tmp_path: Path):
    (tmp_path / "script.py").write_text("print('hello')")

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".py",
            "copy",
        ],
    )
    assert result.exit_code != 0


def test_cli_output_extension_preserved(tmp_path: Path):
    (tmp_path / "data.bin").write_bytes(bytes(range(10)))
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".bin",
            "--output-extension",
            ".bin",
            "--unsafe",
            "--output-dir",
            str(out),
            "copy",
        ],
    )
    assert result.exit_code == 0
    assert (out / "data.bin").exists()


def test_cli_concatenate_custom_output_file(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello")

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "concatenate",
            "--output-file",
            "my_result.txt",
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "my_result.txt").exists()


def test_cli_recursive_flag(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("nested")
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "--base-dir",
            str(tmp_path),
            "--extensions",
            ".txt",
            "--no-recursive",
            "--output-dir",
            str(out),
            "copy",
        ],
    )
    assert result.exit_code == 0
    assert not (out / "sub" / "a.txt").exists()
