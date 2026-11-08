from __future__ import annotations

from pathlib import Path

import pytest
from tqdm import tqdm

from iterecho.config import AppConfig
from iterecho.models import FileEntry
from iterecho.processing import FileProcessor


def make_file_entry(base: Path, rel: str, content: str = "x") -> FileEntry:
    full = base / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return FileEntry(
        abs_path=full,
        name=full.name,
        extension=full.suffix,
        relative_path=rel,
        size=full.stat().st_size,
    )


def make_config(tmp_path: Path, mode: str) -> AppConfig:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    config = AppConfig()
    config.base_dir = src
    config.output_dir = tmp_path / "out"
    config.mode = mode
    if mode == "chunk":
        config.output_prefix = "chunk"  # the CLI default, which we bypass here
    return config


class TestModeSelection:
    def test_unknown_mode_is_rejected(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, "concatenate")
        config.output.mode = "nonsense"  # bypass the validating property setter
        processor = FileProcessor(config)

        with pytest.raises(ValueError, match="Unknown mode"):
            processor.process([])


class TestCopyErrorPaths:
    def test_entry_outside_base_is_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = make_config(tmp_path, "copy")
        outsider = tmp_path / "outside.txt"
        outsider.write_text("data")
        entry = FileEntry(
            abs_path=outsider,
            name=outsider.name,
            extension=".txt",
            relative_path=outsider.name,
            size=outsider.stat().st_size,
        )

        FileProcessor(config).process([entry])

        assert "Security validation failed" in caplog.text
        assert not (tmp_path / "out" / "outside.txt").exists()

    def test_failed_copy_is_logged_and_run_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = make_config(tmp_path, "copy")
        entry = make_file_entry(config.base_dir, "a.txt")
        monkeypatch.setattr("iterecho.processing.safe_file_copy", lambda *args, **kwargs: False)

        FileProcessor(config).process([entry])  # must not raise

        assert "Copy failed" in caplog.text


class TestChunkErrorPaths:
    def test_chunk_with_no_files_still_creates_output_dir(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, "chunk")
        config.chunk_size = "10M"
        out_dir = config.output_dir
        assert out_dir is not None

        FileProcessor(config).process([])

        assert out_dir.is_dir()
        assert list(out_dir.iterdir()) == []

    def test_write_chunks_requires_chunk_size(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, "chunk")
        config.chunk_size = None
        entry = make_file_entry(config.base_dir, "a.txt")
        out_dir = tmp_path / "chunks"
        out_dir.mkdir()

        with pytest.raises(RuntimeError, match="chunk_size is required"):
            FileProcessor(config)._write_chunks([entry], out_dir)

    def test_small_files_share_one_chunk(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = make_config(tmp_path, "chunk")
        config.chunk_size = "10M"
        entries = [
            make_file_entry(config.base_dir, "a.txt", "first"),
            make_file_entry(config.base_dir, "b.txt", "second"),
        ]

        FileProcessor(config).process(entries)

        chunks = sorted((tmp_path / "out").glob("chunk_*.txt"))
        assert [c.name for c in chunks] == ["chunk_001.txt"]
        body = chunks[0].read_text()
        assert "first" in body
        assert "second" in body
        assert "Failed to process" not in caplog.text

    def test_first_entry_failure_in_new_chunk_is_logged(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        config = make_config(tmp_path, "chunk")
        config.chunk_size = "10M"
        entries = [make_file_entry(config.base_dir, "a.txt", "first")]

        def boom(self, entry, out, pbar, pre_encoded_header=None):  # type: ignore[no-untyped-def]
            raise OSError("simulated write failure")

        monkeypatch.setattr(FileProcessor, "_write_file_entry", boom)
        FileProcessor(config).process(entries)  # must not raise

        assert "Failed to process a.txt" in caplog.text

    def test_append_failure_is_logged_without_aborting(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        config = make_config(tmp_path, "chunk")
        config.chunk_size = "10M"
        entries = [
            make_file_entry(config.base_dir, "a.txt", "first"),
            make_file_entry(config.base_dir, "b.txt", "second"),
        ]
        original = FileProcessor._write_file_entry
        calls = {"count": 0}

        def flaky(self, entry, out, pbar, pre_encoded_header=None):  # type: ignore[no-untyped-def]
            calls["count"] += 1
            if calls["count"] > 1:
                raise OSError("simulated write failure")
            return original(self, entry, out, pbar, pre_encoded_header)

        monkeypatch.setattr(FileProcessor, "_write_file_entry", flaky)
        FileProcessor(config).process(entries)  # must not raise

        assert "Failed to process" in caplog.text
        assert (tmp_path / "out" / "chunk_001.txt").exists()

    def test_copy_closes_descriptor_already_closed_upstream(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A descriptor the copy layer fails on must not make cleanup raise."""
        config = make_config(tmp_path, "copy")
        entry = make_file_entry(config.base_dir, "a.txt")
        processor = FileProcessor(config)
        monkeypatch.setattr(
            processor.security,
            "validate_file",
            lambda path, follow_symlinks=False: (True, entry.size, 999999),
        )

        processor.process([entry])  # real safe_file_copy fails on the stale fd

        assert "Copy failed" in caplog.text

    def test_entry_with_unusable_descriptor_still_writes_header(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = make_config(tmp_path, "concatenate")
        entry = make_file_entry(config.base_dir, "a.txt", "body")
        processor = FileProcessor(config)
        monkeypatch.setattr(
            processor.security,
            "validate_file",
            lambda path, follow_symlinks=False: (True, 0, 999999),
        )
        monkeypatch.setattr("iterecho.processing.safe_read_file", lambda *args, **kwargs: iter(()))

        out_path = tmp_path / "out.bin"
        with out_path.open("wb") as out:
            written = processor._write_file_entry(entry, out, tqdm(total=1, disable=True))

        # Header written, body skipped, descriptor failure swallowed.
        assert written > 0
        assert out_path.read_text().startswith("\n" + "=" * 80)
