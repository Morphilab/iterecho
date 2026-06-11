from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileEntry:
    abs_path: Path
    name: str
    extension: str
    relative_path: str
    size: int
