import os
from pathlib import Path

import pytest

from iterecho.config.sanitize import CRITICAL_EXTENSIONS, is_safe_extension
from iterecho.security import SecurityEngine


@pytest.fixture
def engine(tmp_path: Path):
    return SecurityEngine(base_dir=tmp_path, max_file_size=100_000_000)


def test_validate_file_outside_base(engine: SecurityEngine, tmp_path: Path):
    outside = tmp_path.parent / "outside.txt"
    if outside.exists():
        outside.unlink()
    outside.touch()
    valid, size, fd = engine.validate_file(outside)
    assert valid is False
    assert size == 0
    assert fd is None
    outside.unlink()


def test_validate_file_symlink_inside_ok(engine: SecurityEngine, tmp_path: Path):
    target = tmp_path / "real.txt"
    target.write_text("ok")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    valid, size, fd = engine.validate_file(link, follow_symlinks=True)
    assert valid is True
    assert size > 0
    assert fd is not None  # symlinks return an fd
    os.close(fd)


def test_validate_file_too_large(engine: SecurityEngine, tmp_path: Path):
    small_engine = SecurityEngine(base_dir=tmp_path, max_file_size=100)
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * 200)
    valid, size, fd = small_engine.validate_file(big)
    assert valid is False
    assert size == 0
    assert fd is None


def test_validate_file_symlink_in_parent_path_resolved_outside_base(tmp_path: Path):
    """Test that a symlink in a parent path that resolves outside base is correctly rejected."""
    # Create base directory
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    # Create a file outside base that we'll symlink to
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("secret")

    # Create a symlink in base that points to the outside file via a relative path
    # base/link_to_outside.txt -> ../outside.txt
    link_in_base = base_dir / "link_to_outside.txt"
    link_in_base.symlink_to("../outside.txt")

    # Create a dedicated engine scoped to base_dir, so ../outside.txt IS outside base
    local_engine = SecurityEngine(base_dir=base_dir, max_file_size=100_000_000)

    # Validate the symlink - should be rejected because target is outside base
    valid, size, fd = local_engine.validate_file(link_in_base, follow_symlinks=True)
    assert valid is False
    assert size == 0
    assert fd is None


class TestCriticalExtensionsAlwaysBlocked:
    """Regression: critical extensions must be blocked even with unsafe=True.

    This guards the invariant that ``--unsafe`` is a *relaxation*, not a
    blanket bypass. The blocklist for executables (``.exe``, ``.bat``,
    ``.dll``, ``.ps1``, ``.vbs`` etc.) is absolute.
    """

    @pytest.mark.parametrize("ext", sorted(CRITICAL_EXTENSIONS))
    def test_critical_blocked_in_safe_mode(self, ext: str) -> None:
        assert is_safe_extension(ext, unsafe_mode=False) is False

    @pytest.mark.parametrize("ext", sorted(CRITICAL_EXTENSIONS))
    def test_critical_blocked_in_unsafe_mode(self, ext: str) -> None:
        # unsafe_mode=True relaxes WARNING_EXTENSIONS only; CRITICAL stays blocked.
        assert is_safe_extension(ext, unsafe_mode=True) is False

    def test_warning_blocked_in_safe_mode(self) -> None:
        assert is_safe_extension(".py", unsafe_mode=False) is False
        assert is_safe_extension(".sh", unsafe_mode=False) is False
        assert is_safe_extension(".js", unsafe_mode=False) is False

    def test_warning_allowed_in_unsafe_mode(self) -> None:
        assert is_safe_extension(".py", unsafe_mode=True) is True
        assert is_safe_extension(".sh", unsafe_mode=True) is True
        assert is_safe_extension(".js", unsafe_mode=True) is True
