"""Database V1 models in the private ``core`` schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import V1Base


class Location(V1Base):
    __tablename__ = "locations"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    resolution_key: Mapped[str] = mapped_column(sa.String(750), unique=True)
    location_type: Mapped[str] = mapped_column(sa.String(30))
    country_code: Mapped[str | None] = mapped_column(sa.CHAR(2))
    admin_level_1: Mapped[str | None] = mapped_column(sa.String(255))
    admin_level_2: Mapped[str | None] = mapped_column(sa.String(255))
    locality: Mapped[str | None] = mapped_column(sa.String(255))
    street_address: Mapped[str | None] = mapped_column(sa.Text)
    postal_code: Mapped[str | None] = mapped_column(sa.String(30))
    latitude: Mapped[Decimal | None] = mapped_column(sa.Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(sa.Numeric(9, 6))
    canonical_label: Mapped[str] = mapped_column(sa.String(750))
    normalized_label: Mapped[str] = mapped_column(sa.String(750))
    geocoding_provider: Mapped[str | None] = mapped_column(sa.String(100))
    geocoding_version: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class Company(V1Base):
    __tablename__ = "companies"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    canonical_name: Mapped[str] = mapped_column(sa.String(500))
    normalized_name: Mapped[str] = mapped_column(sa.String(500))
    legal_name: Mapped[str | None] = mapped_column(sa.String(500))
    company_type: Mapped[str] = mapped_column(sa.String(30), server_default="unknown")
    headquarters_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.locations.id", ondelete="SET NULL")
    )
    website_url: Mapped[str | None] = mapped_column(sa.Text)
    employee_count_min: Mapped[int | None]
    employee_count_max: Mapped[int | None]
    resolution_status: Mapped[str] = mapped_column(sa.String(30), server_default="provisional")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class CompanyAlias(V1Base):
    __tablename__ = "company_aliases"
    __table_args__ = (
        sa.Index(
            "uq_company_aliases__global",
            "company_id",
            "normalized_alias",
            unique=True,
            postgresql_where=sa.text("source_id IS NULL"),
        ),
        sa.Index(
            "uq_company_aliases__source",
            "company_id",
            "source_id",
            "normalized_alias",
            unique=True,
            postgresql_where=sa.text("source_id IS NOT NULL"),
        ),
        {"schema": "core"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.companies.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
    )
    alias: Mapped[str] = mapped_column(sa.String(500))
    normalized_alias: Mapped[str] = mapped_column(sa.String(500))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    is_verified: Mapped[bool] = mapped_column(server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class CompanyDomain(V1Base):
    __tablename__ = "company_domains"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id", "domain", "domain_type", name="uq_company_domains__company_domain_type"
        ),
        {"schema": "core"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.companies.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    domain: Mapped[str] = mapped_column(sa.String(255))
    domain_type: Mapped[str] = mapped_column(sa.String(30), server_default="corporate")
    is_verified: Mapped[bool] = mapped_column(server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class CoreJobPosting(V1Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        sa.UniqueConstraint("source_id", "source_job_id", name="uq_job_postings__source_identity"),
        {"schema": "core"},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="RESTRICT")
    )
    source_job_id: Mapped[str] = mapped_column(sa.String(255))
    latest_extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
    )
    company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.companies.id", ondelete="RESTRICT")
    )
    source_url: Mapped[str] = mapped_column(sa.Text)
    canonical_url: Mapped[str | None] = mapped_column(sa.Text)
    title_raw: Mapped[str] = mapped_column(sa.Text)
    title_normalized: Mapped[str | None] = mapped_column(sa.Text)
    company_name_raw: Mapped[str | None] = mapped_column(sa.Text)
    company_name_status: Mapped[str] = mapped_column(sa.String(30), server_default="unverified")
    location_raw: Mapped[str | None] = mapped_column(sa.Text)
    employment_type_code: Mapped[str | None] = mapped_column(
        sa.String(30),
        sa.ForeignKey("taxonomy.employment_types.code", ondelete="RESTRICT"),
    )
    seniority_level_code: Mapped[str | None] = mapped_column(
        sa.String(30),
        sa.ForeignKey("taxonomy.seniority_levels.code", ondelete="RESTRICT"),
    )
    work_mode: Mapped[str | None] = mapped_column(sa.String(30))
    experience_min_years: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    experience_max_years: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    current_status: Mapped[str] = mapped_column(sa.String(20), server_default="unknown")
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    last_changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    source_content_hash: Mapped[str | None] = mapped_column(sa.CHAR(64))
    canonical_hash: Mapped[str | None] = mapped_column(sa.CHAR(64))
    extractor_version: Mapped[str | None] = mapped_column(sa.String(100))
    normalization_version: Mapped[str | None] = mapped_column(sa.String(100))
    confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobPostingDescription(V1Base):
    __tablename__ = "job_posting_descriptions"
    __table_args__ = {"schema": "core"}
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("core.job_postings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
    )
    description_text: Mapped[str] = mapped_column(sa.Text)
    description_format: Mapped[str] = mapped_column(sa.String(20), server_default="plain")
    language_code: Mapped[str | None] = mapped_column(sa.String(10))
    content_hash: Mapped[str] = mapped_column(sa.CHAR(64))
    redaction_status: Mapped[str] = mapped_column(sa.String(30), server_default="not_required")
    retained_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobPostingLocation(V1Base):
    __tablename__ = "job_posting_locations"
    __table_args__ = (
        sa.UniqueConstraint(
            "job_posting_id",
            "location_id",
            "relationship_type",
            name="uq_job_posting_locations__job_location_relationship",
        ),
        sa.Index(
            "uq_job_posting_locations__one_primary",
            "job_posting_id",
            "relationship_type",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
        {"schema": "core"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="CASCADE")
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.locations.id", ondelete="RESTRICT")
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
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
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class SalaryOffer(V1Base):
    __tablename__ = "salary_offers"
    __table_args__ = {"schema": "core"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="CASCADE")
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
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
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobPostingSkill(V1Base):
    __tablename__ = "job_posting_skills"
    __table_args__ = (
        sa.UniqueConstraint(
            "job_posting_id",
            "skill_id",
            "requirement_type",
            name="uq_job_posting_skills__job_skill_requirement",
        ),
        {"schema": "core"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="CASCADE")
    )
    skill_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.skills.id", ondelete="RESTRICT")
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
    )
    requirement_type: Mapped[str] = mapped_column(sa.String(20), server_default="mentioned")
    evidence_text: Mapped[str | None] = mapped_column(sa.Text)
    evidence_section: Mapped[str | None] = mapped_column(sa.String(100))
    extraction_method: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class JobPostingOccupation(V1Base):
    __tablename__ = "job_posting_occupations"
    __table_args__ = (
        sa.UniqueConstraint(
            "job_posting_id", "occupation_id", name="uq_job_posting_occupations__job_occupation"
        ),
        sa.Index(
            "uq_job_posting_occupations__one_primary",
            "job_posting_id",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
        {"schema": "core"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    job_posting_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("core.job_postings.id", ondelete="CASCADE")
    )
    occupation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.occupations.id", ondelete="RESTRICT")
    )
    extracted_record_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("ingestion.extracted_records.id", ondelete="SET NULL"),
    )
    is_primary: Mapped[bool] = mapped_column(server_default=sa.false())
    classification_method: Mapped[str | None] = mapped_column(sa.String(100))
    classifier_version: Mapped[str | None] = mapped_column(sa.String(100))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
