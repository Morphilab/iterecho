from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path


def fmt_size(size: int) -> str:
    if size >= 1024**4:
        return f"{size / (1024**4):.1f} TB"
    elif size >= 1024**3:
        return f"{size / (1024**3):.1f} GB"
    elif size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    elif size >= 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size} bytes"


def parse_size(size_str: str | int) -> int:
    if isinstance(size_str, int):
        return size_str
    orig = size_str
    s = str(size_str).strip().upper()
    s = re.sub(r"B$", "", s)
    if s.isdigit():
        return int(s)
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?)$", s)
    if not match:
        raise ValueError(
            f"Invalid size format: '{orig}' (valid examples: 100M, 1.5G, 10MB, 2048, 2TB)"
        )
    value = Decimal(match.group(1))
    unit = match.group(2) or ""
    multipliers = {
        "": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
    }
    result = int(round(value * Decimal(multipliers[unit])))
    if result < 0:
        raise ValueError(f"Size cannot be negative: '{orig}'")
    return result


class Mode(str, Enum):
    """Processing modes supported by IterEcho."""

    COPY = "copy"
    CONCATENATE = "concatenate"
    CHUNK = "chunk"


@dataclass
class SearchConfig:
    extensions: list[str] = field(default_factory=lambda: [".txt"])
    recursive: bool = True
    name_filter: str | None = None


@dataclass
class OutputConfig:
    mode: Mode = Mode.CONCATENATE
    output_dir: Path | None = None
    output_extension: str = ".txt"
    output_prefix: str = "concatenated"
    output_file: Path | None = None
    overwrite: bool = False
    chunk_size: int | None = None


@dataclass
class SecuritySettings:
    max_file_size: int = 100 * 1024 * 1024
    unsafe: bool = False
    follow_symlinks: bool = False
