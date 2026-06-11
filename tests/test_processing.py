from pathlib import Path

from iterecho.config import AppConfig
from iterecho.processing import FileProcessor
from iterecho.search import FileSearcher


def test_concat_streaming(tmp_path: Path):
    config = AppConfig()
    config.base_dir = tmp_path
    config.extensions = [".txt"]
    config.mode = "concatenate"
    config.output_prefix = "out"
    config.output_extension = ".txt"

    (tmp_path / "a.txt").write_text("hello ")
    (tmp_path / "b.txt").write_bytes(b"world" * 100000)  # ~500 KB

    searcher = FileSearcher(config)
    files = searcher.find_files()
    processor = FileProcessor(config)
    processor.process(files)

    output_path = tmp_path / "out.txt"
    assert output_path.exists()
    content = output_path.read_text()
    assert "hello" in content and "world" in content
