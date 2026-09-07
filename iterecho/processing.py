from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path
from typing import BinaryIO

from tqdm import tqdm

from iterecho.config import AppConfig, Mode, sanitize_filename
from iterecho.models import FileEntry
from iterecho.security import SecurityEngine
from iterecho.utils.file_utils import safe_file_copy, safe_read_file
from iterecho.utils.logging import get_logger

logger = get_logger("processing")

_LOCK_MODE = 0o600
_LOCK_BASENAME = ".iterecho.lock"


class FileProcessor:
    def __init__(self, config: AppConfig, security: SecurityEngine | None = None) -> None:
        self.config = config
        self.security = security or SecurityEngine(config.base_dir, config.max_file_size)
        self._lock_path: Path | None = None
        self._lock_fd: int | None = None
        self._atexit_registered = False

    # ── Concurrency lock ────────────────────────────────────────

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        """Check whether a process with the given PID is still running."""
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    def _lock_output_dir(self, output_dir: Path) -> None:
        """Acquire an exclusive file-based lock on the output directory.

        Strategy:
        - POSIX (Linux/macOS): open the lock file (creating it if missing)
          and take an advisory POSIX lock via ``fcntl.lockf(LOCK_EX | LOCK_NB)``.
          ``fcntl`` is the only race-free way to detect a held lock; the
          O_CREAT|O_EXCL fallback has a TOCTOU window when the holder dies
          between the create attempt and the lock acquire.
        - Windows: fall back to O_CREAT|O_EXCL + PID-liveness approach
          because ``fcntl`` is unavailable.
        """
        lock_path = output_dir.resolve() / _LOCK_BASENAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Try fcntl first (POSIX). This is the race-free path.
        if sys.platform != "win32":
            try:
                import fcntl  # local import: not available on Windows

                fcntl_available = True
            except ImportError:
                fcntl_available = False
        else:
            fcntl_available = False

        for attempt in range(3):
            if fcntl_available:
                # Open (creating if absent) and try the advisory lock.
                fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, mode=_LOCK_MODE)
                try:
                    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as e:
                    os.close(fd)
                    if e.errno in (11, 13, 35):  # EAGAIN, EACCES, EDEADLK
                        logger.error(
                            f"Output directory is locked by another process: {lock_path}. "
                            "Wait for it to finish or remove the lock file manually."
                        )
                        raise SystemExit(1) from None
                    raise SystemExit(1) from None
                os.write(fd, str(os.getpid()).encode("ascii"))
                self._lock_path = lock_path
                self._lock_fd = fd
                if not self._atexit_registered:
                    atexit.register(self._release_lock)
                    self._atexit_registered = True
                return

            # Fallback path: O_CREAT|O_EXCL with PID liveness.
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, mode=_LOCK_MODE)
            except FileExistsError:
                self._handle_existing_lock(lock_path)
            except OSError as e:
                logger.error(f"Failed to open lock file {lock_path}: {e}")
                raise SystemExit(1) from None
            else:
                os.write(fd, str(os.getpid()).encode("ascii"))
                self._lock_path = lock_path
                self._lock_fd = fd
                if not self._atexit_registered:
                    atexit.register(self._release_lock)
                    self._atexit_registered = True
                return

            if attempt < 2:
                time.sleep(0.1 * (2**attempt))

        logger.error(f"Could not acquire lock after 3 attempts: {lock_path}")
        raise SystemExit(1)

    def _handle_existing_lock(self, lock_path: Path) -> None:
        """Inspect an existing lock file and decide whether to remove it."""
        try:
            existing_pid = int(lock_path.read_text().strip())
            if self._is_process_alive(existing_pid):
                logger.error(
                    f"Lock file exists: {lock_path}. "
                    "Another instance appears to be running in this output directory. "
                    "If no other instance is running, delete the lock file manually."
                )
                raise SystemExit(1) from None
        except (ValueError, OSError):
            pass
        logger.warning(f"Removing stale lock file: {lock_path}")
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    def _release_lock(self) -> None:
        """Release the advisory lock and remove the lock file.

        Safe to call multiple times. Also registered with ``atexit`` so the
        lock is cleaned up if the process is killed mid-run.
        """
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        if self._lock_path is not None:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._lock_path = None

    # ── Entry point ─────────────────────────────────────────────

    def process(self, files: list[FileEntry]) -> None:
        """Process files according to the configured mode."""
        try:
            # Copy locks only when targeting a shared output directory;
            # concatenate and chunk always write into one.
            if self.config.mode is Mode.COPY:
                if self.config.output_dir:
                    self._lock_output_dir(self.config.output_dir)
            elif self.config.mode in (Mode.CONCATENATE, Mode.CHUNK):
                output_dir = self.config.output_dir or self.config.base_dir
                self._lock_output_dir(output_dir)

            if self.config.mode is Mode.COPY:
                self._copy_mode(files)
            elif self.config.mode is Mode.CONCATENATE:
                self._concatenate_mode(files)
            elif self.config.mode is Mode.CHUNK:
                self._chunk_mode(files)
            else:
                raise ValueError(f"Unknown mode: {self.config.mode}")
        finally:
            self._release_lock()

    def _copy_mode(self, files: list[FileEntry]) -> None:
        """Copy files with name sanitization, preserving directory structure."""
        logger.info("COPY mode started")

        for entry in tqdm(files, desc="Copying", unit="file"):
            fd = None
            try:
                valid, _, fd = self.security.validate_file(
                    entry.abs_path, follow_symlinks=self.config.follow_symlinks
                )
                if not valid:
                    logger.warning(f"Security validation failed for: {entry.abs_path}")
                    continue

                safe_name = sanitize_filename(entry.name)
                if not safe_name:
                    logger.warning(f"Sanitized filename is empty for {entry.name}, skipping")
                    continue
                new_name = Path(safe_name).with_suffix(self.config.output_extension).name

                if self.config.output_dir:
                    safe_dir_parts = []
                    for part in Path(entry.relative_path).parent.parts:
                        safe_part = sanitize_filename(part)
                        safe_dir_parts.append(safe_part)
                    safe_dest_dir = self.config.output_dir / Path(*safe_dir_parts)
                    safe_dest_dir.mkdir(parents=True, exist_ok=True)
                    destination = safe_dest_dir / new_name
                else:
                    destination = entry.abs_path.with_name(new_name)

                if destination.exists() and not self.config.overwrite:
                    logger.debug(f"Skipped (exists): {destination}")
                    continue

                if not safe_file_copy(
                    entry.abs_path, destination, self.config.follow_symlinks, src_fd=fd
                ):
                    # safe_file_copy already logged the cause and cleaned up
                    # the .tmp file. We raise to bail out of this entry's try
                    # block; the outer except below logs at error level and
                    # we move on to the next file.
                    raise RuntimeError("Copy failed")

                logger.debug(f"Copied → {destination}")

            except Exception as e:
                logger.error(f"Copy failed {entry.abs_path}: {e}")
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def _concatenate_mode(self, files: list[FileEntry]) -> None:
        """Concatenate all files into a single output file."""
        logger.info("CONCATENATE mode started")
        output_dir = self.config.output_dir or self.config.base_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.output_file:
            output_path = output_dir / self.config.output_file
        else:
            output_path = output_dir / f"{self.config.output_prefix}{self.config.output_extension}"
        if output_path.exists() and not self.config.overwrite:
            logger.error(f"Output file exists and --overwrite not set: {output_path}")
            raise SystemExit(1)
        self._write_single_file(files, output_path)
        logger.info(f"\nConcatenated file → {output_path}")

    def _chunk_mode(self, files: list[FileEntry]) -> None:
        """Split combined content into multiple chunk files by size."""
        logger.info("CHUNK mode started")
        if not self.config.chunk_size or self.config.chunk_size <= 0:
            logger.error(f"chunk_size must be positive, got: {self.config.chunk_size or 0}")
            raise SystemExit(1)
        output_dir = self.config.output_dir or self.config.base_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        if not self.config.overwrite:
            prefix = self.config.output_prefix
            ext = self.config.output_extension
            existing = sorted(output_dir.glob(f"{prefix}_*{ext}"))
            if existing:
                for p in existing:
                    logger.warning(f"Existing chunk: {p.name}")
                logger.error("Chunks already exist. Use --overwrite to overwrite.")
                raise SystemExit(1)
        self._write_chunks(files, output_dir)
        logger.info(f"\nFiles split into chunks in → {output_dir}")

    def _write_single_file(self, files: list[FileEntry], output_path: Path) -> None:
        """Write a single concatenated output file."""
        if not files:
            logger.info("No files to process")
            # Always leave a valid (empty) output file behind so downstream
            # consumers can rely on the artifact existing.
            output_path.touch(exist_ok=True)
            return

        total_bytes = self._total_output_bytes(files)
        with tqdm(total=total_bytes, unit="B", unit_scale=True, desc="Writing") as pbar:
            with open(output_path, "wb") as out:
                for entry in files:
                    try:
                        self._write_file_entry(entry, out, pbar)
                    except (OSError, RuntimeError) as e:
                        logger.error(f"Failed to process {entry.relative_path}: {e}")

    def _write_chunks(self, files: list[FileEntry], output_dir: Path) -> None:
        """Write files split into chunks by size."""
        if not files:
            logger.info("No files to process")
            output_dir.mkdir(parents=True, exist_ok=True)
            return

        chunk_number = 1
        current_size = 0
        total_bytes = self._total_output_bytes(files)
        pbar = tqdm(total=total_bytes, unit="B", unit_scale=True, desc="Chunking")
        prefix = self.config.output_prefix
        extension = self.config.output_extension
        chunk_size = self.config.chunk_size
        if chunk_size is None:
            raise RuntimeError("chunk_size is required for chunk mode")
        try:
            for entry in files:
                header_bytes = self._get_file_header(entry).encode("utf-8")
                header_size = len(header_bytes)  # Header size without trailing newline
                if entry.size > chunk_size:
                    logger.warning(
                        f"File '{entry.relative_path}' ({entry.size:,} bytes) "
                        f"exceeds chunk_size ({chunk_size:,} bytes). "
                        "Placing it entirely in the current chunk (may exceed the limit)."
                    )
                # Account for header, file content, and the trailing newline
                needed_size = entry.size + header_size + 1
                if current_size == 0 or (
                    current_size + needed_size > chunk_size and current_size > 0
                ):
                    chunk_path = output_dir / f"{prefix}_{chunk_number:03d}{extension}"
                    chunk_number += 1
                    current_size = 0
                    with open(chunk_path, "wb") as out:
                        try:
                            written = self._write_file_entry(
                                entry, out, pbar, pre_encoded_header=header_bytes
                            )
                            current_size += written
                        except (OSError, RuntimeError) as e:
                            logger.error(f"Failed to process {entry.relative_path}: {e}")
                else:
                    # Reuse the current chunk — but we have no long-lived file
                    # handle because we scope it per chunk. Re-open the previous
                    # chunk in append mode.
                    previous_path = output_dir / f"{prefix}_{chunk_number - 1:03d}{extension}"
                    with open(previous_path, "ab") as out:
                        try:
                            written = self._write_file_entry(
                                entry, out, pbar, pre_encoded_header=header_bytes
                            )
                            current_size += written
                        except (OSError, RuntimeError) as e:
                            logger.error(f"Failed to process {entry.relative_path}: {e}")
        finally:
            pbar.close()

    def _write_file_entry(
        self,
        entry: FileEntry,
        out: BinaryIO,
        pbar: tqdm,
        pre_encoded_header: bytes | None = None,
    ) -> int:
        """Write a single file entry into the output stream. Returns bytes written."""
        valid, _, fd = self.security.validate_file(
            entry.abs_path, follow_symlinks=self.config.follow_symlinks
        )
        if not valid:
            raise RuntimeError(f"Validation failed: {entry.abs_path}")

        header = (
            pre_encoded_header
            if pre_encoded_header is not None
            else self._get_file_header(entry).encode("utf-8")
        )
        out.write(header)
        total = len(header)
        pbar.update(len(header))

        fd_to_close = fd
        try:
            for chunk in safe_read_file(
                entry.abs_path,
                src_fd=fd,
                follow_symlinks=self.config.follow_symlinks,
            ):
                out.write(chunk)
                total += len(chunk)
                pbar.update(len(chunk))
        finally:
            if fd_to_close is not None:
                try:
                    os.close(fd_to_close)
                except OSError:
                    pass

        out.write(b"\n")
        total += 1
        pbar.update(1)
        return total

    def _file_overhead_bytes(self, entry: FileEntry) -> int:
        """Return the number of overhead bytes written for this entry (header + newline)."""
        return len(self._get_file_header(entry).encode("utf-8")) + 1

    def _total_output_bytes(self, files: list[FileEntry]) -> int:
        """Return total output bytes including content, headers, and newlines."""
        return sum(entry.size + self._file_overhead_bytes(entry) for entry in files)

    def _get_file_header(self, entry: FileEntry) -> str:
        """Generate the file header marker for the output stream."""
        return f"\n{'=' * 80}\nFILE: {entry.relative_path} ({entry.size:,} bytes)\n{'=' * 80}\n\n"
