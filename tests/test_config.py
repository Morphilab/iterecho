from __future__ import annotations

from pathlib import Path

import pytest

from iterecho.config import AppConfig, is_safe_extension, parse_size


class TestParseSize:
    def test_basic_values(self):
        assert parse_size("100") == 100
        assert parse_size("0") == 0
        assert parse_size("50K") == 50 * 1024
        assert parse_size("1.5M") == int(1.5 * 1024 * 1024)
        assert parse_size("2G") == 2 * 1024**3
        assert parse_size("1TB") == 1024**4

    def test_with_b_suffix(self):
        assert parse_size("10MB") == 10 * 1024**2
        assert parse_size("500KB") == 500 * 1024
        assert parse_size("1GB") == 1024**3

    def test_whitespace(self):
        assert parse_size("100 M") == 100 * 1024**2
        assert parse_size(" 50K ") == 50 * 1024

    def test_integer_input(self):
        assert parse_size(2048) == 2048

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_size("invalid")
        with pytest.raises(ValueError):
            parse_size("")
        with pytest.raises(ValueError):
            parse_size("XYZ")


class TestSecurityConfig:
    def test_safe_extension(self):
        assert is_safe_extension(".txt") is True
        assert is_safe_extension(".md") is True
        assert is_safe_extension(".csv") is True

    def test_unsafe_mode_allows_warning(self):
        assert is_safe_extension(".py", unsafe_mode=True) is True
        assert is_safe_extension(".sh", unsafe_mode=True) is True
        assert is_safe_extension(".js", unsafe_mode=True) is True

    def test_safe_mode_blocks_warning(self):
        assert is_safe_extension(".py", unsafe_mode=False) is False
        assert is_safe_extension(".sh", unsafe_mode=False) is False

    def test_critical_always_blocked(self):
        assert is_safe_extension(".exe") is False
        assert is_safe_extension(".exe", unsafe_mode=True) is False
        assert is_safe_extension(".bat") is False
        assert is_safe_extension(".dll") is False

    def test_case_insensitive(self):
        assert is_safe_extension(".PY") is False
        assert is_safe_extension(".TXT") is True
        assert is_safe_extension(".EXE") is False

    def test_no_dot_returns_false(self):
        assert is_safe_extension("txt") is False
        assert is_safe_extension("") is False


class TestAppConfig:
    def test_default_values(self):
        config = AppConfig()
        assert config.mode == "concatenate"
        assert config.extensions == [".txt"]
        assert config.recursive is True
        assert config.unsafe is False
        assert config.verbose is False
        assert config.overwrite is False
        assert config.max_file_size == 100 * 1024 * 1024
        assert config.output_extension == ".txt"
        assert config.output_prefix == "concatenated"
        assert config.chunk_size is None

    def test_mode_valid(self):
        config = AppConfig()
        config.mode = "copy"
        assert config.mode == "copy"
        config.mode = "concatenate"
        assert config.mode == "concatenate"
        config.mode = "chunk"
        assert config.mode == "chunk"

    def test_mode_invalid_raises(self):
        config = AppConfig()
        with pytest.raises(ValueError, match="Mode must be one of"):
            config.mode = "invalid"

    def test_extension_filter_blocks_warning(self):
        config = AppConfig()
        config.extensions = [".py", ".txt"]
        assert ".py" not in config.extensions
        assert ".txt" in config.extensions

    def test_unsafe_extension_allowed_with_flag(self):
        config = AppConfig()
        config.unsafe = True
        config.extensions = [".py", ".txt"]
        assert ".py" in config.extensions
        assert ".txt" in config.extensions

    def test_critical_always_filtered(self):
        config = AppConfig()
        config.unsafe = True
        config.extensions = [".exe", ".txt"]
        assert ".exe" not in config.extensions
        assert ".txt" in config.extensions

    def test_no_valid_extensions_raises(self):
        config = AppConfig()
        with pytest.raises(ValueError, match="No valid extensions"):
            config.extensions = [".exe", ".bat"]

    def test_output_extension_normalizes(self):
        config = AppConfig()
        config.output_extension = ".TXT"
        assert config.output_extension == ".txt"
        config.output_extension = "md"
        assert config.output_extension == ".md"

    def test_base_dir_validation(self, tmp_path: Path):
        config = AppConfig()
        config.base_dir = tmp_path
        assert config.base_dir == tmp_path.resolve()

    def test_base_dir_nonexistent_raises(self):
        config = AppConfig()
        with pytest.raises(ValueError, match="does not exist"):
            config.base_dir = Path("/nonexistent/path")

    def test_base_dir_not_directory_raises(self, tmp_path: Path):
        config = AppConfig()
        f = tmp_path / "file.txt"
        f.write_text("test")
        with pytest.raises(ValueError, match="not a directory"):
            config.base_dir = f

    def test_output_dir_does_not_create_directory(self, tmp_path: Path):
        config = AppConfig()
        out = tmp_path / "new" / "nested" / "dir"
        config.output_dir = out
        assert not out.exists()
        assert config.output_dir == out

    def test_max_file_size_parsing(self):
        config = AppConfig()
        config.max_file_size = "50M"
        assert config.max_file_size == 50 * 1024 * 1024

    def test_chunk_size_parsing(self):
        config = AppConfig()
        config.chunk_size = "10M"
        assert config.chunk_size == 10 * 1024 * 1024

    def test_chunk_size_none(self):
        config = AppConfig()
        config.chunk_size = None
        assert config.chunk_size is None

    def test_output_prefix_empty_fallback(self):
        config = AppConfig()
        config.output_prefix = ""
        assert config.output_prefix == "concatenated"

    def test_output_file(self):
        config = AppConfig()
        config.output_file = Path("out.txt")
        assert config.output_file == Path("out.txt")
        config.output_file = None
        assert config.output_file is None

    def test_overwrite(self):
        config = AppConfig()
        assert config.overwrite is False
        config.overwrite = True
        assert config.overwrite is True

    def test_follow_symlinks(self):
        config = AppConfig()
        assert config.follow_symlinks is False
        config.follow_symlinks = True
        assert config.follow_symlinks is True

    def test_extensions_from_string(self):
        config = AppConfig()
        config.extensions = ".txt,.md,.py"
        assert ".txt" in config.extensions
        assert ".md" in config.extensions
        # .py should be filtered (unsafe=False by default)
        assert ".py" not in config.extensions

    def test_extensions_with_spaces(self):
        config = AppConfig()
        config.extensions = " .txt , .md "
        assert ".txt" in config.extensions
        assert ".md" in config.extensions

    def test_extensions_without_dot_normalized(self):
        config = AppConfig()
        config.extensions = "txt,log,md"
        assert ".txt" in config.extensions
        assert ".log" in config.extensions
        assert ".md" in config.extensions
