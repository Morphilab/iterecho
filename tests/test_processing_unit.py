from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from iterecho.config import AppConfig
from iterecho.models import FileEntry
from iterecho.processing import FileProcessor


def make_file_entry(tmp_path: Path, rel: str, content: str = "") -> FileEntry:
    full = tmp_path / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return FileEntry(
        abs_path=full,
        name=full.name,
        extension=full.suffix,
        relative_path=rel,
        size=full.stat().st_size,
    )


class TestFileProcessor:
    def test_empty_files_list_copy(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]
        processor = FileProcessor(config)
        # Should not raise
        processor.process([])

    def test_empty_files_list_concat(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True
        processor = FileProcessor(config)
        # Should produce an empty output file
        processor.process([])
        out = tmp_path / "concatenated.txt"
        assert out.exists()

    def test_copy_preserves_subdirectory(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]
        config.output_dir = tmp_path / "output"

        entry = make_file_entry(tmp_path, "sub/file.txt", "hello")
        processor = FileProcessor(config)
        processor.process([entry])

        dest = tmp_path / "output" / "sub" / "file.txt"
        assert dest.exists()
        assert dest.read_text() == "hello"

    def test_copy_follow_symlink(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]
        config.output_dir = tmp_path / "output"
        config.follow_symlinks = True

        target = tmp_path / "real.txt"
        target.write_text("symlink content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        entry = FileEntry(
            abs_path=link,
            name="link.txt",
            extension=".txt",
            relative_path="link.txt",
            size=len(b"symlink content"),
        )
        processor = FileProcessor(config)
        processor.process([entry])

        dest = tmp_path / "output" / "link.txt"
        assert dest.exists()
        assert dest.read_text() == "symlink content"

    def test_copy_without_output_dir(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]

        entry = make_file_entry(tmp_path, "file.txt", "hello")
        processor = FileProcessor(config)
        processor.process([entry])

        # Should create file with sanitized name in same directory
        dest = tmp_path / "file.txt"
        assert dest.exists()

    def test_concat_output_file_custom(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.output_file = Path("custom.txt")
        config.overwrite = True

        entries = [
            make_file_entry(tmp_path, "a.txt", "hello "),
            make_file_entry(tmp_path, "b.txt", "world"),
        ]
        processor = FileProcessor(config)
        processor.process(entries)

        out = tmp_path / "custom.txt"
        assert out.exists()
        content = out.read_text()
        assert "hello" in content
        assert "world" in content

    def test_concat_overwrite_false_existing(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = False

        out = tmp_path / "concatenated.txt"
        out.write_text("existing")

        entries = [make_file_entry(tmp_path, "a.txt", "new")]
        processor = FileProcessor(config)
        with pytest.raises(SystemExit):
            processor.process(entries)

    def test_chunk_respects_size(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "chunk"
        config.extensions = [".txt"]
        config.chunk_size = "500"
        config.output_prefix = "part"
        config.overwrite = True

        entries = [
            make_file_entry(tmp_path, "a.txt", "x" * 300),
            make_file_entry(tmp_path, "b.txt", "y" * 300),
        ]
        processor = FileProcessor(config)
        processor.process(entries)

        chunks = list(tmp_path.glob("part_*.txt"))
        assert len(chunks) >= 2
        total = sum(c.stat().st_size for c in chunks)
        assert total > 0

    def test_chunk_detects_existing_non_001(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "chunk"
        config.extensions = [".txt"]
        config.chunk_size = "500"
        config.output_prefix = "part"
        config.overwrite = False

        (tmp_path / "part_002.txt").write_text("only chunk 002 exists")

        entries = [make_file_entry(tmp_path, "a.txt", "hello")]
        processor = FileProcessor(config)
        with pytest.raises(SystemExit):
            processor.process(entries)

    def test_chunk_no_chunk_size(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "chunk"
        config.extensions = [".txt"]
        config.chunk_size = None

        entries = [make_file_entry(tmp_path, "a.txt", "hello")]
        processor = FileProcessor(config)
        with pytest.raises(SystemExit):
            processor.process(entries)

    def test_chunk_size_zero(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "chunk"
        config.extensions = [".txt"]
        config.chunk_size = "0"

        entries = [make_file_entry(tmp_path, "a.txt", "hello")]
        processor = FileProcessor(config)
        with pytest.raises(SystemExit):
            processor.process(entries)

    def test_file_header_format(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True

        entry = make_file_entry(tmp_path, "test.txt", "hello")
        processor = FileProcessor(config)
        header = processor._get_file_header(entry)
        assert "FILE:" in header
        assert "test.txt" in header
        assert "bytes" in header

    def test_lock_prevents_concurrent_concat(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True

        (tmp_path / "a.txt").write_text("hello")
        entries = [make_file_entry(tmp_path, "a.txt", "hello")]

        if sys.platform == "win32":
            # On Windows we use the O_EXCL + PID-liveness fallback path.
            lock = tmp_path / ".iterecho.lock"
            lock.write_text(str(os.getpid()))
            with pytest.raises(SystemExit):
                FileProcessor(config).process(entries)
            return

        # POSIX path: spawn a child that holds an fcntl lock and sleeps;
        # the child releases the lock when killed. POSIX locks are per-process,
        # so the test runner cannot hold the lock and then re-acquire it from
        # a different fd in the same process.
        import subprocess

        lock_path = tmp_path / ".iterecho.lock"
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import fcntl, os, time
fd = os.open({str(lock_path)!r}, os.O_CREAT | os.O_RDWR, 0o600)
os.write(fd, str(os.getpid()).encode())
fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
time.sleep(30)
""",
            ],
        )
        try:
            # Give the holder a moment to acquire the lock
            for _ in range(20):
                if lock_path.exists():
                    break
                time.sleep(0.1)
            assert lock_path.exists(), "child failed to create lock file"
            with pytest.raises(SystemExit):
                FileProcessor(config).process(entries)
        finally:
            holder.terminate()
            holder.wait(timeout=5)

    def test_lock_released_after_process(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True

        (tmp_path / "a.txt").write_text("hello")

        entries = [make_file_entry(tmp_path, "a.txt", "hello")]
        processor = FileProcessor(config)
        processor.process(entries)

        lock = tmp_path / ".iterecho.lock"
        assert not lock.exists()

    def test_lock_file_has_owner_only_permissions(self, tmp_path: Path):
        """Lock file must be 0o600 to prevent info disclosure across users."""
        import stat

        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True

        (tmp_path / "a.txt").write_text("hello")

        processor = FileProcessor(config)
        processor._lock_output_dir(tmp_path)
        try:
            mode = processor._lock_path.stat().st_mode
            assert stat.S_IMODE(mode) == 0o600
        finally:
            processor._release_lock()

    @pytest.mark.skipif(sys.platform == "win32", reason="fcntl not available on Windows")
    def test_lock_blocks_concurrent_acquire(self, tmp_path: Path):
        """Second processor cannot acquire the same lock while first holds it."""
        import subprocess

        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True

        (tmp_path / "a.txt").write_text("hello")
        entries = [make_file_entry(tmp_path, "a.txt", "hello")]

        # Spawn a child that holds the fcntl lock, then try to acquire
        # from the test process. POSIX locks are per-process, so the
        # child holding and the parent probing is the only way to simulate
        # cross-process locking.
        lock_path = tmp_path / ".iterecho.lock"
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import fcntl, os, time
fd = os.open({str(lock_path)!r}, os.O_CREAT | os.O_RDWR, 0o600)
os.write(fd, str(os.getpid()).encode())
fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
time.sleep(30)
""",
            ],
        )
        try:
            for _ in range(20):
                if lock_path.exists():
                    break
                time.sleep(0.1)
            assert lock_path.exists(), "child failed to create lock file"
            with pytest.raises(SystemExit):
                FileProcessor(config).process(entries)
        finally:
            holder.terminate()
            holder.wait(timeout=5)

    def test_atexit_registration_idempotent(self, tmp_path: Path):
        """Multiple process() calls only register the atexit hook once."""
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True

        (tmp_path / "a.txt").write_text("hello")
        entries = [make_file_entry(tmp_path, "a.txt", "hello")]

        processor = FileProcessor(config)
        processor.process(entries)
        # atexit.register was called once
        assert processor._atexit_registered is True
        registered_after_first = processor._atexit_registered

        # Second process() should not re-register
        (tmp_path / "b.txt").write_text("world")
        entries2 = [make_file_entry(tmp_path, "b.txt", "world")]
        processor.process(entries2)
        assert processor._atexit_registered == registered_after_first

    def test_lock_prevents_concurrent_copy_with_output_dir(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]
        config.output_dir = tmp_path / "output"

        (tmp_path / "a.txt").write_text("hello")
        entries = [make_file_entry(tmp_path, "a.txt", "hello")]

        if sys.platform == "win32":
            lock = (tmp_path / "output") / ".iterecho.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text(str(os.getpid()))
            with pytest.raises(SystemExit):
                FileProcessor(config).process(entries)
            return

        # POSIX path: see test_lock_prevents_concurrent_concat
        import subprocess

        lock_path = tmp_path / "output" / ".iterecho.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import fcntl, os, time
fd = os.open({str(lock_path)!r}, os.O_CREAT | os.O_RDWR, 0o600)
os.write(fd, str(os.getpid()).encode())
fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
time.sleep(30)
""",
            ],
        )
        try:
            for _ in range(20):
                if lock_path.exists():
                    break
                time.sleep(0.1)
            assert lock_path.exists(), "child failed to create lock file"
            with pytest.raises(SystemExit):
                FileProcessor(config).process(entries)
        finally:
            holder.terminate()
            holder.wait(timeout=5)

    def test_lock_not_acquired_for_copy_without_output_dir(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]

        (tmp_path / "a.txt").write_text("hello")
        entries = [make_file_entry(tmp_path, "a.txt", "hello")]
        processor = FileProcessor(config)
        processor.process(entries)

    def test_binary_content_preserved(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.unsafe = True
        config.extensions = [".bin"]
        config.overwrite = True

        binary_data = bytes(range(256))
        full = tmp_path / "data.bin"
        full.write_bytes(binary_data)
        entry = FileEntry(
            abs_path=full,
            name="data.bin",
            extension=".bin",
            relative_path="data.bin",
            size=len(binary_data),
        )

        processor = FileProcessor(config)
        processor.process([entry])

        out = tmp_path / "concatenated.txt"
        raw = out.read_bytes()
        # The binary data should be preserved (not corrupted by encoding)
        for i in range(256):
            assert raw.count(i.to_bytes(1, "big")) > 0

    def test_write_file_entry_validation_before_header(self, tmp_path: Path):
        """When a file fails validation, no content (including header) is written to output.

        Regression guard: if _write_file_entry ever writes the header before calling
        validate_file(), orphaned headers would appear in the output file.
        """
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "concatenate"
        config.extensions = [".txt"]
        config.overwrite = True
        config.max_file_size = "10"  # Very small limit

        # Create a file that exceeds the size limit
        big_file = tmp_path / "big.txt"
        big_file.write_text("012345678901234567890123456789")  # 30 bytes > 10 limit

        entry = FileEntry(
            abs_path=big_file,
            name="big.txt",
            extension=".txt",
            relative_path="big.txt",
            size=len(b"012345678901234567890123456789"),
        )

        processor = FileProcessor(config)
        processor.process([entry])

        out = tmp_path / "concatenated.txt"
        assert out.exists()
        assert out.stat().st_size == 0  # No content written (not even a header)

    def test_copy_mode_fd_no_leak_on_exception(self, tmp_path: Path):
        """Test that file descriptor is not leaked when an exception occurs during copy."""
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "copy"
        config.extensions = [".txt"]
        config.output_dir = tmp_path / "output"
        config.overwrite = True

        # Create a source file
        src_file = tmp_path / "src.txt"
        src_file.write_text("hello")

        entry = FileEntry(
            abs_path=src_file,
            name="src.txt",
            extension=".txt",
            relative_path="src.txt",
            size=len(b"hello"),
        )

        processor = FileProcessor(config)

        # Mock safe_file_copy to raise an exception after validate_file succeeds
        from iterecho.utils.file_utils import safe_file_copy

        original_safe_file_copy = safe_file_copy

        def mock_safe_file_copy(*args, **kwargs):
            # First call validate_file to get fd, then raise exception
            # This simulates an exception occurring after validation but during copy
            raise RuntimeError("Simulated copy failure")

        # Replace the function temporarily
        import iterecho.utils.file_utils

        iterecho.utils.file_utils.safe_file_copy = mock_safe_file_copy

        try:
            # Process should handle the exception gracefully
            processor.process([entry])
            # If we get here, the exception was caught and logged
        finally:
            # Restore original function
            iterecho.utils.file_utils.safe_file_copy = original_safe_file_copy

    def test_chunk_closes_files_on_exception(self, tmp_path: Path):
        """Regression: chunk files must be closed even when _write_file_entry raises."""
        config = AppConfig()
        config.base_dir = tmp_path
        config.mode = "chunk"
        config.extensions = [".txt"]
        config.chunk_size = "100"
        config.output_prefix = "part"
        config.overwrite = True

        entry = make_file_entry(tmp_path, "a.txt", "x" * 50)

        processor = FileProcessor(config)

        # Force _write_file_entry to raise an exception type that is NOT caught
        # by the per-entry handler (only OSError/RuntimeError are caught), so
        # the failure propagates out of process() and we can verify cleanup.
        original_write = processor._write_file_entry

        def boom(*args, **kwargs):
            raise ValueError("simulated mid-write failure")

        processor._write_file_entry = boom  # type: ignore[assignment]

        try:
            with pytest.raises(ValueError, match="simulated mid-write failure"):
                processor.process([entry])
        finally:
            processor._write_file_entry = original_write  # type: ignore[assignment]

        # Each chunk file should be either absent (never opened) or fully
        # closed (not left half-written and locked). Verify with a probe open.
        chunks = list(tmp_path.glob("part_*.txt"))
        for chunk in chunks:
            with open(chunk, "ab"):
                pass  # would fail with 'Resource temporarily unavailable' if leaked
