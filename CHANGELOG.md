# Changelog

All notable changes to IterEcho are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Fixed

- Build: declared `dynamic = ["version"]` so hatchling actually reads the
  version from `__version__` in `iterecho/__init__.py`. The
  `[tool.hatch.version]` config was inert next to the static `version`
  field, making `pyproject.toml` the de facto source and risking silently
  shipping a stale version on a `__version__`-only bump.

### Changed

- Documentation accuracy pass verified against code: corrected the lock
  release/`atexit` claim in `README.md`, the `sanitize_filename` prefixing
  description in `SECURITY.md`, and the lock-scope description (in-place
  `copy` does not lock) in `CONTRIBUTING.md`.

## [1.0.1] - 2026-09-07

### Changed

- Comment hygiene pass: removed or reworded comments that restated the code,
  were misleading, or justified production behavior via internal test
  expectations. No behavior changes.
- Documentation accuracy pass: corrected `chunk` output example, documented
  all CLI options in a command-line reference, fixed `config/` module layout
  description.

## [1.0.0] - 2026-06-11

### Added

- Initial release: `copy`, `concatenate`, `chunk` and `interactive` modes
  with security-first file handling (`O_NOFOLLOW` + `fstat`, path-traversal
  checks, extension blocklists, filename sanitization) and a concurrency
  lock for output directories.
