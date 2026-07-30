"""Policy-aware decisions for immutable raw ingestion evidence.

This module only decides how raw evidence may be represented in Database V1.
It never writes response bodies to disk or provisions object storage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Literal

from .contracts import JsonContainer
from .hashing import raw_bytes_sha256

INLINE_JSON_MAX_BYTES = 256 * 1024

StorageProvider = Literal[
    "inline",
    "supabase_storage",
    "filesystem",
    "s3_compatible",
    "github_artifact",
    "other",
]
StorageReason = Literal[
    "fixture_reference",
    "inline_json",
    "policy_disallowed",
    "object_storage_unavailable",
    "not_structured_json",
    "payload_too_large",
]


@dataclass(frozen=True, slots=True)
class RawStorageDecision:
    """A complete, auditable raw-storage decision for one exact body."""

    sha256: str
    byte_size: int
    storage_provider: StorageProvider | None
    object_key: str | None
    expires_at: datetime | None
    inline_payload_json: JsonContainer | None = None
    bucket_name: str | None = None
    mime_type: str | None = None
    reason: StorageReason = "fixture_reference"

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("raw SHA-256 must be 64 lowercase hexadecimal characters")
        if self.byte_size < 0:
            raise ValueError("raw byte size must not be negative")

        if self.storage_provider is None:
            if self.object_key is not None or self.inline_payload_json is not None:
                raise ValueError("suppressed raw evidence cannot include a storage location")
            if self.bucket_name is not None:
                raise ValueError("suppressed raw evidence cannot include a bucket")
            return

        if self.storage_provider == "inline":
            if self.inline_payload_json is None:
                raise ValueError("inline raw evidence requires a JSON payload")
            if self.object_key is not None or self.bucket_name is not None:
                raise ValueError("inline raw evidence cannot include an object location")
        elif self.object_key is None:
            raise ValueError("non-inline raw evidence requires an object key")
        elif self.inline_payload_json is not None:
            raise ValueError("non-inline raw evidence cannot include inline JSON")

    @property
    def should_persist(self) -> bool:
        """Whether this decision can create or reference a ``raw_objects`` row."""

        return self.storage_provider is not None


def _validate_timestamp_and_retention(
    fetched_at: datetime, retention_days: int | None
) -> datetime | None:
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")
    if retention_days is not None and retention_days < 0:
        raise ValueError("retention_days must not be negative")
    return fetched_at + timedelta(days=retention_days) if retention_days is not None else None


def _repository_fixture_key(fixture_key: str) -> str:
    normalized = fixture_key.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or normalized.endswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in normalized
    ):
        raise ValueError("fixture raw object key must be a repository-relative file identifier")
    return path.as_posix()


def fixture_raw_decision(
    body: bytes,
    fixture_key: str,
    fetched_at: datetime,
    retention_days: int | None,
    *,
    mime_type: str | None = None,
) -> RawStorageDecision:
    """Reference fixture bytes without copying HTML into JSONB or another file."""

    expires_at = _validate_timestamp_and_retention(fetched_at, retention_days)
    return RawStorageDecision(
        sha256=raw_bytes_sha256(body),
        byte_size=len(body),
        # Database V1 has no ``fixture`` provider vocabulary.  ``filesystem``
        # plus a repository-relative identifier represents an existing fixture
        # without persisting an absolute host path.
        storage_provider="filesystem",
        object_key=_repository_fixture_key(fixture_key),
        expires_at=expires_at,
        mime_type=mime_type,
        reason="fixture_reference",
    )


def inline_json_raw_decision(
    body: bytes,
    fetched_at: datetime,
    retention_days: int | None,
    *,
    allow_raw_storage: bool,
    mime_type: str | None = "application/json",
) -> RawStorageDecision:
    """Store small structured JSON inline when policy and size permit it.

    The hash and size always describe the original bytes, not the parsed JSON
    representation.  Invalid JSON and scalar JSON values are not treated as
    structured evidence.
    """

    expires_at = _validate_timestamp_and_retention(fetched_at, retention_days)
    sha256 = raw_bytes_sha256(body)

    def suppressed(reason: StorageReason) -> RawStorageDecision:
        return RawStorageDecision(
            sha256=sha256,
            byte_size=len(body),
            storage_provider=None,
            object_key=None,
            expires_at=expires_at,
            mime_type=mime_type,
            reason=reason,
        )

    if not allow_raw_storage:
        return suppressed("policy_disallowed")
    if len(body) > INLINE_JSON_MAX_BYTES:
        return suppressed("payload_too_large")

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return suppressed("not_structured_json")
    if not isinstance(payload, (dict, list)):
        return suppressed("not_structured_json")

    return RawStorageDecision(
        sha256=sha256,
        byte_size=len(body),
        storage_provider="inline",
        object_key=None,
        expires_at=expires_at,
        inline_payload_json=payload,
        mime_type=mime_type,
        reason="inline_json",
    )


def suppressed_raw_decision(
    body: bytes,
    fetched_at: datetime,
    retention_days: int | None,
    *,
    policy_allows_storage: bool,
    mime_type: str | None = None,
) -> RawStorageDecision:
    """Describe in-memory processing when no safe raw storage is available."""

    expires_at = _validate_timestamp_and_retention(fetched_at, retention_days)
    return RawStorageDecision(
        sha256=raw_bytes_sha256(body),
        byte_size=len(body),
        storage_provider=None,
        object_key=None,
        expires_at=expires_at,
        mime_type=mime_type,
        reason="object_storage_unavailable" if policy_allows_storage else "policy_disallowed",
    )
