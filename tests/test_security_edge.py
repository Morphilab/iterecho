from __future__ import annotations

import os
from pathlib import Path

import pytest

from iterecho.config import sanitize_filename
from iterecho.security import SecurityEngine


@pytest.fixture
def engine(tmp_path: Path) -> SecurityEngine:
    return SecurityEngine(base_dir=tmp_path, max_file_size=100_000_000)


class TestSecurityEngineEdgeCases:
    def _assert_invalid(self, engine: SecurityEngine, path: Path) -> None:
        valid, size, fd = engine.validate_file(path)
        assert valid is False
        assert size == 0
        assert fd is None

    def _assert_valid(
        self, engine: SecurityEngine, path: Path, *, follow_symlinks: bool = False
    ) -> None:
        valid, size, fd = engine.validate_file(path, follow_symlinks=follow_symlinks)
        assert valid is True
        assert size > 0
        if fd is not None:
            os.close(fd)

    def _outside_path(self, tmp_path: Path) -> Path:
        return tmp_path.parent / f"outside_{os.getpid()}.txt"

    def test_outside_base_directory(self, engine: SecurityEngine, tmp_path: Path):
        outside = self._outside_path(tmp_path)
        outside.touch()
        self._assert_invalid(engine, outside)
        outside.unlink()

    def test_symlink_to_outside_blocked(self, engine: SecurityEngine, tmp_path: Path):
        target = self._outside_path(tmp_path)
        try:
            target.write_text("evil")
            link = tmp_path / "evil_link.txt"
            link.symlink_to(target)
            self._assert_invalid(engine, link)
        finally:
            if target.exists():
                target.unlink()

    def test_symlink_to_inside_allowed(self, engine: SecurityEngine, tmp_path: Path):
        target = tmp_path / "real.txt"
        target.write_text("safe")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        self._assert_valid(engine, link, follow_symlinks=True)

    def test_symlink_chain_to_outside(self, engine: SecurityEngine, tmp_path: Path):
        intermediate = tmp_path / "intermediate.txt"
        outside = self._outside_path(tmp_path)
        try:
            outside.write_text("evil")
            intermediate.symlink_to(outside)
            link = tmp_path / "chain.txt"
            link.symlink_to(intermediate)
            self._assert_invalid(engine, link)
        finally:
            if outside.exists():
                outside.unlink()

    def test_broken_symlink(self, engine: SecurityEngine, tmp_path: Path):
        link = tmp_path / "broken.txt"
        link.symlink_to("/nonexistent/target")
        self._assert_invalid(engine, link)

    def test_relative_symlink_to_outside(self, engine: SecurityEngine, tmp_path: Path):
        parent_dir = tmp_path / "subdir"
        parent_dir.mkdir()
        outside = tmp_path.parent / "outside.txt"
        try:
            outside.write_text("outside")
            link = parent_dir / "link.txt"
            link.symlink_to(os.path.join("..", "outside.txt"))
            self._assert_invalid(engine, link)
        finally:
            if outside.exists():
                outside.unlink()

    def test_file_size_limit(self, engine: SecurityEngine, tmp_path: Path):
        # Use a smaller engine limit to avoid creating huge files
        small_engine = SecurityEngine(base_dir=tmp_path, max_file_size=100)
        big = tmp_path / "big.txt"
        big.write_bytes(b"a" * 200)
        self._assert_invalid(small_engine, big)

    def test_file_within_size_limit(self, engine: SecurityEngine, tmp_path: Path):
        small = tmp_path / "small.txt"
        small.write_text("small")
        self._assert_valid(engine, small)

    def test_nonexistent_file(self, engine: SecurityEngine, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist.txt"
        self._assert_invalid(engine, nonexistent)

    def test_directory_not_file(self, engine: SecurityEngine, tmp_path: Path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        self._assert_invalid(engine, subdir)

    def test_is_within_base(self, engine: SecurityEngine, tmp_path: Path):
        assert engine.is_within_base(tmp_path / "file.txt") is True
        assert engine.is_within_base(tmp_path) is True

    def test_is_not_within_base(self, engine: SecurityEngine, tmp_path: Path):
        outside = self._outside_path(tmp_path)
        assert engine.is_within_base(outside) is False

    def test_file_no_read_permission(self, engine: SecurityEngine, tmp_path: Path):
        no_perm = tmp_path / "no_perm.txt"
        no_perm.write_text("secret")
        no_perm.chmod(0o000)
        self._assert_invalid(engine, no_perm)
        no_perm.chmod(0o644)

    def test_file_no_permission_no_fd_leak(self, engine: SecurityEngine, tmp_path: Path):
        no_perm = tmp_path / "no_perm_leak.txt"
        no_perm.write_text("no leak")
        no_perm.chmod(0o000)
        valid, size, fd = engine.validate_file(no_perm)
        assert valid is False
        assert fd is None
        no_perm.chmod(0o644)

    def test_sanitize_filename_windows_reserved(self):
        assert sanitize_filename("CON.txt") == "_CON.txt"
        assert sanitize_filename("NUL.txt") == "_NUL.txt"
        assert sanitize_filename("COM1.txt") == "_COM1.txt"
        assert sanitize_filename("LPT1.txt") == "_LPT1.txt"

    def test_sanitize_filename_special_chars(self):
        result = sanitize_filename('bad<>:"/\\|?*chars.txt')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_sanitize_filename_whitespace(self):
        result = sanitize_filename("file   name.txt")
        assert "  " not in result
        assert "file_name.txt" in result

    def test_sanitize_filename_empty_result(self):
        result = sanitize_filename("...")
        assert result == "unnamed_file"

    def test_sanitize_filename_length_limit(self):
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_sanitize_filename_unicode(self):
        result = sanitize_filename("über cool.txt")
        assert "ü" in result
        assert ".txt" in result

    def test_sanitize_filename_trailing_dots(self):
        result = sanitize_filename("file...")
        assert not result.endswith(".")

    def test_symlink_in_parent_dir_blocked(self, tmp_path: Path):
        """A file inside a directory whose parent is a symlink pointing outside base must be rejected.

        This catches a regression where ``path.resolve()`` resolves through the
        symlink and the resolved path ends up outside the base directory, even
        though the original user-supplied path is inside the base.
        """
        base = tmp_path / "base"
        base.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        secret = outside_dir / "secret.txt"
        secret.write_text("leaked content")

        # symlink inside base that points to outside_dir
        sneaky_link = base / "sneaky"
        sneaky_link.symlink_to(outside_dir)

        # A regular file inside the symlinked dir (looks "inside base" before resolve)
        target_file = (
            sneaky_link / "secret.txt"
        )  # this is /tmp/.../outside/secret.txt after resolve

        local_engine = SecurityEngine(base_dir=base, max_file_size=100_000_000)
        valid, size, fd = local_engine.validate_file(target_file)
        assert valid is False
        assert size == 0
        assert fd is None

    def test_symlink_grandparent_outside_base(self, tmp_path: Path):
        """A file inside base/sub/inner/ is rejected when base/sub itself is a symlink to outside."""
        base = tmp_path / "base"
        base.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "leak.txt").write_text("data")

        # base/link -> outside_dir
        link = base / "link"
        link.symlink_to(outside_dir)

        # /tmp/.../base/link/leak.txt  (path string looks like inside base)
        target = base / "link" / "leak.txt"

        local_engine = SecurityEngine(base_dir=base, max_file_size=100_000_000)
        valid, size, fd = local_engine.validate_file(target)
        assert valid is False
        assert fd is None
