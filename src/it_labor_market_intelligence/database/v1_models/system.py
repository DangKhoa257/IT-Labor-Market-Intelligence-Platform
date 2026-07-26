"""Database V1 models in the private ``system`` schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import V1Base

UUID_PK = PGUUID(as_uuid=True)


class PipelineVersion(V1Base):
    __tablename__ = "pipeline_versions"
    __table_args__ = (
        sa.UniqueConstraint("component", "version", name="uq_pipeline_versions__component_version"),
        {"schema": "system"},
    )
    id: Mapped[UUID] = mapped_column(
        UUID_PK, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    component: Mapped[str] = mapped_column(sa.String(50))
    version: Mapped[str] = mapped_column(sa.String(100))
    git_commit_sha: Mapped[str | None] = mapped_column(sa.String(64))
    configuration_hash: Mapped[str | None] = mapped_column(sa.String(128))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    released_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class RetentionPolicy(V1Base):
    __tablename__ = "retention_policies"
    __table_args__ = {"schema": "system"}
    id: Mapped[UUID] = mapped_column(
        UUID_PK, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="CASCADE")
    )
    data_class: Mapped[str] = mapped_column(sa.String(50))
    retention_days: Mapped[int | None]
    action: Mapped[str] = mapped_column(sa.String(30), server_default="delete")
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    policy_version: Mapped[str] = mapped_column(sa.String(100))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class BackgroundJob(V1Base):
    __tablename__ = "background_jobs"
    __table_args__ = {"schema": "system"}
    id: Mapped[UUID] = mapped_column(
        UUID_PK, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    job_name: Mapped[str] = mapped_column(sa.String(150))
    job_type: Mapped[str] = mapped_column(sa.String(50))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    scheduled_for: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(server_default="0")
    max_attempts: Mapped[int] = mapped_column(server_default="1")
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class AuditEvent(V1Base):
    __tablename__ = "audit_events"
    __table_args__ = {"schema": "system"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    actor_type: Mapped[str] = mapped_column(sa.String(30))
    actor_id: Mapped[str | None] = mapped_column(sa.String(255))
    action: Mapped[str] = mapped_column(sa.String(100))
    entity_schema: Mapped[str | None] = mapped_column(sa.String(63))
    entity_table: Mapped[str | None] = mapped_column(sa.String(63))
    entity_id: Mapped[str | None] = mapped_column(sa.String(255))
    request_id: Mapped[str | None] = mapped_column(sa.String(100))
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
