from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Generator

from iterecho.config import AppConfig
from iterecho.models import FileEntry
from iterecho.utils.logging import get_logger

logger = get_logger("search")


class FileSearcher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._extensions = {e.lower() for e in config.extensions}

    def _file_generator(self) -> Generator[Path, None, None]:
        if self.config.recursive:
            paths = self._walk_recursive(self.config.base_dir)
        else:
            paths = self.config.base_dir.iterdir()

        for path in paths:
            if path.is_symlink() and not self.config.follow_symlinks:
                continue
            if path.is_file():
                yield path

    def _walk_recursive(self, root: Path) -> Generator[Path, None, None]:
        """Recursively walk directories, skipping symlink directories."""
        try:
            entries = list(root.iterdir())
        except OSError:
            return
        for entry in entries:
            yield entry
            if entry.is_dir() and not entry.is_symlink():
                yield from self._walk_recursive(entry)

    def find_files(self) -> list[FileEntry]:
        files: list[FileEntry] = []
        exts = self._extensions
        name_filter = self.config.name_filter.lower() if self.config.name_filter else None

        for path in self._file_generator():
            if path.suffix.lower() not in exts:
                continue
            if name_filter and name_filter not in path.name.lower():
                continue

            try:
                lst = os.lstat(str(path))
            except OSError:
                continue

            if stat.S_ISREG(lst.st_mode):
                file_size = lst.st_size
            elif stat.S_ISLNK(lst.st_mode):
                if not self.config.follow_symlinks:
                    continue
                try:
                    file_size = path.stat().st_size
                except OSError:
                    continue
            else:
                continue

            if file_size > self.config.max_file_size:
                logger.debug(f"Skipped (too large): {path}")
                continue

            try:
                rel = path.relative_to(self.config.base_dir)
            except ValueError:
                logger.debug(f"Skipped (path outside base): {path}")
                continue
            files.append(
                FileEntry(
                    abs_path=path,
                    name=path.name,
                    extension=path.suffix,
                    relative_path=str(rel),
                    size=file_size,
                )
            )

        files.sort(key=lambda f: f.relative_path)
        logger.debug(f"Search completed → {len(files)} files found")
        return files
