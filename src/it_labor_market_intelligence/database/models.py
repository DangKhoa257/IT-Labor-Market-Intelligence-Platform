"""Relational Phase 3 schema."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    comparison_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    jobs: Mapped[list[JobPosting]] = relationship(back_populates="company")


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_job_source_identity"),
        Index("ix_jobs_primary_category", "primary_category"),
        Index("ix_jobs_city", "city"),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_posted_at", "posted_at"),
        Index("ix_jobs_salary_currency", "salary_currency"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title_raw: Mapped[str] = mapped_column(Text, nullable=False)
    title_normalized: Mapped[str | None] = mapped_column(Text)
    primary_category: Mapped[str | None] = mapped_column(String(255))
    secondary_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    location_raw: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(255))
    province: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(100))
    work_mode: Mapped[str | None] = mapped_column(String(50))
    employment_type: Mapped[str | None] = mapped_column(String(50))
    seniority: Mapped[str | None] = mapped_column(String(100))
    experience_min_years: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    experience_max_years: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    salary_raw: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    salary_period: Mapped[str | None] = mapped_column(String(50))
    salary_type: Mapped[str | None] = mapped_column(String(50))
    salary_disclosed: Mapped[bool] = mapped_column(Boolean, default=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    extractor_version: Mapped[str | None] = mapped_column(String(100))
    normalization_version: Mapped[str | None] = mapped_column(String(100))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    description_raw: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    source: Mapped[Source] = relationship()
    company: Mapped[Company | None] = relationship(back_populates="jobs")
    skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(255))
    jobs: Mapped[list[JobSkill]] = relationship(back_populates="skill")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id", name="uq_job_skill"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    evidence: Mapped[str | None] = mapped_column(Text)
    job: Mapped[JobPosting] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="jobs")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    run_type: Mapped[str] = mapped_column(String(50), default="IMPORT")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inserted: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)


class DuplicateCluster(Base):
    __tablename__ = "duplicate_clusters"
    id: Mapped[int] = mapped_column(primary_key=True)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    method_version: Mapped[str | None] = mapped_column(String(100))


class DuplicateClusterMember(Base):
    __tablename__ = "duplicate_cluster_members"
    __table_args__ = (UniqueConstraint("cluster_id", "job_id", name="uq_cluster_job"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("duplicate_clusters.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    representative: Mapped[bool] = mapped_column(Boolean, default=False)
