from __future__ import annotations

from pathlib import Path

import pytest

from iterecho.utils.file_utils import safe_file_copy, safe_read_file


class TestSafeFileCopy:
    def test_basic_copy(self, tmp_path: Path):
        src = tmp_path / "src.txt"
        src.write_text("hello world")
        dst = tmp_path / "dst.txt"
        assert safe_file_copy(src, dst) is True
        assert dst.read_text() == "hello world"

    def test_source_not_found(self, tmp_path: Path):
        src = tmp_path / "nonexistent.txt"
        dst = tmp_path / "dst.txt"
        assert safe_file_copy(src, dst) is False
        assert not dst.exists()

    def test_source_is_directory(self, tmp_path: Path):
        src = tmp_path / "adir"
        src.mkdir()
        dst = tmp_path / "dst.txt"
        assert safe_file_copy(src, dst) is False

    def test_destination_directory_created(self, tmp_path: Path):
        src = tmp_path / "src.txt"
        src.write_text("content")
        dst = tmp_path / "nested" / "deep" / "dst.txt"
        assert safe_file_copy(src, dst) is True
        assert dst.read_text() == "content"

    def test_overwrites_existing(self, tmp_path: Path):
        src = tmp_path / "src.txt"
        src.write_text("new content")
        dst = tmp_path / "dst.txt"
        dst.write_text("old content")
        assert safe_file_copy(src, dst) is True
        assert dst.read_text() == "new content"

    def test_binary_content(self, tmp_path: Path):
        src = tmp_path / "src.bin"
        data = bytes(range(256))
        src.write_bytes(data)
        dst = tmp_path / "dst.bin"
        assert safe_file_copy(src, dst) is True
        assert dst.read_bytes() == data

    def test_preserves_tmp_cleanup_on_failure(self, tmp_path: Path):
        src = tmp_path / "src.txt"
        src.write_text("content")
        dst = tmp_path / "nonexistent" / "subdir" / "dst.txt"
        assert safe_file_copy(src, dst) is True
        assert dst.exists()
        tmp_file = dst.with_suffix(dst.suffix + ".tmp")
        assert not tmp_file.exists()

    def test_large_file(self, tmp_path: Path):
        src = tmp_path / "large.bin"
        data = b"x" * (5 * 1024 * 1024)  # 5MB
        src.write_bytes(data)
        dst = tmp_path / "large_copy.bin"
        assert safe_file_copy(src, dst) is True
        assert dst.exists()
        assert dst.stat().st_size == len(data)

    def test_copy_symlink_with_follow(self, tmp_path: Path):
        target = tmp_path / "target.txt"
        target.write_text("symlink follow works")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        dst = tmp_path / "copied.txt"
        assert safe_file_copy(link, dst, follow_symlinks=True) is True
        assert dst.read_text() == "symlink follow works"

    def test_copy_symlink_without_follow_fails(self, tmp_path: Path):
        target = tmp_path / "target.txt"
        target.write_text("should fail")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        dst = tmp_path / "copied.txt"
        assert safe_file_copy(link, dst, follow_symlinks=False) is False

    def test_copy_same_source_destination(self, tmp_path: Path):
        src = tmp_path / "same.txt"
        src.write_text("content")
        assert safe_file_copy(src, src) is False


class TestSafeReadFile:
    def test_reads_content(self, tmp_path: Path):
        src = tmp_path / "test.txt"
        src.write_text("hello world")
        chunks = list(safe_read_file(src))
        assert b"".join(chunks) == b"hello world"

    def test_binary_content(self, tmp_path: Path):
        src = tmp_path / "test.bin"
        data = bytes(range(256))
        src.write_bytes(data)
        chunks = list(safe_read_file(src))
        assert b"".join(chunks) == data

    def test_chunk_boundary(self, tmp_path: Path):
        src = tmp_path / "test.txt"
        src.write_bytes(b"x" * 100)
        chunks = list(safe_read_file(src, chunk_size=30))
        assert len(chunks) >= 4
        assert b"".join(chunks) == b"x" * 100

    def test_empty_file(self, tmp_path: Path):
        src = tmp_path / "empty.txt"
        src.write_text("")
        chunks = list(safe_read_file(src))
        assert chunks == []

    def test_nonexistent_file(self, tmp_path: Path):
        src = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            list(safe_read_file(src))

    def test_directory_raises(self, tmp_path: Path):
        src = tmp_path / "adir"
        src.mkdir()
        with pytest.raises(RuntimeError, match="Not a regular file"):
            list(safe_read_file(src))

    def test_large_file(self, tmp_path: Path):
        src = tmp_path / "large.bin"
        data = b"x" * (5 * 1024 * 1024)
        src.write_bytes(data)
        chunks = list(safe_read_file(src))
        assert b"".join(chunks) == data

    def test_read_symlink_with_follow(self, tmp_path: Path):
        target = tmp_path / "target.txt"
        target.write_text("symlink read ok")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        chunks = list(safe_read_file(link, follow_symlinks=True))
        assert b"".join(chunks) == b"symlink read ok"

    def test_read_symlink_without_follow_fails(self, tmp_path: Path):
        target = tmp_path / "target.txt"
        target.write_text("should fail")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        with pytest.raises((RuntimeError, OSError)):
            list(safe_read_file(link, follow_symlinks=False))

    def test_read_symlink_chain_with_follow(self, tmp_path: Path):
        real_file = tmp_path / "real.txt"
        real_file.write_text("chain works")
        link_a = tmp_path / "link_a.txt"
        link_a.symlink_to(real_file)
        link_b = tmp_path / "link_b.txt"
        link_b.symlink_to(link_a)
        chunks = list(safe_read_file(link_b, follow_symlinks=True))
        assert b"".join(chunks) == b"chain works"
