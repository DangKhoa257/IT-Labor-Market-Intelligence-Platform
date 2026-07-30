"""Stable hashes used for immutable ingestion evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any


def raw_bytes_sha256(body: bytes) -> str:
    """Return the lowercase SHA-256 of the exact response bytes."""
    return hashlib.sha256(body).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("direct payload datetimes must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"unsupported direct payload value: {type(value)!r}")


def direct_payload_sha256(payload: dict[str, Any]) -> str:
    """Hash canonical direct-payload-json.v1 bytes while preserving list order."""
    encoded = json.dumps(
        payload, default=_json_default, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return raw_bytes_sha256(encoded)
