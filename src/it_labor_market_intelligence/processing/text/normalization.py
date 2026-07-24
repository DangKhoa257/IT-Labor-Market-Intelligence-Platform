"""Unicode-safe display normalization and accent-insensitive matching keys."""

from __future__ import annotations

import re
import unicodedata

_PUNCTUATION = str.maketrans(
    {"\u2013": "-", "\u2014": "-", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
)
_NON_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFC", value).translate(_PUNCTUATION)
    return " ".join(normalized.split()) or None


def normalize_display(value: str | None) -> str | None:
    """Return readable normalized text without removing Vietnamese accents."""
    return normalize_whitespace(value)


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return without_marks.replace("\u0111", "d").replace("\u0110", "D")


def comparison_key(value: str | None) -> str | None:
    """Stable case-folded, accent-insensitive key for matching only."""
    display = normalize_whitespace(value)
    if display is None:
        return None
    key = _strip_accents(display).casefold()
    return _NON_TOKEN.sub(" ", key).strip() or None


def tokenize(value: str | None) -> tuple[str, ...]:
    key = comparison_key(value)
    return tuple(token for token in (key or "").split() if token)
