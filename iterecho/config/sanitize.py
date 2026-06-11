from __future__ import annotations

import re
import unicodedata
from pathlib import Path

CRITICAL_EXTENSIONS = {
    ".ade",
    ".adp",
    ".apk",
    ".app",
    ".appx",
    ".appxbundle",
    ".bat",
    ".cab",
    ".cmd",
    ".com",
    ".cpl",
    ".dll",
    ".dmg",
    ".exe",
    ".hta",
    ".ins",
    ".isp",
    ".iso",
    ".jar",
    ".jse",
    ".lib",
    ".lnk",
    ".mde",
    ".msc",
    ".msi",
    ".msix",
    ".msixbundle",
    ".msp",
    ".mst",
    ".nsh",
    ".pif",
    ".ps1",
    ".scr",
    ".sct",
    ".shb",
    ".so",
    ".sys",
    ".vb",
    ".vbe",
    ".vbs",
    ".vxd",
    ".wsc",
    ".wsf",
    ".wsh",
}

WARNING_EXTENSIONS = {
    ".sh",
    ".py",
    ".php",
    ".js",
    ".rb",
    ".pl",
    ".cgi",
    ".bin",
    ".run",
}


def is_safe_extension(extension: str, unsafe_mode: bool = False) -> bool:
    if not extension.startswith("."):
        return False
    ext = extension.lower()
    if ext in CRITICAL_EXTENSIONS:
        return False
    if not unsafe_mode and ext in WARNING_EXTENSIONS:
        return False
    return True


RESERVED_WINDOWS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Unicode control / formatting characters that should never appear in a filename
_UNSAFE_UNICODE = (
    "\u200b-\u200f"  # zero-width space, ZWJ, LRM, RLM
    "\u2028-\u202f"  # line/paragraph separator, LRO, RLO, etc.
    "\u2060-\u206f"  # word joiner, invisible operators
    "\ufeff"  # BOM / zero-width no-break space
)


def sanitize_filename(name: str) -> str:
    # 1. Strip ASCII and Unicode control characters
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f' + _UNSAFE_UNICODE + r"]", "_", name)

    # 2. Normalise to NFC (prevents visual spoofing via decomposed forms)
    safe = unicodedata.normalize("NFC", safe)

    # 3. Collapse whitespace runs
    safe = re.sub(r"\s+", "_", safe)

    # 3b. Prefix with underscore if name starts with '-' (shell safety)
    if safe.startswith("-"):
        safe = "_" + safe

    # 4. Check for Windows reserved names (CON, NUL, etc.)
    # We check the stem (filename without extension) because Windows reserves names
    # regardless of extension (e.g., CON.txt is still problematic)
    # For hidden files like .NUL.txt, we need to check the stem without the leading dot
    stem_for_check = Path(safe).stem.upper()  # Get stem and uppercase for comparison
    # Remove any leading dots from the stem for reserved name checking
    stem_for_reserved_check = stem_for_check.lstrip(".")
    if stem_for_reserved_check in RESERVED_WINDOWS:
        # Prepend underscore, but if the name starts with dot, replace the dot with underscore
        if safe.startswith("."):
            safe = "_" + safe[1:]
        else:
            safe = "_" + safe

    # 5. Strip trailing dots (Windows/macOS special meaning)
    safe = safe.rstrip(".")

    # 6. Truncate to 200 characters, preserving extension
    max_len = 200
    if len(safe) > max_len:
        stem_part, dot, ext_part = safe.rpartition(".")
        if ext_part:  # Has extension
            # Reserve space for dot and extension
            max_stem_len = max_len - len(dot) - len(ext_part)
            if max_stem_len > 0:
                stem_part = stem_part[:max_stem_len]
                safe = f"{stem_part}{dot}{ext_part}"
            else:
                # Extension too long, truncate to max_len anyway
                safe = safe[:max_len]
        else:  # No extension
            safe = safe[:max_len]

    # 7. Fallback for empty result
    if not safe:
        safe = "unnamed_file"

    return safe
