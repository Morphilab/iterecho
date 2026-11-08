from __future__ import annotations

import errno
import fcntl
import os
import sys
from pathlib import Path

import pytest

from iterecho.config import AppConfig
from iterecho.processing import _LOCK_BASENAME, FileProcessor


def make_config(tmp_path: Path) -> AppConfig:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    config = AppConfig()
    config.base_dir = src
    config.output_dir = tmp_path / "out"
    config.mode = "concatenate"
    return config


def dead_pid() -> int:
    """A PID the kernel will never answer for (valid PIDs stop at pid_max - 1)."""
    try:
        return int(Path("/proc/sys/kernel/pid_max").read_text().strip())
    except OSError:
        return 4194305


class TestProcessLiveness:
    def test_own_pid_is_alive(self) -> None:
        assert FileProcessor._is_process_alive(os.getpid()) is True

    def test_unreachable_pid_is_not_alive(self) -> None:
        assert FileProcessor._is_process_alive(dead_pid()) is False

    def test_permission_denied_pid_is_treated_as_alive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def deny(_pid: int, _signal: int) -> None:
            raise PermissionError

        monkeypatch.setattr(os, "kill", deny)
        assert FileProcessor._is_process_alive(1234) is True


class TestLockFallbackPaths:
    def test_fcntl_import_failure_falls_back_to_excl(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without fcntl the O_CREAT|O_EXCL + PID path has to take over."""
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        monkeypatch.setitem(sys.modules, "fcntl", None)

        processor._lock_output_dir(out_dir)

        lock_file = out_dir / _LOCK_BASENAME
        assert lock_file.read_text().strip() == str(os.getpid())
        processor._release_lock()
        assert not lock_file.exists()

    def test_windows_platform_falls_back_to_excl(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        monkeypatch.setattr(sys, "platform", "win32")

        processor._lock_output_dir(out_dir)

        lock_file = out_dir / _LOCK_BASENAME
        assert lock_file.read_text().strip() == str(os.getpid())
        processor._release_lock()
        assert not lock_file.exists()

    def test_lock_with_live_pid_blocks_the_next_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / _LOCK_BASENAME).write_text(str(os.getpid()))
        monkeypatch.setattr(sys, "platform", "win32")

        with pytest.raises(SystemExit) as excinfo:
            processor._lock_output_dir(out_dir)
        assert excinfo.value.code == 1

    @pytest.mark.skipif(sys.platform == "win32", reason="O_NOFOLLOW is POSIX-only")
    def test_symlinked_lock_file_is_rejected(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("do not touch")
        (out_dir / _LOCK_BASENAME).symlink_to(victim)

        with pytest.raises(SystemExit) as excinfo:
            processor._lock_output_dir(out_dir)

        assert excinfo.value.code == 1
        assert victim.read_text() == "do not touch"

    def test_stale_lock_from_dead_pid_is_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / _LOCK_BASENAME).write_text(str(dead_pid()))
        monkeypatch.setattr(sys, "platform", "win32")

        processor._lock_output_dir(out_dir)

        lock_file = out_dir / _LOCK_BASENAME
        assert lock_file.read_text().strip() == str(os.getpid())
        processor._release_lock()

    def test_unparsable_lock_is_treated_as_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / _LOCK_BASENAME).write_text("not-a-pid")
        monkeypatch.setattr(sys, "platform", "win32")

        processor._lock_output_dir(out_dir)

        lock_file = out_dir / _LOCK_BASENAME
        assert lock_file.read_text().strip() == str(os.getpid())
        processor._release_lock()

    def test_gives_up_after_three_attempts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the stale lock cannot be removed, three attempts are all we get."""
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / _LOCK_BASENAME).write_text(str(dead_pid()))
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(Path, "unlink", lambda self, *args, **kwargs: None)

        with pytest.raises(SystemExit) as excinfo:
            processor._lock_output_dir(out_dir)
        assert excinfo.value.code == 1

    def test_unexpected_lockf_error_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None

        def broken_lockf(*_args: object, **_kwargs: object) -> None:
            raise OSError(22, "simulated lock failure")  # EINVAL, not EAGAIN/EACCES

        monkeypatch.setattr(fcntl, "lockf", broken_lockf)
        with pytest.raises(SystemExit) as excinfo:
            processor._lock_output_dir(out_dir)
        assert excinfo.value.code == 1

    def test_lock_file_open_failure_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        monkeypatch.setattr(sys, "platform", "win32")

        def denied(_path: object, _flags: int, *args: object, **kwargs: object) -> int:
            raise OSError(errno.EACCES, "simulated permission denial")

        monkeypatch.setattr(os, "open", denied)
        with pytest.raises(SystemExit) as excinfo:
            processor._lock_output_dir(out_dir)
        assert excinfo.value.code == 1

    def test_stale_lock_vanishing_before_unlink_is_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The stale lock may disappear between the check and the unlink."""
        config = make_config(tmp_path)
        processor = FileProcessor(config)
        out_dir = config.output_dir
        assert out_dir is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        lock_file = out_dir / _LOCK_BASENAME
        lock_file.write_text(str(dead_pid()))
        monkeypatch.setattr(sys, "platform", "win32")

        def vanishing(self: Path, *args: object, **kwargs: object) -> None:
            os.unlink(self)
            raise FileNotFoundError(self)

        monkeypatch.setattr(Path, "unlink", vanishing)
        processor._lock_output_dir(out_dir)

        assert lock_file.read_text().strip() == str(os.getpid())
        processor._release_lock()


class TestReleaseLockResilience:
    def test_close_failure_is_swallowed(self, tmp_path: Path) -> None:
        processor = FileProcessor(make_config(tmp_path))
        processor._lock_fd = 999999  # EBADF: an already-closed descriptor
        processor._lock_path = tmp_path / "missing.lock"

        processor._release_lock()

        assert processor._lock_fd is None
        assert processor._lock_path is None

    def test_vanished_lock_file_is_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        processor = FileProcessor(make_config(tmp_path))
        lock_file = tmp_path / _LOCK_BASENAME
        lock_file.write_text(str(os.getpid()))
        processor._lock_path = lock_file

        def vanished(self: Path, missing_ok: bool = False) -> None:
            raise FileNotFoundError(self)

        monkeypatch.setattr(Path, "unlink", vanished)
        processor._release_lock()

        assert processor._lock_path is None
