"""Database V1 immutable models in the private ``history`` schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import V1Base


class JobObservation(V1Base):
    __tablename__ = "job_observations"
    __table_args__ = (
        sa.UniqueConstraint("id", "job_posting_id", name="uq_job_observations__id_job"),
        sa.UniqueConstraint("id", "extracted_record_id", name="uq_job_observations__id_extracted"),
        sa.UniqueConstraint(
            "job_posting_id",
            "extracted_record_id",
            "normalization_version",
            name="uq_job_observations__job_extracted_normalization",
        ),
        sa.ForeignKeyConstraint(
            ("job_posting_id", "source_id", "source_job_id"),
            (
                "core.job_postings.id",
                "core.job_postings.source_id",
                "core.job_postings.source_job_id",
            ),
            name="fk_job_observations__job_source_identity__job_postings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("extracted_record_id", "source_id", "source_job_id"),
            (
                "ingestion.extracted_records.id",
                "ingestion.extracted_records.source_id",
                "ingestion.extracted_records.source_job_id",
            ),
            name="fk_job_observations__extracted_identity__extracted_records",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("previous_observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_job_observations__previous_job__job_observations",
            ondelete="RESTRICT",
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_job_id: Mapped[str] = mapped_column(sa.String(255))
    extracted_record_id: Mapped[int] = mapped_column(sa.BigInteger)
    crawl_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.crawl_runs.id", ondelete="SET NULL")
    )
    previous_observation_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    observation_reason: Mapped[str] = mapped_column(sa.String(30))
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    canonical_hash: Mapped[str] = mapped_column(sa.CHAR(64))
    source_content_hash: Mapped[str | None] = mapped_column(sa.CHAR(64))
    status: Mapped[str] = mapped_column(sa.String(20))
    source_url: Mapped[str] = mapped_column(sa.Text)
    canonical_url: Mapped[str | None] = mapped_column(sa.Text)
    title_raw: Mapped[str] = mapped_column(sa.Text)
    title_normalized: Mapped[str | None] = mapped_column(sa.Text)
    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.companies.id", ondelete="RESTRICT")
    )
    company_name_raw: Mapped[str | None] = mapped_column(sa.Text)
    location_raw: Mapped[str | None] = mapped_column(sa.Text)
    employment_type_code: Mapped[str | None] = mapped_column(
        sa.String(30), sa.ForeignKey("taxonomy.employment_types.code", ondelete="RESTRICT")
    )
    seniority_level_code: Mapped[str | None] = mapped_column(
        sa.String(30), sa.ForeignKey("taxonomy.seniority_levels.code", ondelete="RESTRICT")
    )
    work_mode: Mapped[str | None] = mapped_column(sa.String(30))
    experience_min_years: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    experience_max_years: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    canonical_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    extractor_version: Mapped[str | None] = mapped_column(sa.String(100))
    normalization_version: Mapped[str] = mapped_column(sa.String(100))
    confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ObservationDescription(V1Base):
    __tablename__ = "observation_descriptions"
    __table_args__ = {"schema": "history"}
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    description_text: Mapped[str | None] = mapped_column(sa.Text)
    description_format: Mapped[str] = mapped_column(sa.String(20), server_default="plain")
    language_code: Mapped[str | None] = mapped_column(sa.String(10))
    content_hash: Mapped[str] = mapped_column(sa.CHAR(64))
    redaction_status: Mapped[str] = mapped_column(sa.String(30), server_default="not_required")
    retained_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ObservationLocation(V1Base):
    __tablename__ = "observation_locations"
    __table_args__ = (
        sa.UniqueConstraint(
            "observation_id",
            "location_id",
            "relationship_type",
            name="uq_observation_locations__observation_location_relationship",
        ),
        sa.Index(
            "uq_observation_locations__one_primary",
            "observation_id",
            "relationship_type",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT")
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.locations.id", ondelete="RESTRICT")
    )
    relationship_type: Mapped[str] = mapped_column(sa.String(30), server_default="workplace")
    is_primary: Mapped[bool] = mapped_column(server_default=sa.false())
    is_remote: Mapped[bool] = mapped_column(server_default=sa.false())
    remote_scope: Mapped[str | None] = mapped_column(sa.String(30))
    source_text: Mapped[str | None] = mapped_column(sa.Text)
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ObservationSalary(V1Base):
    __tablename__ = "observation_salaries"
    __table_args__ = (
        sa.UniqueConstraint(
            "observation_id", "offer_index", name="uq_observation_salaries__observation_offer"
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT")
    )
    offer_index: Mapped[int] = mapped_column(sa.SmallInteger, server_default="0")
    source_salary_offer_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("core.salary_offers.id", ondelete="SET NULL")
    )
    raw_text: Mapped[str | None] = mapped_column(sa.Text)
    amount_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_exact: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(sa.CHAR(3))
    period: Mapped[str | None] = mapped_column(sa.String(20))
    compensation_type: Mapped[str] = mapped_column(sa.String(30), server_default="base_salary")
    tax_basis: Mapped[str] = mapped_column(sa.String(20), server_default="unknown")
    is_disclosed: Mapped[bool] = mapped_column(server_default=sa.false())
    is_negotiable: Mapped[bool] = mapped_column(server_default=sa.false())
    is_estimated: Mapped[bool] = mapped_column(server_default=sa.false())
    normalized_monthly_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    fx_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 8))
    fx_rate_date: Mapped[date | None] = mapped_column(sa.Date)
    normalization_method: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ObservationSkill(V1Base):
    __tablename__ = "observation_skills"
    __table_args__ = (
        sa.UniqueConstraint(
            "observation_id",
            "skill_id",
            "requirement_type",
            name="uq_observation_skills__observation_skill_requirement",
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT")
    )
    skill_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.skills.id", ondelete="RESTRICT")
    )
    requirement_type: Mapped[str] = mapped_column(sa.String(20), server_default="mentioned")
    evidence_text: Mapped[str | None] = mapped_column(sa.Text)
    evidence_section: Mapped[str | None] = mapped_column(sa.String(100))
    extraction_method: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class ObservationOccupation(V1Base):
    __tablename__ = "observation_occupations"
    __table_args__ = (
        sa.UniqueConstraint(
            "observation_id",
            "occupation_id",
            name="uq_observation_occupations__observation_occupation",
        ),
        sa.Index(
            "uq_observation_occupations__one_primary",
            "observation_id",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT")
    )
    occupation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.occupations.id", ondelete="RESTRICT")
    )
    is_primary: Mapped[bool] = mapped_column(server_default=sa.false())
    classification_method: Mapped[str | None] = mapped_column(sa.String(100))
    classifier_version: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobStatusEvent(V1Base):
    __tablename__ = "job_status_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_job_status_events__observation_job__job_observations",
            ondelete="RESTRICT",
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    observation_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    from_status: Mapped[str | None] = mapped_column(sa.String(20))
    to_status: Mapped[str] = mapped_column(sa.String(20))
    event_type: Mapped[str] = mapped_column(sa.String(40))
    event_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    rule_version: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobChangeEvent(V1Base):
    __tablename__ = "job_change_events"
    __table_args__ = (
        sa.UniqueConstraint(
            "from_observation_id",
            "to_observation_id",
            "field_path",
            "change_type",
            name="uq_job_change_events__observations_field_type",
        ),
        sa.ForeignKeyConstraint(
            ("from_observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_job_change_events__from_observation_job__job_observations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("to_observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_job_change_events__to_observation_job__job_observations",
            ondelete="RESTRICT",
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    from_observation_id: Mapped[int] = mapped_column(sa.BigInteger)
    to_observation_id: Mapped[int] = mapped_column(sa.BigInteger)
    field_path: Mapped[str] = mapped_column(sa.String(500))
    change_type: Mapped[str] = mapped_column(sa.String(30))
    old_value_json: Mapped[Any | None] = mapped_column(JSONB)
    new_value_json: Mapped[Any | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobRepostEvent(V1Base):
    __tablename__ = "job_repost_events"
    __table_args__ = (
        sa.UniqueConstraint(
            "previous_observation_id",
            "new_observation_id",
            "method_version",
            name="uq_job_repost_events__observations_method",
        ),
        sa.ForeignKeyConstraint(
            ("previous_observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_job_repost_events__previous_job__job_observations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("new_observation_id", "job_posting_id"),
            ("history.job_observations.id", "history.job_observations.job_posting_id"),
            name="fk_job_repost_events__new_observation_job__job_observations",
            ondelete="RESTRICT",
        ),
        {"schema": "history"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    previous_observation_id: Mapped[int] = mapped_column(sa.BigInteger)
    new_observation_id: Mapped[int] = mapped_column(sa.BigInteger)
    repost_type: Mapped[str] = mapped_column(sa.String(30))
    previous_posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    new_posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    detection_method: Mapped[str] = mapped_column(sa.String(100))
    method_version: Mapped[str] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    detected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
