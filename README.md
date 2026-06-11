# IterEcho — Secure File Processor

[![CI](https://github.com/Morphilab/iterecho/actions/workflows/test.yml/badge.svg)](https://github.com/Morphilab/iterecho/actions/workflows/test.yml)
[![Python Versions](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11%20|%203.12-blue)](#supported-python-versions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy strict](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org)
[![Security: bandit clean](https://img.shields.io/badge/security-bandit%20clean-brightgreen)](https://github.com/PyCQA/bandit)

IterEcho is a security-first Python 3.8+ CLI tool that **copies, concatenates,
or chunks** a tree of files. Designed for sysadmins and developers who need
to consolidate logs, bundle documentation, or split large archives into
size-bounded pieces — without accidentally executing scripts or leaking data
through symlink traversal.



## Why IterEcho?

- **Security-first by design.** Every file read uses `O_NOFOLLOW` and
  `fstat` on the open fd, eliminating TOCTOU windows. Path traversal
  is checked via `path.resolve()` + `relative_to(base)` in
  `SecurityEngine.is_within_base`. Critical extensions (`.exe`, `.bat`,
  `.dll`, `.ps1`, `.vbs`, …) are blocked unconditionally; warning
  extensions (`.py`, `.sh`, `.js`, …) require an explicit `--unsafe`.
- **Three modes, one tool.** `copy` (with name sanitization),
  `concatenate` (with file headers), `chunk` (size-bounded output).
- **Dual interface.** A Typer-based CLI with git-style global options
  + an interactive Rich-based TUI.
- **Streaming.** Files are read in 1 MiB chunks — no full-file memory
  load, no `shutil.copy2` corruption.
- **Concurrency-safe.** `fcntl.lockf` advisory lock (POSIX) prevents
  two instances from clobbering the same output directory; the lock
  is released via `atexit` if the process is killed mid-run.
- **Battle-tested.** 236 tests covering unit, integration, CLI
  (CliRunner), TUI (stdin mocking), and security edge cases.

## ⚠️ AI Disclosure / Divulgación de IA

**English:**
This project was developed with assistance from artificial intelligence tools. Given the automated nature of some components, users are advised to review and test the code independently before integrating it into their own systems.

**Español:**
Este proyecto fue desarrollado con asistencia de herramientas de inteligencia artificial. Dada la naturaleza automatizada de algunos componentes, se recomienda que los usuarios revisen y prueben el código independientemente antes de integrarlo en sus propios sistemas.

## Table of contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Modes](#modes)
- [Security](#security)
- [Architecture](#architecture)
- [Development](#development)
- [Roadmap](#roadmap)
- [Tests](#tests)
- [Contributing](#contributing)
- [License](#license)

## Installation

```bash
git clone https://github.com/Morphilab/iterecho.git
cd iterecho
pip install -e ".[dev]"
```

Or, once published, simply:

```bash
pip install iterecho
```

## Quick start

```bash
# Show version
iterecho --version

# Interactive mode (recommended for first use)
iterecho interactive

# Copy files with sanitization
iterecho --extensions .txt,.log --base-dir ./my-files --output-dir ./output copy

# Concatenate files (with file headers in the output)
iterecho --extensions .txt --base-dir ./data concatenate

# Split into size-bounded chunks
iterecho --extensions .txt --base-dir ./logs chunk --chunk-size 50M
```

Global options go before the subcommand; subcommand-specific options after:

```bash
iterecho --verbose --unsafe --extensions .py,.txt copy --follow-symlinks
iterecho --overwrite --output-dir ./out chunk --chunk-size 10M
```

## Modes

### `copy`

Copies files from `--base-dir` to `--output-dir` (defaults to in-place
sanitized copy). Names are sanitized to remove control characters, NUL
bytes, Windows-reserved names (`CON`, `NUL`, …), and Unicode spoofing
characters. Subdirectory structure is preserved.

```bash
iterecho --base-dir ./src --output-dir ./dst --extensions .md copy
```

### `concatenate`

Combines all matching files into a single output with a per-file header:

```
================================================================================
FILE: logs/2024-01-01.log (12,345 bytes)
================================================================================

...file contents...

================================================================================
FILE: logs/2024-01-02.log (15,678 bytes)
================================================================================
```

```bash
iterecho --base-dir ./logs --extensions .log --output-prefix combined concatenate
# -> ./combined.txt
```

### `chunk`

Splits the combined content into multiple files no larger than
`--chunk-size`. Files larger than `--chunk-size` are placed in their
own chunk with a warning.

```bash
iterecho --base-dir ./logs --extensions .log chunk --chunk-size 50M
# -> ./chunk_001.log, ./chunk_002.log, ...
```

## Security

IterEcho's security model is documented in detail in [`SECURITY.md`](SECURITY.md).
The short version:

| Threat | Mitigation |
| --- | --- |
| Path traversal via `..` or symlinks | `path.resolve()` + `relative_to(base)` |
| TOCTOU between validation and I/O | `os.open(O_NOFOLLOW)` + `os.fstat` on the fd |
| Symlink-chain escape | Resolved target re-validated against base |
| Race conditions across processes | `fcntl.lockf` advisory lock (POSIX) |
| Filename injection | `sanitize_filename` strips control chars, NULs, BOM, ZWJ |
| Visual spoofing via Unicode | NFC normalization; zero-width / RTL override replaced |
| Executable smuggling | `CRITICAL_EXTENSIONS` (44 entries) — always blocked |
| Script file processing | `WARNING_EXTENSIONS` blocked by default; require `--unsafe` |
| fd leaks on exception | per-entry try/finally + per-block context managers |
| Information disclosure | Lock file created with 0o600 permissions |

Reporting a vulnerability: email **lab@morphilab.com** (do not open a
public issue). See [`SECURITY.md`](SECURITY.md) for our coordinated
disclosure process.

## Architecture

```
iterecho/
  cli.py                # Typer app, git-style @app.callback() + subcommands
  models.py             # FileEntry dataclass
  search.py             # FileSearcher — walks base_dir, filters by ext/size/security
  processing.py         # FileProcessor — copy/concat/chunk + fcntl lock
  security.py           # SecurityEngine — path traversal / symlink validation
  tui.py                # Rich-based interactive mode
  config/               # Configuration package
    models.py           # SearchConfig, OutputConfig, SecuritySettings + parse_size/fmt_size
    sanitize.py         # CRITICAL/WARNING blocklists + sanitize_filename + is_safe_extension
    app.py              # AppConfig (backward-compatible delegation to dataclasses)
  utils/
    file_utils.py       # safe_file_copy / safe_read_file (O_NOFOLLOW, atomic tmp)
    logging.py          # setup_logging, ITERECHO_DEBUG env var
```

New consumers should use the dataclasses (`SearchConfig`, `OutputConfig`,
`SecuritySettings`) directly. `AppConfig` is a backward-compatible wrapper.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional: pre-commit hooks (run ruff/black/isort on staged files)
pip install pre-commit
pre-commit install
```

Run the quality gate locally:

```bash
pre-commit run --all-files          # ruff + black + isort
ruff check iterecho/ tests/        # or just ruff
black --check iterecho/ tests/     # or just black
mypy iterecho/                      # mypy strict
pytest --cov=iterecho --cov-report=term-missing   # 236 tests
python -m build                     # validate sdist + wheel
```

## Tests

```bash
pytest                              # 236 tests
pytest --cov=iterecho               # with coverage
pytest tests/test_security.py       # single file
pytest -k "symlink"                 # pattern match
```

The test suite is organized by concern:

- `test_security.py` — security invariants and parametrized blocklist
- `test_security_edge.py` — symlink, permission, sanitization edge cases
- `test_file_utils.py` — `safe_file_copy`, `safe_read_file`
- `test_config.py` — `AppConfig`, `parse_size`, `is_safe_extension`
- `test_search.py` — `FileSearcher`
- `test_processing.py` / `test_processing_unit.py` — `FileProcessor`
- `test_integration.py` — end-to-end flows for all three modes
- `test_cli.py` — Typer CliRunner
- `test_tui.py` — Rich TUI via stdin mocking

## Roadmap

- [x] `fcntl`-based atomic lock (replaced O_EXCL + PID liveness)
- [x] `--version` works without a subcommand
- [x] Per-extension blocklist regression tests (parametrized)
- [x] Symlink-in-parent regression tests
- [x] Bandit + pip-audit in CI
- [x] Pre-commit hooks
- [ ] Watch mode (continuous processing on file changes)
- [ ] Pluggable transformers (gzip, encrypt)
- [ ] Optional `nox` matrix for local cross-version testing

## Supported Python versions

3.8, 3.9, 3.10, 3.11, 3.12 — tested on every push via GitHub Actions.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All contributions are expected
to follow the Code of Conduct ([`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md))
and to be security-reviewed if they touch the file-I/O boundary.

## License

MIT © morphilab. See [`LICENSE`](LICENSE).
