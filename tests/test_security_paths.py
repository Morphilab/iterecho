from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from iterecho.security import SecurityEngine


class TestIsWithinBase:
    def test_resolve_failure_is_treated_as_outside(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)

        def boom(_self: Path, strict: bool = False) -> Path:
            raise RuntimeError("simulated resolution failure")

        monkeypatch.setattr(Path, "resolve", boom)
        assert engine.is_within_base(tmp_path / "anything.txt") is False


class TestValidateFileRegularPaths:
    def test_open_error_other_than_eloop_is_rejected(self, tmp_path: Path) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        (tmp_path / "dir").mkdir()
        (tmp_path / "dir" / "f.txt").write_text("x")

        # A path component that is a file yields ENOTDIR, not ELOOP: it must
        # not be mistaken for the symlink branch.
        valid, size, fd = engine.validate_file(tmp_path / "dir" / "f.txt" / "child")
        assert valid is False
        assert size == 0
        assert fd is None

    def test_file_replaced_between_open_and_stat_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        target = tmp_path / "a.txt"
        target.write_text("data")
        real_open = os.open

        def fake_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            if str(path) == str(target):
                raise OSError(errno.ELOOP, "simulated symlink swap")
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "open", fake_open)
        valid, size, fd = engine.validate_file(target, follow_symlinks=True)
        assert valid is False
        assert fd is None


class TestValidateFileSymlinkBranch:
    def test_relative_symlink_inside_base_is_followed(self, tmp_path: Path) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        (tmp_path / "real.txt").write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(Path("real.txt"))

        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is True
        assert size == len("data")
        assert fd is not None
        os.close(fd)

    def test_target_swapped_to_outside_base_is_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        (tmp_path / "real.txt").write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(Path("real.txt"))
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("secret")

        # The base check only sees the link's own path (still inside the base);
        # readlink then reports a target outside it, as it would if the link
        # were swapped between the two checks. The re-validation must block it.
        monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self)
        monkeypatch.setattr(os, "readlink", lambda _path: str(outside))
        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is False
        assert fd is None

    def test_dangling_target_cannot_be_opened(self, tmp_path: Path) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        link = tmp_path / "link.txt"
        link.symlink_to(Path("missing.txt"))

        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is False
        assert fd is None

    def test_symlink_to_directory_is_rejected(self, tmp_path: Path) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        (tmp_path / "subdir").mkdir()
        link = tmp_path / "link.txt"
        link.symlink_to(Path("subdir"))

        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is False
        assert fd is None

    def test_symlink_target_larger_than_limit_is_rejected(self, tmp_path: Path) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=4)
        (tmp_path / "real.txt").write_text("more than four bytes")
        link = tmp_path / "link.txt"
        link.symlink_to(Path("real.txt"))

        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is False
        assert fd is None

    def test_fstat_error_after_opening_target_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        (tmp_path / "real.txt").write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(Path("real.txt"))

        def broken_fstat(_fd: int) -> os.stat_result:
            raise OSError(errno.EIO, "simulated fstat failure")

        monkeypatch.setattr(os, "fstat", broken_fstat)
        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is False
        assert fd is None

    def test_stat_error_in_symlink_branch_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = SecurityEngine(tmp_path, max_file_size=1024)
        (tmp_path / "real.txt").write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(Path("real.txt"))

        def broken_stat(*_args: object, **_kwargs: object) -> os.stat_result:
            raise OSError(errno.EIO, "simulated stat failure")

        monkeypatch.setattr(os, "stat", broken_stat)
        valid, size, fd = engine.validate_file(link, follow_symlinks=True)
        assert valid is False
        assert fd is None
