import tempfile
from pathlib import Path

from iterecho.config import AppConfig
from iterecho.processing import FileProcessor
from iterecho.search import FileSearcher


def test_copy_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "file1.txt").write_text("Hello World 1")
        (tmpdir / "file2.txt").write_text("Hello World 2")
        (tmpdir / "subdir").mkdir()
        (tmpdir / "subdir" / "file3.txt").write_text("Hello World 3")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".txt"]
        config.mode = "copy"
        config.output_dir = tmpdir / "output"
        config.recursive = True

        searcher = FileSearcher(config)
        files = searcher.find_files()
        processor = FileProcessor(config)
        processor.process(files)

        assert (config.output_dir / "file1.txt").exists()
        assert (config.output_dir / "file2.txt").exists()
        assert (config.output_dir / "subdir" / "file3.txt").exists()
        assert (config.output_dir / "file1.txt").read_text() == "Hello World 1"


def test_concat_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "file1.txt").write_text("Content 1\n")
        (tmpdir / "file2.txt").write_text("Content 2\n")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".txt"]
        config.mode = "concatenate"
        config.output_prefix = "combined"
        config.recursive = False

        searcher = FileSearcher(config)
        files = searcher.find_files()
        processor = FileProcessor(config)
        processor.process(files)

        output_file = tmpdir / "combined.txt"
        assert output_file.exists()
        content = output_file.read_text()
        assert "Content 1" in content
        assert "Content 2" in content
        assert "FILE: file1.txt" in content


def test_chunk_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        large_content = "X" * 1024 * 1024  # 1MB
        (tmpdir / "large.txt").write_text(large_content)
        (tmpdir / "small.txt").write_text("Small content")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".txt"]
        config.mode = "chunk"
        config.chunk_size = "500K"
        config.recursive = False
        config.output_prefix = "part"

        searcher = FileSearcher(config)
        files = searcher.find_files()
        processor = FileProcessor(config)
        processor.process(files)

        chunk_files = list(tmpdir.glob("part_*.txt"))
        assert len(chunk_files) >= 2

        total_content = ""
        for chunk_file in sorted(chunk_files):
            total_content += chunk_file.read_text()

        assert "large.txt" in total_content
        assert "small.txt" in total_content


def test_copy_mode_follow_symlinks():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "real.txt").write_text("symlink target content")
        link = tmpdir / "link.txt"
        link.symlink_to(tmpdir / "real.txt")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".txt"]
        config.mode = "copy"
        config.output_dir = tmpdir / "output"
        config.follow_symlinks = True

        searcher = FileSearcher(config)
        files = searcher.find_files()
        processor = FileProcessor(config)
        processor.process(files)

        dest = config.output_dir / "link.txt"
        assert dest.exists()
        assert dest.read_text() == "symlink target content"


def test_concat_mode_follow_symlinks():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "real.txt").write_text("Content A\n")
        link = tmpdir / "link.txt"
        link.symlink_to(tmpdir / "real.txt")
        (tmpdir / "extra.txt").write_text("Content B\n")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".txt"]
        config.mode = "concatenate"
        config.follow_symlinks = True
        config.output_prefix = "combined"
        config.recursive = False

        searcher = FileSearcher(config)
        files = searcher.find_files()
        processor = FileProcessor(config)
        processor.process(files)

        output_file = tmpdir / "combined.txt"
        assert output_file.exists()
        content = output_file.read_text()
        assert "Content A" in content
        assert "Content B" in content
        assert "link.txt" in content


def test_chunk_mode_follow_symlinks():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "real.txt").write_text("X" * 600)
        link = tmpdir / "link.txt"
        link.symlink_to(tmpdir / "real.txt")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".txt"]
        config.mode = "chunk"
        config.follow_symlinks = True
        config.chunk_size = "400"
        config.output_prefix = "part"
        config.recursive = False

        searcher = FileSearcher(config)
        files = searcher.find_files()
        processor = FileProcessor(config)
        processor.process(files)

        chunk_files = list(tmpdir.glob("part_*.txt"))
        assert len(chunk_files) >= 1
        total_content = ""
        for chunk_file in sorted(chunk_files):
            total_content += chunk_file.read_text()
        assert "link.txt" in total_content


def test_security_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "malicious.exe").write_text("malicious")

        config = AppConfig()
        config.base_dir = tmpdir
        config.extensions = [".exe", ".txt"]
        config.mode = "copy"
        config.unsafe = False

        searcher = FileSearcher(config)
        files = searcher.find_files()
        exe_files = [f for f in files if f.extension == ".exe"]
        assert len(exe_files) == 0
