from __future__ import annotations

from pathlib import Path

from iterecho.config.models import Mode, OutputConfig, SearchConfig, SecuritySettings, parse_size
from iterecho.config.sanitize import is_safe_extension
from iterecho.utils.logging import get_logger

logger = get_logger("config")


class AppConfig:
    """Main application configuration — delegates to focused dataclasses.

    Backward-compatible wrapper. New code should use SearchConfig,
    OutputConfig, and SecuritySettings directly.
    """

    def __init__(self) -> None:
        self.search = SearchConfig()
        self.output = OutputConfig()
        self.security = SecuritySettings()
        self.verbose: bool = False
        self.quiet: bool = False
        self._base_dir = Path.cwd()
        self._raw_extensions: list[str] | None = None

    def _apply_security_filter(self) -> None:
        if self._raw_extensions is None:
            source = self.search.extensions
        else:
            source = self._raw_extensions
        safe_extensions = [ext for ext in source if is_safe_extension(ext, self.security.unsafe)]
        if len(safe_extensions) < len(source):
            blocked = set(source) - set(safe_extensions)
            logger.warning(f"Blocked unsafe extensions: {', '.join(blocked)}")
        self.search.extensions = safe_extensions
        if not self.search.extensions:
            raise ValueError("No valid extensions provided after security filtering.")

    # ── base_dir ──────────────────────────────────────────────────────

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @base_dir.setter
    def base_dir(self, value: str | Path) -> None:
        p = Path(value).resolve()
        if not p.exists():
            raise ValueError(f"Base directory does not exist: {p}")
        if not p.is_dir():
            raise ValueError(f"Base directory is not a directory: {p}")
        self._base_dir = p

    # ── search delegation ─────────────────────────────────────────────

    @property
    def extensions(self) -> list[str]:
        return self.search.extensions

    @extensions.setter
    def extensions(self, value: str | list[str]) -> None:
        if isinstance(value, str):
            value = [e.strip().lower() for e in value.split(",") if e.strip()]
        value = [e if e.startswith(".") else "." + e for e in value]
        self._raw_extensions = value.copy()
        self.search.extensions = value
        self._apply_security_filter()

    @property
    def recursive(self) -> bool:
        return self.search.recursive

    @recursive.setter
    def recursive(self, value: bool) -> None:
        self.search.recursive = value

    @property
    def name_filter(self) -> str | None:
        return self.search.name_filter

    @name_filter.setter
    def name_filter(self, value: str | None) -> None:
        self.search.name_filter = value

    # ── output delegation ─────────────────────────────────────────────

    @property
    def mode(self) -> Mode:
        return self.output.mode

    @mode.setter
    def mode(self, value: str | Mode) -> None:
        if isinstance(value, Mode):
            self.output.mode = value
        elif value in {m.value for m in Mode}:
            self.output.mode = Mode(value)
        else:
            raise ValueError(f"Mode must be one of: {', '.join(m.value for m in Mode)}")

    @property
    def output_dir(self) -> Path | None:
        return self.output.output_dir

    @output_dir.setter
    def output_dir(self, value: Path | None) -> None:
        if value is None:
            self.output.output_dir = None
        else:
            self.output.output_dir = Path(value).resolve()

    @property
    def output_extension(self) -> str:
        return self.output.output_extension

    @output_extension.setter
    def output_extension(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Output extension cannot be empty")
        v = value.strip()
        if not v.startswith("."):
            v = "." + v
        self.output.output_extension = v.lower()

    @property
    def output_prefix(self) -> str:
        return self.output.output_prefix

    @output_prefix.setter
    def output_prefix(self, value: str) -> None:
        stripped = value.strip() if value else ""
        self.output.output_prefix = stripped or "concatenated"

    @property
    def output_file(self) -> Path | None:
        return self.output.output_file

    @output_file.setter
    def output_file(self, value: Path | None) -> None:
        self.output.output_file = Path(value) if value else None

    @property
    def overwrite(self) -> bool:
        return self.output.overwrite

    @overwrite.setter
    def overwrite(self, value: bool) -> None:
        self.output.overwrite = value

    # ── security delegation ───────────────────────────────────────────

    @property
    def max_file_size(self) -> int:
        return self.security.max_file_size

    @max_file_size.setter
    def max_file_size(self, value: str | int) -> None:
        self.security.max_file_size = parse_size(value)

    @property
    def unsafe(self) -> bool:
        return self.security.unsafe

    @unsafe.setter
    def unsafe(self, value: bool) -> None:
        self.security.unsafe = value
        self._apply_security_filter()

    @property
    def follow_symlinks(self) -> bool:
        return self.security.follow_symlinks

    @follow_symlinks.setter
    def follow_symlinks(self, value: bool) -> None:
        self.security.follow_symlinks = value

    # ── chunk delegation ──────────────────────────────────────────────

    @property
    def chunk_size(self) -> int | None:
        return self.output.chunk_size

    @chunk_size.setter
    def chunk_size(self, value: str | None) -> None:
        if value is None:
            self.output.chunk_size = None
        else:
            self.output.chunk_size = parse_size(value)
