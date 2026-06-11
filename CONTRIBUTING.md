# Contributing to IterEcho

## How to contribute

1. **Fork** the repository
2. Create a branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Ensure all tests pass:
   ```bash
   pip install -e ".[dev]"
   pytest                           # 236 tests
   ruff check --fix && black . && isort . && mypy iterecho/
   ```
5. Commit with a clear message ([Conventional Commits](https://www.conventionalcommits.org/))
6. Open a **Pull Request**

## Code standards

- **Black** (line-length: 100), **Ruff**, **mypy** (strict)
- Type hints required for all function signatures
- `from __future__ import annotations` at the top of every module
- All code, comments, and user-facing text in **English**
- Docstrings: Google style, triple-quoted. Omit if implementation is self-documenting.

## Architecture notes

```
iterecho/
  config/          # Focused modules (models, parse, blocklists, sanitize, app)
    models.py      # SearchConfig, OutputConfig, SecuritySettings dataclasses
    app.py         # AppConfig wrapper (backward compat with old consumers)
  security.py      # SecurityEngine: is_within_base + validate_file only
  processing.py    # FileProcessor: copy/concat/chunk + concurrency lock
  utils/
    file_utils.py  # safe_file_copy, safe_read_file (O_NOFOLLOW, atomic tmp)
  tui.py           # Rich-based interactive mode
```

New consumers should use the dataclasses (`SearchConfig`, `OutputConfig`,
`SecuritySettings`) directly instead of `AppConfig`.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Pre-commit hooks (recommended; runs ruff/black/isort on staged files)
pip install pre-commit
pre-commit install
```

To run the hooks on demand (the same checks CI runs, except mypy):

```bash
pre-commit run --all-files
```

## Testing

```bash
pytest                              # all 236 tests
pytest --cov=iterecho --cov-report=term-missing
pytest tests/test_security.py       # single file
pytest -k "tui"                     # pattern match
```

## Concurrency lock

The `FileProcessor` acquires an atomic file lock (`.iterecho.lock`) in the
output directory before writing. If you add new write paths, ensure they
participate in the lock or opt out explicitly.

## Reporting bugs

Open an Issue with steps to reproduce. Include Python version and OS.
