from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_path_with_files(tmp_path: Path):
    def _make(files_dict: dict[str, str | bytes]):
        for path, content in files_dict.items():
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                full.write_bytes(content)
            else:
                full.write_text(content)

    return tmp_path, _make
