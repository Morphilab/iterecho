# Changelog

All notable changes to IterEcho are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
