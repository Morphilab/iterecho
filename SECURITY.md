# Security Policy

## Supported versions

| Version | Supported           |
| ------- | ------------------- |
| 1.0.x   | :white_check_mark:  |
| < 1.0   | :x:                 |

Only the latest minor release receives security fixes. Please upgrade
before reporting an issue against an older version.

## Reporting a vulnerability

**Please do not open a public GitHub Issue for security vulnerabilities.**

Send a private report to **lab@morphilab.com** with:

1. A clear description of the vulnerability and its impact.
2. Steps to reproduce, ideally with a minimal test case.
3. The IterEcho version (`iterecho --version`) and Python version.
4. The operating system and filesystem (some issues are FS-specific).
5. Whether you intend to disclose publicly (we will coordinate timing).

### What to expect

- **Initial acknowledgement** within 72 hours.
- **Triage and impact assessment** within 7 days.
- **Patch** for critical issues within 30 days; medium/low within 90 days.
- **Coordinated disclosure** with a CVE if the impact is significant.
- **Credit** in the CHANGELOG and release notes (unless you prefer anonymity).

## Security model

IterEcho is a local CLI tool. The threat model is:

| Threat | Mitigation |
| --- | --- |
| Path traversal via `..` or symlinks | `path.resolve()` + `relative_to(base)` check in `SecurityEngine.is_within_base` |
| TOCTOU between validation and I/O | `os.open(O_NOFOLLOW)` + `os.fstat` on the open fd; no stat-then-use |
| Symlink-chain escape | Resolved target re-validated against base; intermediate symlinks unwound |
| Race conditions across processes | `fcntl.lockf` advisory lock on a 0o600 file (POSIX); O_EXCL + PID liveness (Windows) |
| Information disclosure via lock file | Lock file created with 0o600 permissions |
| Filename injection (`/`, `\0`, Windows reserved names) | `sanitize_filename` strips control chars, NULs, BOM, ZWJ; prefixes `_` to names starting with `-` and to Windows reserved names; truncates to 200 chars |
| Visual spoofing via Unicode normalization | NFC normalization; zero-width / RTL override characters replaced with `_` |
| Executable smuggling | `CRITICAL_EXTENSIONS` blocklist (44 entries) — always blocked, even with `--unsafe` |
| Script file processing | `WARNING_EXTENSIONS` (`.py`, `.sh`, `.js`, etc.) blocked by default; require `--unsafe` opt-in |
| fd leaks on exception | per-entry try/finally closes the validation fd; chunk files scoped to per-block context managers |
| Concurrency corruption | per-output-dir advisory lock + atexit cleanup |

## Out of scope

- Vulnerabilities in `tqdm` or `typer[all]` (report upstream).
- Bugs in the Python standard library.
- Issues that require local code execution by the user (this is a CLI;
  if the attacker already runs code as you, the game is over).

## Hall of fame

We thank the following reporters (none yet — be the first!).

---

_Last updated: IterEcho v1.0.1_
