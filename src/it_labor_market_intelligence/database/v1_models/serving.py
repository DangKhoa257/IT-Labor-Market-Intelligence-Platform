"""Database V1 models in the private ``serving`` schema."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import V1Base


class ServingRefreshRun(V1Base):
    __tablename__ = "refresh_runs"
    __table_args__ = {"schema": "serving"}
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    run_type: Mapped[str] = mapped_column(sa.String(30))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    document_version: Mapped[str] = mapped_column(sa.String(100))
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    watermark_observed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    rows_upserted: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    rows_deleted: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    salary_rows_replaced: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    error_count: Mapped[int] = mapped_column(server_default="0")
    configuration_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobSearchDocument(V1Base):
    __tablename__ = "job_search_documents"
    __table_args__ = {"schema": "serving"}
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT"),
        unique=True,
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    source_job_id: Mapped[str] = mapped_column(sa.String(255))
    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.companies.id", ondelete="RESTRICT")
    )
    source_url: Mapped[str] = mapped_column(sa.Text)
    canonical_url: Mapped[str | None] = mapped_column(sa.Text)
    title: Mapped[str] = mapped_column(sa.Text)
    title_normalized: Mapped[str | None] = mapped_column(sa.Text)
    company_name: Mapped[str | None] = mapped_column(sa.Text)
    description_excerpt: Mapped[str | None] = mapped_column(sa.Text)
    employment_type_code: Mapped[str | None] = mapped_column(sa.String(30))
    seniority_level_code: Mapped[str | None] = mapped_column(sa.String(30))
    work_mode: Mapped[str | None] = mapped_column(sa.String(30))
    status: Mapped[str] = mapped_column(sa.String(20))
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    location_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    location_labels: Mapped[list[str]] = mapped_column(ARRAY(sa.Text))
    locations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    occupation_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    occupation_names: Mapped[list[str]] = mapped_column(ARRAY(sa.Text))
    occupations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    skill_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    skill_names: Mapped[list[str]] = mapped_column(ARRAY(sa.Text))
    skills_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    salary_disclosed: Mapped[bool]
    search_vector: Mapped[str] = mapped_column(TSVECTOR)
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("serving.refresh_runs.id", ondelete="RESTRICT")
    )
    document_version: Mapped[str] = mapped_column(sa.String(100))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobSearchSalaryOffer(V1Base):
    __tablename__ = "job_search_salary_offers"
    __table_args__ = {"schema": "serving"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("serving.job_search_documents.job_posting_id", ondelete="CASCADE"),
    )
    observation_salary_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.observation_salaries.id", ondelete="RESTRICT"),
        unique=True,
    )
    currency: Mapped[str | None] = mapped_column(sa.CHAR(3))
    period: Mapped[str | None] = mapped_column(sa.String(20))
    tax_basis: Mapped[str] = mapped_column(sa.String(20))
    compensation_type: Mapped[str] = mapped_column(sa.String(30))
    is_disclosed: Mapped[bool]
    is_negotiable: Mapped[bool]
    is_estimated: Mapped[bool]
    amount_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_exact: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("serving.refresh_runs.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
