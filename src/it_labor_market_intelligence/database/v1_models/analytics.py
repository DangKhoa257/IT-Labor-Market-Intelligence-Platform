"""Database V1 models in the private ``analytics`` schema."""

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


class AnalyticsRefreshRun(V1Base):
    __tablename__ = "refresh_runs"
    __table_args__ = {"schema": "analytics"}
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    run_type: Mapped[str] = mapped_column(sa.String(30))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    window_start_date: Mapped[date | None] = mapped_column(sa.Date)
    window_end_date: Mapped[date | None] = mapped_column(sa.Date)
    watermark_observed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    lookback_days: Mapped[int] = mapped_column(server_default="7")
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    trigger_type: Mapped[str] = mapped_column(sa.String(30), server_default="manual")
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    fact_rows_inserted: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    dimension_rows_inserted: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    dimension_rows_updated: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    aggregate_rows_upserted: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
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


class DimDate(V1Base):
    __tablename__ = "dim_dates"
    __table_args__ = {"schema": "analytics"}
    date_key: Mapped[int] = mapped_column(primary_key=True)
    calendar_date: Mapped[date] = mapped_column(sa.Date, unique=True)
    year: Mapped[int] = mapped_column(sa.SmallInteger)
    quarter: Mapped[int] = mapped_column(sa.SmallInteger)
    month: Mapped[int] = mapped_column(sa.SmallInteger)
    month_name: Mapped[str] = mapped_column(sa.String(20))
    week_of_year: Mapped[int] = mapped_column(sa.SmallInteger)
    day_of_month: Mapped[int] = mapped_column(sa.SmallInteger)
    day_of_week: Mapped[int] = mapped_column(sa.SmallInteger)
    day_name: Mapped[str] = mapped_column(sa.String(20))
    is_weekend: Mapped[bool]
    month_start_date: Mapped[date] = mapped_column(sa.Date)
    month_end_date: Mapped[date] = mapped_column(sa.Date)
    quarter_start_date: Mapped[date] = mapped_column(sa.Date)
    quarter_end_date: Mapped[date] = mapped_column(sa.Date)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DimSource(V1Base):
    __tablename__ = "dim_sources"
    __table_args__ = {"schema": "analytics"}
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True), primary_key=True
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT"),
        unique=True,
    )
    slug: Mapped[str] = mapped_column(sa.String(100), unique=True)
    display_name: Mapped[str] = mapped_column(sa.String(255))
    source_type: Mapped[str] = mapped_column(sa.String(50))
    country_code: Mapped[str | None] = mapped_column(sa.CHAR(2))
    status: Mapped[str] = mapped_column(sa.String(30))
    is_enabled: Mapped[bool]
    source_updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    warehouse_synced_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DimCompany(V1Base):
    __tablename__ = "dim_companies"
    __table_args__ = {"schema": "analytics"}
    company_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True), primary_key=True
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.companies.id", ondelete="RESTRICT"), unique=True
    )
    canonical_name: Mapped[str] = mapped_column(sa.String(500))
    normalized_name: Mapped[str] = mapped_column(sa.String(500))
    company_type: Mapped[str] = mapped_column(sa.String(30))
    headquarters_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.locations.id", ondelete="SET NULL")
    )
    resolution_status: Mapped[str] = mapped_column(sa.String(30))
    company_updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    warehouse_synced_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DimLocation(V1Base):
    __tablename__ = "dim_locations"
    __table_args__ = {"schema": "analytics"}
    location_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=False), primary_key=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.locations.id", ondelete="RESTRICT"), unique=True
    )
    resolution_key: Mapped[str] = mapped_column(sa.String(750), unique=True)
    location_type: Mapped[str] = mapped_column(sa.String(30))
    country_code: Mapped[str | None] = mapped_column(sa.CHAR(2))
    admin_level_1: Mapped[str | None] = mapped_column(sa.String(255))
    admin_level_2: Mapped[str | None] = mapped_column(sa.String(255))
    locality: Mapped[str | None] = mapped_column(sa.String(255))
    canonical_label: Mapped[str] = mapped_column(sa.String(750))
    normalized_label: Mapped[str] = mapped_column(sa.String(750))
    latitude: Mapped[Decimal | None] = mapped_column(sa.Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(sa.Numeric(9, 6))
    location_updated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    warehouse_synced_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DimOccupation(V1Base):
    __tablename__ = "dim_occupations"
    __table_args__ = {"schema": "analytics"}
    occupation_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=False), primary_key=True
    )
    occupation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("taxonomy.occupations.id", ondelete="RESTRICT"),
        unique=True,
    )
    taxonomy_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("taxonomy.taxonomy_versions.id", ondelete="RESTRICT"),
    )
    taxonomy_version: Mapped[str] = mapped_column(sa.String(100))
    canonical_code: Mapped[str] = mapped_column(sa.String(100))
    canonical_name: Mapped[str] = mapped_column(sa.String(255))
    normalized_name: Mapped[str] = mapped_column(sa.String(255))
    parent_occupation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.occupations.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool]
    occupation_updated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    warehouse_synced_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DimSkill(V1Base):
    __tablename__ = "dim_skills"
    __table_args__ = {"schema": "analytics"}
    skill_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True), primary_key=True
    )
    skill_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.skills.id", ondelete="RESTRICT"), unique=True
    )
    taxonomy_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("taxonomy.taxonomy_versions.id", ondelete="RESTRICT"),
    )
    taxonomy_version: Mapped[str] = mapped_column(sa.String(100))
    canonical_code: Mapped[str] = mapped_column(sa.String(100))
    canonical_name: Mapped[str] = mapped_column(sa.String(255))
    normalized_name: Mapped[str] = mapped_column(sa.String(255))
    skill_type: Mapped[str] = mapped_column(sa.String(30))
    parent_skill_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.skills.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool]
    skill_updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    warehouse_synced_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class FactJobObservation(V1Base):
    __tablename__ = "fact_job_observations"
    __table_args__ = {"schema": "analytics"}
    job_observation_fact_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True), primary_key=True
    )
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT"),
        unique=True,
    )
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="RESTRICT")
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT")
    )
    company_key: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("analytics.dim_companies.company_key", ondelete="RESTRICT")
    )
    observed_date_key: Mapped[int] = mapped_column(
        sa.ForeignKey("analytics.dim_dates.date_key", ondelete="RESTRICT")
    )
    posted_date_key: Mapped[int | None] = mapped_column(
        sa.ForeignKey("analytics.dim_dates.date_key", ondelete="RESTRICT")
    )
    expires_date_key: Mapped[int | None] = mapped_column(
        sa.ForeignKey("analytics.dim_dates.date_key", ondelete="RESTRICT")
    )
    previous_observation_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    observation_reason: Mapped[str] = mapped_column(sa.String(30))
    status: Mapped[str] = mapped_column(sa.String(20))
    employment_type_code: Mapped[str | None] = mapped_column(sa.String(30))
    seniority_level_code: Mapped[str | None] = mapped_column(sa.String(30))
    work_mode: Mapped[str | None] = mapped_column(sa.String(30))
    experience_min_years: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    experience_max_years: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    salary_disclosed: Mapped[bool] = mapped_column(server_default=sa.false())
    skill_count: Mapped[int] = mapped_column(server_default="0")
    occupation_count: Mapped[int] = mapped_column(server_default="0")
    location_count: Mapped[int] = mapped_column(server_default="0")
    is_first_observation: Mapped[bool] = mapped_column(server_default=sa.false())
    is_status_change: Mapped[bool] = mapped_column(server_default=sa.false())
    is_content_change: Mapped[bool] = mapped_column(server_default=sa.false())
    canonical_hash: Mapped[str] = mapped_column(sa.CHAR(64))
    normalization_version: Mapped[str] = mapped_column(sa.String(100))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    loaded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class FactSalaryObservation(V1Base):
    __tablename__ = "fact_salary_observations"
    __table_args__ = {"schema": "analytics"}
    salary_fact_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True), primary_key=True
    )
    observation_salary_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.observation_salaries.id", ondelete="RESTRICT"),
        unique=True,
    )
    observation_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("history.job_observations.id", ondelete="RESTRICT")
    )
    job_observation_fact_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "analytics.fact_job_observations.job_observation_fact_id", ondelete="RESTRICT"
        ),
    )
    observed_date_key: Mapped[int] = mapped_column(
        sa.ForeignKey("analytics.dim_dates.date_key", ondelete="RESTRICT")
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT")
    )
    company_key: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("analytics.dim_companies.company_key", ondelete="RESTRICT")
    )
    amount_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_exact: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(sa.CHAR(3))
    period: Mapped[str | None] = mapped_column(sa.String(20))
    compensation_type: Mapped[str] = mapped_column(sa.String(30))
    tax_basis: Mapped[str] = mapped_column(sa.String(20))
    is_disclosed: Mapped[bool]
    is_negotiable: Mapped[bool]
    is_estimated: Mapped[bool]
    normalized_monthly_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    fx_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 8))
    fx_rate_date: Mapped[date | None] = mapped_column(sa.Date)
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    loaded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class BridgeJobObservationLocation(V1Base):
    __tablename__ = "bridge_job_observation_locations"
    __table_args__ = {"schema": "analytics"}
    job_observation_fact_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "analytics.fact_job_observations.job_observation_fact_id", ondelete="RESTRICT"
        ),
        primary_key=True,
    )
    observation_location_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.observation_locations.id", ondelete="RESTRICT"),
        primary_key=True,
        unique=True,
    )
    location_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("analytics.dim_locations.location_key", ondelete="RESTRICT")
    )
    relationship_type: Mapped[str] = mapped_column(sa.String(30))
    is_primary: Mapped[bool]
    is_remote: Mapped[bool]
    remote_scope: Mapped[str | None] = mapped_column(sa.String(30))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    loaded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class BridgeJobObservationOccupation(V1Base):
    __tablename__ = "bridge_job_observation_occupations"
    __table_args__ = (
        sa.Index(
            "uq_bridge_job_observation_occupations__one_primary",
            "job_observation_fact_id",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
        {"schema": "analytics"},
    )
    job_observation_fact_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "analytics.fact_job_observations.job_observation_fact_id", ondelete="RESTRICT"
        ),
        primary_key=True,
    )
    observation_occupation_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.observation_occupations.id", ondelete="RESTRICT"),
        primary_key=True,
        unique=True,
    )
    occupation_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_occupations.occupation_key", ondelete="RESTRICT"),
    )
    is_primary: Mapped[bool]
    classification_method: Mapped[str | None] = mapped_column(sa.String(100))
    classifier_version: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    loaded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class BridgeJobObservationSkill(V1Base):
    __tablename__ = "bridge_job_observation_skills"
    __table_args__ = {"schema": "analytics"}
    job_observation_fact_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "analytics.fact_job_observations.job_observation_fact_id", ondelete="RESTRICT"
        ),
        primary_key=True,
    )
    observation_skill_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("history.observation_skills.id", ondelete="RESTRICT"),
        primary_key=True,
        unique=True,
    )
    skill_key: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("analytics.dim_skills.skill_key", ondelete="RESTRICT")
    )
    requirement_type: Mapped[str] = mapped_column(sa.String(20))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    loaded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DailyMarketMetric(V1Base):
    __tablename__ = "daily_market_metrics"
    __table_args__ = {"schema": "analytics"}
    metric_date: Mapped[date] = mapped_column(
        sa.Date,
        sa.ForeignKey("analytics.dim_dates.calendar_date", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    employment_type_code: Mapped[str] = mapped_column(
        sa.String(30),
        sa.ForeignKey("taxonomy.employment_types.code", ondelete="RESTRICT"),
        primary_key=True,
    )
    seniority_level_code: Mapped[str] = mapped_column(
        sa.String(30),
        sa.ForeignKey("taxonomy.seniority_levels.code", ondelete="RESTRICT"),
        primary_key=True,
    )
    work_mode: Mapped[str] = mapped_column(sa.String(30), primary_key=True)
    active_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    new_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    closed_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    expired_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    removed_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    reactivated_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    content_changed_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    salary_disclosed_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    remote_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DailyCompanyHiring(V1Base):
    __tablename__ = "daily_company_hiring"
    __table_args__ = {"schema": "analytics"}
    metric_date: Mapped[date] = mapped_column(
        sa.Date,
        sa.ForeignKey("analytics.dim_dates.calendar_date", ondelete="RESTRICT"),
        primary_key=True,
    )
    company_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_companies.company_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    active_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    new_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    closed_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    unique_occupation_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    unique_skill_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    salary_disclosed_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    remote_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DailyLocationDemand(V1Base):
    __tablename__ = "daily_location_demand"
    __table_args__ = {"schema": "analytics"}
    metric_date: Mapped[date] = mapped_column(
        sa.Date,
        sa.ForeignKey("analytics.dim_dates.calendar_date", ondelete="RESTRICT"),
        primary_key=True,
    )
    location_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_locations.location_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    work_mode: Mapped[str] = mapped_column(sa.String(30), primary_key=True)
    active_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    new_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    closed_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    salary_disclosed_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DailyOccupationDemand(V1Base):
    __tablename__ = "daily_occupation_demand"
    __table_args__ = {"schema": "analytics"}
    metric_date: Mapped[date] = mapped_column(
        sa.Date,
        sa.ForeignKey("analytics.dim_dates.calendar_date", ondelete="RESTRICT"),
        primary_key=True,
    )
    occupation_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_occupations.occupation_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    active_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    new_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    closed_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    salary_disclosed_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    remote_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DailySkillDemand(V1Base):
    __tablename__ = "daily_skill_demand"
    __table_args__ = {"schema": "analytics"}
    metric_date: Mapped[date] = mapped_column(
        sa.Date,
        sa.ForeignKey("analytics.dim_dates.calendar_date", ondelete="RESTRICT"),
        primary_key=True,
    )
    skill_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_skills.skill_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    requirement_type: Mapped[str] = mapped_column(sa.String(20), primary_key=True)
    active_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    new_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    closed_posting_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    company_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    occupation_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class DailySalaryMetric(V1Base):
    __tablename__ = "daily_salary_metrics"
    __table_args__ = {"schema": "analytics"}
    metric_date: Mapped[date] = mapped_column(
        sa.Date,
        sa.ForeignKey("analytics.dim_dates.calendar_date", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_sources.source_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    occupation_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_occupations.occupation_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    location_key: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("analytics.dim_locations.location_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    currency: Mapped[str] = mapped_column(sa.CHAR(3), primary_key=True)
    period: Mapped[str] = mapped_column(sa.String(20), primary_key=True)
    tax_basis: Mapped[str] = mapped_column(sa.String(20), primary_key=True)
    disclosed_salary_count: Mapped[int] = mapped_column(sa.BigInteger)
    estimated_salary_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    negotiable_salary_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    amount_min_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_max_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    amount_exact_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_min_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_max_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_min_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_max_average: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_min_median: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_monthly_max_median: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_min_median: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    normalized_annual_max_median: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2))
    refresh_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("analytics.refresh_runs.id", ondelete="RESTRICT")
    )
    calculation_version: Mapped[str] = mapped_column(sa.String(100))
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
