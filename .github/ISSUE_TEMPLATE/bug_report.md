---
name: Bug report
about: Report incorrect behavior or an unexpected error
title: "[bug] "
labels: bug
assignees: ""
---

## Describe the bug

A clear and concise description of what the bug is.

## To reproduce

```bash
# Minimal command that triggers the issue
iterecho --base-dir ./test --extensions .txt copy
```

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. Include the full error message and stack trace
(if any) verbatim.

## Environment

- IterEcho version: (`iterecho --version`)
- Python version: (`python3 --version`)
- OS: (e.g. Ubuntu 24.04, macOS 15, Windows 11)
- Filesystem: (e.g. ext4, APFS, NTFS — some issues are FS-specific)
- Installation method: (e.g. `pip install -e .[dev]`, Homebrew, pipx)

## Files

If the bug involves specific input files, attach or describe them
(use a small example — never paste sensitive data).

## Additional context

Any other relevant information, workarounds, or related issues.
