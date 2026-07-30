"""Short PostgreSQL transactions for ingestion claims and raw evidence.

Functions in this module deliberately neither commit nor roll back.  The caller
owns the transaction boundary, allowing a claim to commit before any network
request and an evidence write to commit independently afterwards.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from .contracts import JsonContainer
from .raw_storage import RawStorageDecision, StorageProvider

_LOWERCASE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STORAGE_PROVIDERS = frozenset(
    {
        "inline",
        "supabase_storage",
        "filesystem",
        "s3_compatible",
        "github_artifact",
        "other",
    }
)

_CLAIM_DUE_TASK_SQL = sa.text(
    """
    WITH candidate AS (
        SELECT task.id
        FROM ingestion.crawl_tasks AS task
        JOIN ingestion.crawl_runs AS run ON run.id = task.crawl_run_id
        WHERE task.crawl_run_id = :run_id
          AND run.status = 'running'
          AND task.source_id = run.source_id
          AND task.status = 'pending'
          AND task.attempt_count < task.max_attempts
          AND (task.scheduled_for IS NULL OR task.scheduled_for <= now())
        ORDER BY task.priority DESC, task.id
        FOR UPDATE OF task SKIP LOCKED
        LIMIT 1
    )
    UPDATE ingestion.crawl_tasks AS task
    SET status = 'running',
        attempt_count = task.attempt_count + 1,
        scheduled_for = NULL,
        started_at = now(),
        finished_at = NULL,
        updated_at = now()
    FROM candidate
    WHERE task.id = candidate.id
    RETURNING task.*
    """
)

_UPSERT_RAW_OBJECT_SQL = (
    sa.text(
        """
        INSERT INTO ingestion.raw_objects (
            sha256,
            storage_provider,
            bucket_name,
            object_key,
            inline_payload_json,
            compression,
            mime_type,
            byte_size,
            redaction_status,
            retention_policy_id,
            expires_at
        ) VALUES (
            :sha256,
            :storage_provider,
            :bucket_name,
            :object_key,
            :inline_payload_json,
            :compression,
            :mime_type,
            :byte_size,
            :redaction_status,
            :retention_policy_id,
            :expires_at
        )
        ON CONFLICT (sha256) DO UPDATE
        SET sha256 = ingestion.raw_objects.sha256
        WHERE ingestion.raw_objects.byte_size = EXCLUDED.byte_size
        RETURNING ingestion.raw_objects.id
        """
    )
    .bindparams(sa.bindparam("inline_payload_json", type_=JSONB))
    .columns(id=sa.BigInteger())
)


def claim_due_task(connection: sa.Connection, run_id: UUID) -> sa.Row[Any] | None:
    """Atomically claim one due task using ``FOR UPDATE SKIP LOCKED``.

    Only tasks belonging to a running crawl run are eligible.  Exhausted tasks
    remain untouched, and the attempt number is incremented in the same
    statement that marks the task running.
    """

    return connection.execute(_CLAIM_DUE_TASK_SQL, {"run_id": run_id}).first()


def _validate_raw_object_values(
    *,
    sha256: str,
    byte_size: int,
    storage_provider: str,
    bucket_name: str | None,
    object_key: str | None,
    inline_payload_json: JsonContainer | None,
) -> None:
    if _LOWERCASE_SHA256.fullmatch(sha256) is None:
        raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters")
    if byte_size < 0:
        raise ValueError("byte_size must not be negative")
    if storage_provider not in _STORAGE_PROVIDERS:
        raise ValueError(f"unsupported storage_provider: {storage_provider}")
    if storage_provider == "inline":
        if inline_payload_json is None:
            raise ValueError("inline storage requires inline_payload_json")
        if bucket_name is not None or object_key is not None:
            raise ValueError("inline storage cannot include a bucket or object key")
    else:
        if object_key is None:
            raise ValueError("non-inline storage requires object_key")
        if inline_payload_json is not None:
            raise ValueError("non-inline storage cannot include inline_payload_json")


def upsert_raw_object(
    connection: sa.Connection,
    sha256: str,
    byte_size: int,
    object_key: str | None,
    expires_at: datetime | None,
    *,
    storage_provider: StorageProvider = "filesystem",
    bucket_name: str | None = None,
    inline_payload_json: JsonContainer | None = None,
    compression: str = "none",
    mime_type: str | None = None,
    redaction_status: str = "not_required",
    retention_policy_id: UUID | None = None,
) -> int:
    """Insert immutable raw metadata or return its globally deduplicated ID.

    The conflict action is intentionally a no-op: the first storage decision
    remains immutable.  Its ``WHERE`` clause also prevents a same-hash,
    different-size value from being silently accepted.
    """

    _validate_raw_object_values(
        sha256=sha256,
        byte_size=byte_size,
        storage_provider=storage_provider,
        bucket_name=bucket_name,
        object_key=object_key,
        inline_payload_json=inline_payload_json,
    )
    if compression not in {"none", "gzip", "zstd", "zip", "other"}:
        raise ValueError(f"unsupported compression: {compression}")
    if redaction_status not in {"not_required", "pending", "redacted", "failed"}:
        raise ValueError(f"unsupported redaction_status: {redaction_status}")

    raw_object_id = connection.execute(
        _UPSERT_RAW_OBJECT_SQL,
        {
            "sha256": sha256,
            "storage_provider": storage_provider,
            "bucket_name": bucket_name,
            "object_key": object_key,
            "inline_payload_json": inline_payload_json,
            "compression": compression,
            "mime_type": mime_type,
            "byte_size": byte_size,
            "redaction_status": redaction_status,
            "retention_policy_id": retention_policy_id,
            "expires_at": expires_at,
        },
    ).scalar_one_or_none()
    if raw_object_id is None:
        raise ValueError("an existing raw object has the same SHA-256 but a different byte size")
    return int(raw_object_id)


def upsert_raw_storage_decision(
    connection: sa.Connection,
    decision: RawStorageDecision,
    *,
    compression: str = "none",
    redaction_status: str = "not_required",
    retention_policy_id: UUID | None = None,
) -> int | None:
    """Persist a storage decision, or return ``None`` for suppressed evidence."""

    if decision.storage_provider is None:
        return None
    return upsert_raw_object(
        connection,
        sha256=decision.sha256,
        byte_size=decision.byte_size,
        object_key=decision.object_key,
        expires_at=decision.expires_at,
        storage_provider=decision.storage_provider,
        bucket_name=decision.bucket_name,
        inline_payload_json=decision.inline_payload_json,
        compression=compression,
        mime_type=decision.mime_type,
        redaction_status=redaction_status,
        retention_policy_id=retention_policy_id,
    )
