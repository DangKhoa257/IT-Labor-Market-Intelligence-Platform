"""Database V1 models in the private ``quality`` schema."""

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


class ValidationRun(V1Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("crawl_run_id", "source_id"),
            ("ingestion.crawl_runs.id", "ingestion.crawl_runs.source_id"),
            name="fk_validation_runs__crawl_source_identity__crawl_runs",
        ),
        {"schema": "quality"},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    crawl_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="SET NULL")
    )
    pipeline_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("system.pipeline_versions.id", ondelete="SET NULL")
    )
    scope_type: Mapped[str] = mapped_column(sa.String(30))
    ruleset_version: Mapped[str] = mapped_column(sa.String(100))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    records_checked_count: Mapped[int] = mapped_column(server_default="0")
    issues_found_count: Mapped[int] = mapped_column(server_default="0")
    critical_issue_count: Mapped[int] = mapped_column(server_default="0")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DataQualityIssue(V1Base):
    __tablename__ = "data_quality_issues"
    __table_args__ = (
        sa.UniqueConstraint(
            "validation_run_id", "fingerprint", name="uq_data_quality_issues__run_fingerprint"
        ),
        sa.ForeignKeyConstraint(
            ("observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_data_quality_issues__observation_job__job_observations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("crawl_run_id", "source_id"),
            ("ingestion.crawl_runs.id", "ingestion.crawl_runs.source_id"),
            name="fk_data_quality_issues__crawl_source_identity__crawl_runs",
        ),
        sa.ForeignKeyConstraint(
            ("extracted_record_id", "source_id"),
            ("ingestion.extracted_records.id", "ingestion.extracted_records.source_id"),
            name="fk_data_quality_issues__extracted_source__extracted_records",
        ),
        sa.ForeignKeyConstraint(
            ("job_posting_id", "source_id"),
            ("core.job_postings.id", "core.job_postings.source_id"),
            name="fk_data_quality_issues__job_source_identity__job_postings",
        ),
        sa.ForeignKeyConstraint(
            ("observation_id", "job_posting_id", "source_id"),
            (
                "history.job_observations.id",
                "history.job_observations.job_posting_id",
                "history.job_observations.source_id",
            ),
            name="fk_data_quality_issues__observation_source__job_observations",
            ondelete="RESTRICT",
        ),
        sa.Index("ix_data_quality_issues__source_detected_at", "source_id", sa.desc("detected_at")),
        sa.Index("ix_data_quality_issues__job_posting_id", "job_posting_id"),
        sa.Index("ix_data_quality_issues__observation_id", "observation_id"),
        sa.Index("ix_data_quality_issues__issue_code", "issue_code"),
        {"schema": "quality"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    validation_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("quality.validation_runs.id", ondelete="RESTRICT")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    crawl_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="RESTRICT")
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("ingestion.extracted_records.id", ondelete="RESTRICT")
    )
    job_posting_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    observation_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    issue_code: Mapped[str] = mapped_column(sa.String(150))
    field_path: Mapped[str | None] = mapped_column(sa.String(500))
    severity: Mapped[str] = mapped_column(sa.String(20), server_default="warning")
    status: Mapped[str] = mapped_column(sa.String(30), server_default="open")
    fingerprint: Mapped[str] = mapped_column(sa.CHAR(64))
    message: Mapped[str] = mapped_column(sa.Text)
    rule_version: Mapped[str] = mapped_column(sa.String(100))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    detected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class FieldEvidence(V1Base):
    __tablename__ = "field_evidence"
    __table_args__ = (
        sa.UniqueConstraint(
            "observation_id",
            "field_path",
            "evidence_index",
            name="uq_field_evidence__observation_field_index",
        ),
        {"schema": "quality"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT")
    )
    field_path: Mapped[str] = mapped_column(sa.String(500))
    evidence_index: Mapped[int] = mapped_column(sa.SmallInteger, server_default="0")
    classification: Mapped[str] = mapped_column(sa.String(30))
    raw_value_json: Mapped[Any | None] = mapped_column(JSONB)
    normalized_value_json: Mapped[Any | None] = mapped_column(JSONB)
    evidence_path: Mapped[str | None] = mapped_column(sa.Text)
    evidence_section: Mapped[str | None] = mapped_column(sa.String(100))
    extraction_method: Mapped[str | None] = mapped_column(sa.String(100))
    extractor_version: Mapped[str | None] = mapped_column(sa.String(100))
    normalization_rule: Mapped[str | None] = mapped_column(sa.String(150))
    normalization_version: Mapped[str | None] = mapped_column(sa.String(100))
    inference_method: Mapped[str | None] = mapped_column(sa.String(150))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    review_status: Mapped[str] = mapped_column(sa.String(30), server_default="unreviewed")
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DuplicateCandidate(V1Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        sa.UniqueConstraint(
            "left_job_posting_id",
            "right_job_posting_id",
            "method_version",
            name="uq_duplicate_candidates__pair_method",
        ),
        {"schema": "quality"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    left_job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    right_job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    candidate_reason: Mapped[str] = mapped_column(sa.String(50))
    method_version: Mapped[str] = mapped_column(sa.String(100))
    score: Mapped[Decimal] = mapped_column(sa.Numeric(5, 4))
    feature_vector_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DuplicateCluster(V1Base):
    __tablename__ = "duplicate_clusters"
    __table_args__ = (
        sa.Index(
            "ix_duplicate_clusters__review_status_created_at",
            "review_status",
            sa.desc("created_at"),
        ),
        {"schema": "quality"},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    cluster_type: Mapped[str] = mapped_column(sa.String(30))
    method_version: Mapped[str] = mapped_column(sa.String(100))
    score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    review_status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    created_by: Mapped[str] = mapped_column(sa.String(20), server_default="automated")
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DuplicateClusterMember(V1Base):
    __tablename__ = "duplicate_cluster_members"
    __table_args__ = (
        sa.Index(
            "uq_duplicate_cluster_members__one_representative",
            "cluster_id",
            unique=True,
            postgresql_where=sa.text("member_role = 'representative'"),
        ),
        {"schema": "quality"},
    )
    cluster_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("quality.duplicate_clusters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    member_role: Mapped[str] = mapped_column(sa.String(20), server_default="member")
    membership_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    added_by: Mapped[str] = mapped_column(sa.String(20), server_default="automated")
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
