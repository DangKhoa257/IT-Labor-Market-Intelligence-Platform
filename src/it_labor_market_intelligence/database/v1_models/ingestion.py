"""Database V1 models in the private ``ingestion`` schema."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import V1Base


def uuid_pk() -> sa.types.TypeEngine[UUID]:
    return PGUUID(as_uuid=True)


class Source(V1Base):
    __tablename__ = "sources"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[UUID] = mapped_column(
        uuid_pk(), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(sa.String(100), unique=True)
    display_name: Mapped[str] = mapped_column(sa.String(255))
    base_url: Mapped[str] = mapped_column(sa.Text)
    source_type: Mapped[str] = mapped_column(sa.String(50), server_default="job_board")
    country_code: Mapped[str | None] = mapped_column(sa.CHAR(2))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="researching")
    is_enabled: Mapped[bool] = mapped_column(server_default=sa.false())
    owner_contact: Mapped[str | None] = mapped_column(sa.String(255))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class SourcePolicy(V1Base):
    __tablename__ = "source_policies"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[UUID] = mapped_column(
        uuid_pk(), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="CASCADE")
    )
    policy_version: Mapped[str] = mapped_column(sa.String(100))
    robots_review_status: Mapped[str] = mapped_column(sa.String(30), server_default="not_reviewed")
    terms_review_status: Mapped[str] = mapped_column(sa.String(30), server_default="not_reviewed")
    approved_paths: Mapped[list[Any]] = mapped_column(JSONB, server_default=sa.text("'[]'::jsonb"))
    blocked_paths: Mapped[list[Any]] = mapped_column(JSONB, server_default=sa.text("'[]'::jsonb"))
    minimum_request_interval_seconds: Mapped[Decimal] = mapped_column(
        sa.Numeric(10, 3), server_default="2.000"
    )
    maximum_requests_per_run: Mapped[int] = mapped_column(server_default="30")
    maximum_concurrent_requests: Mapped[int] = mapped_column(server_default="1")
    raw_retention_days: Mapped[int | None] = mapped_column(server_default="30")
    description_retention_days: Mapped[int | None] = mapped_column(server_default="90")
    allow_raw_storage: Mapped[bool] = mapped_column(server_default=sa.true())
    allow_description_storage: Mapped[bool] = mapped_column(server_default=sa.true())
    notes: Mapped[str | None] = mapped_column(sa.Text)
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_from: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ParserVersion(V1Base):
    __tablename__ = "parser_versions"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[UUID] = mapped_column(
        uuid_pk(), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="CASCADE")
    )
    pipeline_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("system.pipeline_versions.id", ondelete="SET NULL")
    )
    parser_name: Mapped[str] = mapped_column(sa.String(150))
    version: Mapped[str] = mapped_column(sa.String(100))
    schema_version: Mapped[str] = mapped_column(sa.String(100))
    git_commit_sha: Mapped[str | None] = mapped_column(sa.String(64))
    configuration_hash: Mapped[str | None] = mapped_column(sa.String(128))
    is_active: Mapped[bool] = mapped_column(server_default=sa.false())
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    retired_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class CrawlRun(V1Base):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        sa.UniqueConstraint("id", "source_id", name="uq_crawl_runs__id_source_id"),
        {"schema": "ingestion"},
    )
    id: Mapped[UUID] = mapped_column(
        uuid_pk(), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    source_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.source_policies.id", ondelete="SET NULL")
    )
    parser_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.parser_versions.id", ondelete="SET NULL")
    )
    pipeline_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("system.pipeline_versions.id", ondelete="SET NULL")
    )
    run_type: Mapped[str] = mapped_column(sa.String(30), server_default="scheduled")
    trigger_type: Mapped[str] = mapped_column(sa.String(30), server_default="manual")
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    requested_limit: Mapped[int | None]
    configuration_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    git_commit_sha: Mapped[str | None] = mapped_column(sa.String(64))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    discovered_count: Mapped[int] = mapped_column(server_default="0")
    task_count: Mapped[int] = mapped_column(server_default="0")
    fetch_success_count: Mapped[int] = mapped_column(server_default="0")
    fetch_failure_count: Mapped[int] = mapped_column(server_default="0")
    unchanged_count: Mapped[int] = mapped_column(server_default="0")
    extracted_count: Mapped[int] = mapped_column(server_default="0")
    accepted_count: Mapped[int] = mapped_column(server_default="0")
    rejected_count: Mapped[int] = mapped_column(server_default="0")
    error_count: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class CrawlTask(V1Base):
    __tablename__ = "crawl_tasks"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    crawl_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    task_type: Mapped[str] = mapped_column(sa.String(30))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    priority: Mapped[int] = mapped_column(sa.SmallInteger, server_default="0")
    source_job_id: Mapped[str | None] = mapped_column(sa.String(255))
    requested_url: Mapped[str | None] = mapped_column(sa.Text)
    discovery_method: Mapped[str | None] = mapped_column(sa.String(150))
    attempt_count: Mapped[int] = mapped_column(server_default="0")
    max_attempts: Mapped[int] = mapped_column(server_default="1")
    scheduled_for: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    task_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class RawObject(V1Base):
    __tablename__ = "raw_objects"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    sha256: Mapped[str] = mapped_column(sa.CHAR(64), unique=True)
    storage_provider: Mapped[str] = mapped_column(sa.String(30))
    bucket_name: Mapped[str | None] = mapped_column(sa.String(255))
    object_key: Mapped[str | None] = mapped_column(sa.Text)
    inline_payload_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB)
    compression: Mapped[str] = mapped_column(sa.String(20), server_default="none")
    mime_type: Mapped[str | None] = mapped_column(sa.String(255))
    byte_size: Mapped[int] = mapped_column(sa.BigInteger)
    redaction_status: Mapped[str] = mapped_column(sa.String(30), server_default="not_required")
    retention_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("system.retention_policies.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class FetchEvent(V1Base):
    __tablename__ = "fetch_events"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    crawl_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="CASCADE")
    )
    crawl_task_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.crawl_tasks.id", ondelete="SET NULL")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    raw_object_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.raw_objects.id", ondelete="SET NULL")
    )
    requested_url: Mapped[str] = mapped_column(sa.Text)
    resolved_url: Mapped[str | None] = mapped_column(sa.Text)
    http_method: Mapped[str] = mapped_column(sa.String(10), server_default="GET")
    http_status: Mapped[int | None] = mapped_column(sa.SmallInteger)
    content_type: Mapped[str | None] = mapped_column(sa.String(255))
    response_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    duration_ms: Mapped[int | None]
    attempt_number: Mapped[int] = mapped_column(server_default="1")
    robots_allowed: Mapped[bool | None]
    fetch_outcome: Mapped[str] = mapped_column(sa.String(30))
    etag: Mapped[str | None] = mapped_column(sa.Text)
    last_modified: Mapped[str | None] = mapped_column(sa.Text)
    request_headers_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    response_headers_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    fetched_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ExtractionRun(V1Base):
    __tablename__ = "extraction_runs"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    crawl_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="SET NULL")
    )
    fetch_event_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.fetch_events.id", ondelete="CASCADE")
    )
    raw_object_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.raw_objects.id", ondelete="SET NULL")
    )
    parser_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.parser_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    record_count: Mapped[int] = mapped_column(server_default="0")
    warning_count: Mapped[int] = mapped_column(server_default="0")
    error_count: Mapped[int] = mapped_column(server_default="0")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ExtractedRecord(V1Base):
    __tablename__ = "extracted_records"
    __table_args__ = (
        sa.UniqueConstraint(
            "id",
            "source_id",
            "source_job_id",
            name="uq_extracted_records__id_source_identity",
        ),
        sa.UniqueConstraint("id", "source_id", name="uq_extracted_records__id_source_id"),
        {"schema": "ingestion"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    extraction_run_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.extraction_runs.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    source_job_id: Mapped[str] = mapped_column(sa.String(255))
    fetch_event_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.fetch_events.id", ondelete="CASCADE")
    )
    raw_object_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.raw_objects.id", ondelete="SET NULL")
    )
    record_schema_version: Mapped[str] = mapped_column(sa.String(100))
    direct_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    direct_hash: Mapped[str] = mapped_column(sa.CHAR(64))
    processing_status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text)
    extracted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class CrawlError(V1Base):
    __tablename__ = "crawl_errors"
    __table_args__ = {"schema": "ingestion"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    crawl_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="CASCADE")
    )
    crawl_task_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.crawl_tasks.id", ondelete="SET NULL")
    )
    fetch_event_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.fetch_events.id", ondelete="SET NULL")
    )
    extraction_run_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.extraction_runs.id", ondelete="SET NULL")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    stage: Mapped[str] = mapped_column(sa.String(30))
    category: Mapped[str] = mapped_column(sa.String(50))
    error_code: Mapped[str | None] = mapped_column(sa.String(150))
    retryable: Mapped[bool] = mapped_column(server_default=sa.false())
    severity: Mapped[str] = mapped_column(sa.String(20), server_default="error")
    source_job_id: Mapped[str | None] = mapped_column(sa.String(255))
    url: Mapped[str | None] = mapped_column(sa.Text)
    http_status: Mapped[int | None] = mapped_column(sa.SmallInteger)
    sanitized_message: Mapped[str] = mapped_column(sa.Text)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
