from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Generator

from iterecho.utils.logging import get_logger

logger = get_logger("file_utils")


def _open_secure(path: Path, follow_symlinks: bool = False) -> int:
    """Open a regular file securely, returning a file descriptor.

    Uses O_NOFOLLOW to prevent symlink race attacks unless follow_symlinks is True,
    in which case the symlink is resolved first and then opened without O_NOFOLLOW.
    Raises RuntimeError if the path is not a regular file.
    """
    if follow_symlinks:
        resolved = path.resolve(strict=False)
        fd = os.open(str(resolved), os.O_RDONLY | os.O_NOFOLLOW)
    else:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f"Not a regular file: {path}")
    except Exception:
        os.close(fd)
        raise
    return fd


def safe_read_file(
    path: Path,
    chunk_size: int = 1024 * 1024,
    follow_symlinks: bool = False,
    src_fd: int | None = None,
) -> Generator[bytes, None, None]:
    """Read a file safely with TOCTOU protection, yielding chunks.

    If *src_fd* is provided it is used directly, bypassing *path*
    and *follow_symlinks*.  If *src_fd* is None, the fd is closed when the generator
    is exhausted; if *src_fd* is provided, the caller owns the fd.
    This eliminates the TOCTOU window between
    validation and actual I/O.
    """
    fd = src_fd if src_fd is not None else _open_secure(path, follow_symlinks)
    try:
        while True:
            chunk = os.read(fd, chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        if src_fd is None:
            try:
                os.close(fd)
            except OSError:
                pass


def safe_file_copy(
    src: Path,
    dst: Path,
    follow_symlinks: bool = False,
    src_fd: int | None = None,
) -> bool:
    """Copy a file safely using an atomic temporary file with TOCTOU protection.

    If *src_fd* is provided it is used directly, bypassing *src*
    and *follow_symlinks*.  The fd is closed when the copy completes.
    """
    tmp = None
    try:
        if src.resolve() == dst.resolve():
            logger.warning(f"Source and destination are the same file: {src}")
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)

        # Determine if we should close the fd after use
        should_close_fd = src_fd is None
        fd = src_fd if src_fd is not None else _open_secure(src, follow_symlinks)
        try:
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            with open(tmp, "wb") as f_out:
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    f_out.write(chunk)
            tmp.replace(dst)
        finally:
            if should_close_fd:
                try:
                    os.close(fd)
                except OSError:
                    pass

        logger.debug(f"Copied {src} -> {dst}")
        return True

    except Exception as e:
        logger.error(f"Copy failed {src} -> {dst}: {e}")
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        return False
