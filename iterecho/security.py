from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

from iterecho.utils.logging import get_logger

logger = get_logger("security")


class SecurityEngine:
    def __init__(self, base_dir: Path, max_file_size: int):
        self.base_dir = base_dir.resolve()
        self.max_file_size = max_file_size

    def is_within_base(self, path: Path) -> bool:
        """Verify that a path is within the base directory, preventing symlink traversal."""
        try:
            real_path = path.resolve(strict=False)
            real_base = self.base_dir.resolve(strict=False)
            real_path.relative_to(real_base)
            return True
        except ValueError:
            return False
        except Exception as e:
            logger.warning(f"Path validation error: {e}")
            return False

    def validate_file(
        self, file_path: Path, follow_symlinks: bool = False
    ) -> tuple[bool, int, int | None]:
        """Validate a file considering security constraints and size limits.

        Uses open-then-fstat to eliminate the TOCTOU window present
        in stat-then-use patterns. Regular files are opened with
        O_NOFOLLOW; symlinks are resolved and opened directly when
        *follow_symlinks* is True, and rejected otherwise.

        Returns (is_valid, file_size_in_bytes, fd_or_none).
        When is_valid is True, fd_or_none is an open file descriptor that
        the caller MUST close with ``os.close(fd)`` — this eliminates the
        TOCTOU between validation and I/O for both regular files and symlinks.
        """
        try:
            # ── Attempt to open and validate as a regular file ──────
            try:
                fd = os.open(str(file_path), os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                return False, 0, None
            except PermissionError:
                return False, 0, None
            except OSError as e:
                if e.errno == errno.ELOOP:
                    # Symlink detected with O_NOFOLLOW — fall through
                    pass
                else:
                    return False, 0, None
            else:
                # Regular file opened successfully — validate via fstat
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    os.close(fd)
                    return False, 0, None
                if not self.is_within_base(file_path):
                    logger.warning(f"Traversal blocked: {file_path}")
                    os.close(fd)
                    return False, 0, None
                file_size = st.st_size
                if file_size > self.max_file_size:
                    logger.warning(f"File too large ({file_size:,} bytes): {file_path}")
                    os.close(fd)
                    return False, 0, None
                return True, file_size, fd

            # ── Symlink path ───────────────────────────────────────
            if not follow_symlinks:
                logger.warning(f"Symlink skipped (follow_symlinks disabled): {file_path}")
                return False, 0, None

            st = os.stat(str(file_path), follow_symlinks=False)
            if not stat.S_ISLNK(st.st_mode):
                return False, 0, None

            if not self.is_within_base(file_path):
                logger.warning(f"Traversal blocked: {file_path}")
                return False, 0, None

            # Read and resolve the symlink target
            target = Path(os.readlink(file_path))
            if target.is_absolute():
                resolved_target = target.resolve(strict=False)
            else:
                resolved_target = (file_path.parent.resolve(strict=False) / target).resolve(
                    strict=False
                )

            # Ensure the resolved target is within the base directory
            if not self.is_within_base(resolved_target):
                logger.warning(f"Dangerous symlink blocked: {file_path} -> {target}")
                return False, 0, None

            # Open target with O_NOFOLLOW (prevents symlink-chain attacks)
            try:
                fd = os.open(str(resolved_target), os.O_RDONLY | os.O_NOFOLLOW)
            except OSError:
                return False, 0, None

            # Validate via fstat (atomic: open + stat eliminates TOCTOU)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    os.close(fd)
                    return False, 0, None
                file_size = st.st_size
                if file_size > self.max_file_size:
                    logger.warning(f"File too large ({file_size:,} bytes): {file_path}")
                    os.close(fd)
                    return False, 0, None
                return True, file_size, fd
            except OSError:
                os.close(fd)
                return False, 0, None
        except OSError as e:
            logger.warning(f"Validation error {file_path}: {e}")
            return False, 0, None
