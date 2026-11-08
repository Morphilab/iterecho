from __future__ import annotations

import os
from pathlib import Path

import pytest

from iterecho.config import AppConfig
from iterecho.search import FileSearcher


def base_config(base: Path) -> AppConfig:
    config = AppConfig()
    config.base_dir = base
    config.extensions = [".txt"]
    return config


def inject_paths(
    searcher: FileSearcher, paths: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the walk handing over paths we choose (deleted files, FIFOs, races)."""
    monkeypatch.setattr(searcher, "_file_generator", lambda: iter(paths))


class TestFileGenerator:
    def test_symlink_is_not_followed_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "real.txt").write_text("data")
        (tmp_path / "link.txt").symlink_to(Path("real.txt"))

        files = FileSearcher(base_config(tmp_path)).find_files()

        assert [f.name for f in files] == ["real.txt"]

    def test_base_that_is_a_file_ends_the_walk(self, tmp_path: Path) -> None:
        plain_file = tmp_path / "not-a-dir.txt"
        plain_file.write_text("x")
        config = base_config(tmp_path)
        config._base_dir = plain_file  # bypass the validating setter on purpose

        assert FileSearcher(config).find_files() == []


class TestFindFilesInjectedPaths:
    def test_entry_deleted_before_lstat_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        searcher = FileSearcher(base_config(tmp_path))
        inject_paths(searcher, [tmp_path / "ghost.txt"], monkeypatch)

        assert searcher.find_files() == []

    def test_symlink_handed_over_without_follow_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "real.txt").write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(Path("real.txt"))
        searcher = FileSearcher(base_config(tmp_path))
        inject_paths(searcher, [link], monkeypatch)

        assert searcher.find_files() == []

    def test_symlink_that_cannot_be_statted_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dangling = tmp_path / "dangling.txt"
        dangling.symlink_to(Path("vanished.txt"))
        config = base_config(tmp_path)
        config.follow_symlinks = True
        searcher = FileSearcher(config)
        inject_paths(searcher, [dangling], monkeypatch)

        assert searcher.find_files() == []

    def test_fifo_is_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fifo = tmp_path / "pipe.txt"
        os.mkfifo(fifo)
        searcher = FileSearcher(base_config(tmp_path))
        inject_paths(searcher, [fifo], monkeypatch)

        assert searcher.find_files() == []

    def test_path_outside_base_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = tmp_path / "sub"
        base.mkdir()
        (base / "inside.txt").write_text("in")
        outside = tmp_path / "other.txt"
        outside.write_text("out")
        searcher = FileSearcher(base_config(base))
        inject_paths(searcher, [outside], monkeypatch)

        assert searcher.find_files() == []
