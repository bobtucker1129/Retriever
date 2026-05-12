"""Same-origin path safety for rendering broker-supplied URLs in Fetch HTML."""

from __future__ import annotations

from typing import Optional


def _has_ascii_control_char(text: str) -> bool:
    """True if *text* contains C0 controls (U+0000–U+001F) or ASCII DEL (U+007F)."""
    return any(ord(ch) < 32 or ch == "\x7f" for ch in text)


def safe_fetch_download_href(raw: object) -> Optional[str]:
    """Return a path safe to place in ``href`` (leading ``/``, same origin), or ``None``."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s.startswith("/") or s.startswith("//"):
        return None
    if len(s) > 2048:
        return None
    if _has_ascii_control_char(s):
        return None
    if "\\" in s:
        return None
    if ".." in s:
        return None
    return s
