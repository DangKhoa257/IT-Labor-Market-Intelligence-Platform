"""Secret-safe persistence and logging helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping

_ALLOWED_HEADERS = {
    "user-agent",
    "accept",
    "accept-language",
    "if-none-match",
    "if-modified-since",
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "cache-control",
    "retry-after",
    "date",
}
_SECRET = re.compile(
    r"(?is)(postgres(?:ql)?://\S+|authorization\s*[:=]\s*\S+|cookie\s*[:=]\s*\S+|(?:token|secret|password|api[_-]?key)\s*[:=]\s*\S+|(?:body|raw[_-]?body|response[_-]?body)\s*[:=]\s*.*)"
)


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.casefold() in _ALLOWED_HEADERS}


def sanitize_error(message: str, limit: int = 2000) -> str:
    return _SECRET.sub("[redacted]", message).replace("\n", " ")[:limit]
