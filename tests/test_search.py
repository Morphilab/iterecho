from __future__ import annotations

from pathlib import Path

import pytest

from iterecho.config import AppConfig
from iterecho.search import FileSearcher


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.base_dir = tmp_path
    cfg.extensions = [".txt", ".md"]
    cfg.recursive = True
    return cfg


def create_files(base: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        full = base / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)


class TestFileSearcher:
    def test_finds_matching_files(self, tmp_path: Path):
        create_files(tmp_path, {"a.txt": "hello", "b.md": "world"})
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 1
        assert files[0].name == "a.txt"

    def test_finds_multiple_extensions(self, tmp_path: Path):
        create_files(tmp_path, {"a.txt": "hello", "b.md": "world", "c.py": "code"})
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt", ".md"]
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 2
        extensions = {f.extension for f in files}
        assert extensions == {".txt", ".md"}

    def test_non_recursive(self, tmp_path: Path):
        create_files(tmp_path, {"a.txt": "root", "sub/b.txt": "nested"})
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        cfg.recursive = False
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 1
        assert files[0].name == "a.txt"

    def test_name_filter(self, tmp_path: Path):
        create_files(tmp_path, {"abc.txt": "hello", "def.txt": "world"})
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        cfg.name_filter = "abc"
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 1
        assert files[0].name == "abc.txt"

    def test_case_insensitive_extension(self, tmp_path: Path):
        create_files(tmp_path, {"hello.TXT": "content"})
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 1

    def test_empty_directory(self, tmp_path: Path):
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 0

    def test_file_entry_attributes(self, tmp_path: Path):
        (tmp_path / "test.txt").write_text("hello world")
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 1
        f = files[0]
        assert f.name == "test.txt"
        assert f.extension == ".txt"
        assert f.relative_path == "test.txt"
        assert f.size == 11
        assert f.abs_path == tmp_path / "test.txt"

    def test_ignores_critical_extensions(self, tmp_path: Path):
        (tmp_path / "bad.exe").write_text("evil")
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".exe", ".txt"]
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        # .exe is filtered out by config, so no files match
        assert len(files) == 0

    def test_large_file_filtered(self, tmp_path: Path):
        (tmp_path / "big.txt").write_bytes(b"x" * 200)
        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        cfg.max_file_size = "100"
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        assert len(files) == 0

    def test_directory_symlink_not_followed(self, tmp_path: Path):
        outside = tmp_path.parent / "outside_secret.txt"
        outside.write_text("should not be found")
        outside_dir = tmp_path.parent / "outside_dir"
        outside_dir.mkdir(exist_ok=True)
        (outside_dir / "leak.txt").write_text("leaked")

        sym_dir = tmp_path / "link_to_outside"
        sym_dir.symlink_to(outside_dir, target_is_directory=True)

        cfg = AppConfig()
        cfg.base_dir = tmp_path
        cfg.extensions = [".txt"]
        cfg.follow_symlinks = True
        searcher = FileSearcher(cfg)
        files = searcher.find_files()
        names = [f.name for f in files]
        assert "leak.txt" not in names
