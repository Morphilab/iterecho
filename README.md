# IterEcho — Secure File Processor

**English** | [Español](README.es.md)

[![CI](https://github.com/Morphilab/iterecho/actions/workflows/test.yml/badge.svg)](https://github.com/Morphilab/iterecho/actions/workflows/test.yml)
[![Python Versions](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13%20|%203.14-blue)](#supported-python-versions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy strict](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org)
[![Security: bandit clean](https://img.shields.io/badge/security-bandit%20clean-brightgreen)](https://github.com/PyCQA/bandit)

IterEcho is a security-first Python 3.8+ CLI tool that **copies, concatenates,
or chunks** a tree of files. Designed for sysadmins and developers who need
to consolidate logs, bundle documentation, or split large archives into
size-bounded pieces — without accidentally including scripts or leaking data
through symlink traversal.

## Why IterEcho?

- **Security-first by design.** Source files are opened with `O_NOFOLLOW`
  and validated via `fstat` on the open descriptor, eliminating the
  validation-to-read TOCTOU window. Path traversal is checked via
  `path.resolve()` + `relative_to(base)` in `SecurityEngine.is_within_base`.
  Requested critical extensions (`.exe`, `.bat`, `.dll`, `.ps1`, `.vbs`, …)
  are rejected unconditionally (the filter applies to the searched path's
  extension); warning extensions (`.py`, `.sh`, `.js`, …) require an explicit
  `--unsafe`.
- **Three modes, one tool.** `copy` (with name sanitization),
  `concatenate` (with file headers), `chunk` (size-bounded output).
- **Dual interface.** A Typer-based CLI with git-style global options
  + an interactive Rich-based TUI.
- **Streaming.** Files are read in 1 MiB chunks — no full-file memory load.
- **Concurrency-safe.** `fcntl.lockf` advisory lock (POSIX) prevents
  two instances from clobbering the same output directory. The lock is
  released when processing finishes and an `atexit` hook releases it on
  a normal interpreter exit. After a hard kill (`SIGKILL`) the kernel
  drops the advisory lock itself, so the next run simply reclaims the
  lock file; on Windows, where `fcntl` does not exist, the
  `O_EXCL` + PID-liveness fallback inspects the leftover lock and
  removes it if its PID is dead.
- **Well covered.** Unit, integration, CLI (CliRunner), TUI (stdin
  mocking) and security-edge test suites.

## AI Disclosure

This project was developed with assistance from artificial intelligence tools. Given the automated nature of some components, users are advised to review and test the code independently before integrating it into their own systems.

## Table of contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Modes](#modes)
- [Command-line reference](#command-line-reference)
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
uv sync --extra dev
```

Fallback (pip; requires `python3-venv` on the system):

```bash
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

Copies files from `--base-dir` to `--output-dir` (defaults to an
in-place sanitized copy). The destination name is rebuilt from the
sanitized base name plus `--output-extension` (`.txt` by default), so
`notes.md` lands as `notes.txt`; on an in-place copy the original file
stays put and the renamed copy is created next to it. Sanitization
replaces control characters, NUL bytes and Unicode spoofing characters
with `_`; prefixes `_` to names starting with `-` and to
Windows-reserved names (`CON`, `NUL`, …); strips trailing dots; and
truncates to 200 characters while keeping the extension. Subdirectory
structure is preserved.

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
iterecho --base-dir ./logs --extensions .log concatenate --output-prefix combined
# -> ./logs/combined.txt   (written to --output-dir, or --base-dir when unset)
```

`--output-file` is resolved under `--output-dir`; paths that escape that
directory are rejected.

### `chunk`

Splits the combined content across multiple files. The size check
compares the running chunk against the next file **plus its per-file
header**, and starts a new chunk when that would pass `--chunk-size` —
so a chunk may end up slightly over the limit. A file larger than
`--chunk-size` is written into a chunk of its own, with a warning.

```bash
iterecho --base-dir ./logs --extensions .log chunk --chunk-size 50M
# -> ./logs/chunk_001.txt, ./logs/chunk_002.txt, ...
```

Chunk names follow `{prefix}_{NNN}{extension}` — `chunk_001.txt` by default
(see `--output-prefix` and `--output-extension` below).

> **Exit status (all modes):** an entry that fails while processing
> (validation or I/O) is logged and skipped — the run continues and still
> exits `0`, so an output can be incomplete without a non-zero status.
> Run-stopping failures exit `1`: existing `concatenate`/`chunk` output
> without `--overwrite`, a locked output directory, or a non-positive
> `--chunk-size`. `copy` never fails on an existing destination — it skips
> it (debug log) unless `--overwrite` is set. Check the log, not just the
> exit code.

## Command-line reference

Global options apply to all subcommands and go **before** the subcommand:

| Option | Default | Description |
| --- | --- | --- |
| `--version` | — | Show version and exit |
| `--extensions` | `.txt` | Comma-separated extensions to include (e.g. `.txt,.log`) |
| `--base-dir` | current dir | Base directory for the file search |
| `--output-dir` | `--base-dir` | Output directory |
| `--output-extension` | `.txt` | Extension for generated output files |
| `--recursive / --no-recursive` | recursive | Search into subdirectories |
| `--name-filter` | none | Substring to match in filenames |
| `--max-file-size` | `100M` | Skip files larger than this (e.g. `100M`, `1G`) |
| `--unsafe` | off | Allow warning-level extensions (`.py`, `.sh`, …) |
| `--overwrite` | off | Overwrite existing output files |
| `--verbose / -v` | off | Enable DEBUG logging |
| `--quiet / -q` | off | Suppress all output except warnings and errors |
| `--dry-run` | off | Show what would be processed without writing |

Subcommand-specific options go **after** the subcommand:

| Subcommand | Option | Default | Description |
| --- | --- | --- | --- |
| `copy` | `--follow-symlinks` | off | Follow symbolic links |
| `concatenate` | `--output-file` | none | Output file name (overrides `--output-prefix`) |
| `concatenate` | `--output-prefix` | `concatenated` | Prefix for the output file name |
| `chunk` | `--chunk-size` | `50M` | Maximum size per chunk (e.g. `10M`, `1G`) |
| `chunk` | `--output-prefix` | `chunk` | Prefix for chunk file names |
| `chunk` | `--follow-symlinks` | off | Follow symbolic links |
| `interactive` | — | — | TUI mode (ignores shared CLI options) |

## Security

IterEcho's security model is documented in detail in [`SECURITY.md`](SECURITY.md).
The short version:

| Threat | Mitigation |
| --- | --- |
| Path traversal via `..` or symlinks | `path.resolve()` + `relative_to(base)` |
| TOCTOU between validation and I/O | `os.open(O_NOFOLLOW)` + `os.fstat` for regular files; symlink targets are resolved and re-validated before opening |
| Symlink-chain escape | Resolved target re-validated against base |
| Race conditions across processes | `fcntl.lockf` advisory lock (POSIX) |
| Filename injection | `sanitize_filename` strips control chars, NULs, BOM, ZWJ |
| Visual spoofing via Unicode | NFC normalization; zero-width / RTL override replaced |
| Executable smuggling | Requested `CRITICAL_EXTENSIONS` (44 entries) are rejected; the filter applies to the searched path's extension |
| Script file processing | Requested `WARNING_EXTENSIONS` are blocked unless `--unsafe` |
| fd leaks on exception | per-entry `try/finally`; chunk files are closed explicitly |
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
    models.py           # SearchConfig, OutputConfig, SecuritySettings, Mode + parse_size/fmt_size
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
uv sync --extra dev
source .venv/bin/activate

# Optional: pre-commit hooks (ruff, ruff-format, black, isort + hygiene checks)
uv run --with pre-commit pre-commit install
```

Fallback without uv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the quality gate locally:

```bash
pre-commit run --all-files          # on a feature branch; on main use SKIP=no-commit-to-branch
uv run --no-sync ruff check iterecho/ tests/        # or just ruff
uv run --no-sync black --check iterecho/ tests/     # or just black
uv run --no-sync mypy iterecho/                      # mypy strict
uv run --no-sync pytest --cov=iterecho --cov-report=term-missing   # full suite
uv build                     # validate sdist + wheel
```

## Tests

```bash
pytest                              # full suite
pytest --collect-only -q | tail -1   # exact test count (never hard-code it)
pytest --cov=iterecho               # with coverage
pytest tests/test_security.py       # single file
pytest -k "symlink"                 # pattern match
```

The test suite is organized by concern:

- `test_security.py` / `test_security_edge.py` / `test_security_paths.py` — security invariants, symlinks, races and path edge cases
- `test_file_utils.py` — `safe_file_copy`, `safe_read_file`
- `test_config.py` — `AppConfig`, `parse_size`, `is_safe_extension`
- `test_search.py` / `test_search_paths.py` — `FileSearcher` and path edge cases
- `test_processing.py` / `test_processing_unit.py` / `test_processing_errors.py` / `test_processing_lock.py` — `FileProcessor`, failures and locking
- `test_logging.py` — logging setup and `ITERECHO_DEBUG`
- `test_main_module.py` — `python -m iterecho`
- `test_integration.py` — end-to-end flows for all three modes
- `test_cli.py` — Typer CliRunner
- `test_tui.py` — Rich TUI via stdin mocking

## Roadmap

- [x] `fcntl`-based lock on POSIX (`O_EXCL` + PID liveness kept as the Windows fallback)
- [x] `--version` works without a subcommand
- [x] Per-extension blocklist regression tests (parametrized)
- [x] Symlink-in-parent regression tests
- [x] Bandit + pip-audit in CI
- [x] Pre-commit hooks
- [ ] Watch mode (continuous processing on file changes)
- [ ] Pluggable transformers (gzip, encrypt)
- [ ] Optional `nox` matrix for local cross-version testing

## Supported Python versions

3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14 — tested on every push to `main` and on every pull request via GitHub Actions.

## Contributing

IterEcho is maintained by a single owner; external pull requests are not
being accepted at this time. Bug reports are welcome via GitHub Issues.
Security reports must follow [`SECURITY.md`](SECURITY.md) and must not be
opened as public issues.

## License

MIT © morphilab. See [`LICENSE`](LICENSE).
