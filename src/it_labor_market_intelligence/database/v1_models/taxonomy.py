"""Database V1 models in the private ``taxonomy`` schema."""

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


class TaxonomyVersion(V1Base):
    __tablename__ = "taxonomy_versions"
    __table_args__ = (
        sa.UniqueConstraint("taxonomy_type", "version", name="uq_taxonomy_versions__type_version"),
        sa.Index(
            "uq_taxonomy_versions__one_active_type",
            "taxonomy_type",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        ),
        {"schema": "taxonomy"},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    taxonomy_type: Mapped[str] = mapped_column(sa.String(30))
    version: Mapped[str] = mapped_column(sa.String(100))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="draft")
    name: Mapped[str] = mapped_column(sa.String(255))
    description: Mapped[str | None] = mapped_column(sa.Text)
    source_name: Mapped[str | None] = mapped_column(sa.String(255))
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    license_name: Mapped[str | None] = mapped_column(sa.String(255))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class EmploymentType(V1Base):
    __tablename__ = "employment_types"
    __table_args__ = (
        sa.UniqueConstraint("display_name", name="uq_employment_types__display_name"),
        {"schema": "taxonomy"},
    )
    code: Mapped[str] = mapped_column(sa.String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(sa.String(100))
    sort_order: Mapped[int] = mapped_column(sa.SmallInteger, server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class SeniorityLevel(V1Base):
    __tablename__ = "seniority_levels"
    __table_args__ = (
        sa.UniqueConstraint("display_name", name="uq_seniority_levels__display_name"),
        sa.UniqueConstraint("rank_order", name="uq_seniority_levels__rank_order"),
        {"schema": "taxonomy"},
    )
    code: Mapped[str] = mapped_column(sa.String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(sa.String(100))
    rank_order: Mapped[int] = mapped_column(sa.SmallInteger)
    is_management: Mapped[bool] = mapped_column(server_default=sa.false())
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class Occupation(V1Base):
    __tablename__ = "occupations"
    __table_args__ = (
        sa.UniqueConstraint(
            "taxonomy_version_id", "canonical_code", name="uq_occupations__version_code"
        ),
        sa.UniqueConstraint("id", "taxonomy_version_id", name="uq_occupations__id_version"),
        sa.ForeignKeyConstraint(
            ("parent_id", "taxonomy_version_id"),
            ("taxonomy.occupations.id", "taxonomy.occupations.taxonomy_version_id"),
            name="fk_occupations__parent_id_version__occupations",
            ondelete="RESTRICT",
        ),
        {"schema": "taxonomy"},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    taxonomy_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("taxonomy.taxonomy_versions.id", ondelete="RESTRICT"),
    )
    canonical_code: Mapped[str] = mapped_column(sa.String(100))
    canonical_name: Mapped[str] = mapped_column(sa.String(255))
    normalized_name: Mapped[str] = mapped_column(sa.String(255))
    parent_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(sa.Text)
    external_system: Mapped[str | None] = mapped_column(sa.String(100))
    external_id: Mapped[str | None] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class OccupationAlias(V1Base):
    __tablename__ = "occupation_aliases"
    __table_args__ = (
        sa.Index(
            "uq_occupation_aliases__global",
            "occupation_id",
            "normalized_alias",
            unique=True,
            postgresql_where=sa.text("source_id IS NULL"),
        ),
        sa.Index(
            "uq_occupation_aliases__source",
            "occupation_id",
            "source_id",
            "normalized_alias",
            unique=True,
            postgresql_where=sa.text("source_id IS NOT NULL"),
        ),
        {"schema": "taxonomy"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    occupation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.occupations.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    alias: Mapped[str] = mapped_column(sa.String(500))
    normalized_alias: Mapped[str] = mapped_column(sa.String(500))
    language_code: Mapped[str | None] = mapped_column(sa.String(10))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    is_verified: Mapped[bool] = mapped_column(server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class Skill(V1Base):
    __tablename__ = "skills"
    __table_args__ = (
        sa.UniqueConstraint(
            "taxonomy_version_id", "canonical_code", name="uq_skills__version_code"
        ),
        sa.UniqueConstraint("id", "taxonomy_version_id", name="uq_skills__id_version"),
        sa.ForeignKeyConstraint(
            ("parent_id", "taxonomy_version_id"),
            ("taxonomy.skills.id", "taxonomy.skills.taxonomy_version_id"),
            name="fk_skills__parent_id_version__skills",
            ondelete="RESTRICT",
        ),
        {"schema": "taxonomy"},
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    taxonomy_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("taxonomy.taxonomy_versions.id", ondelete="RESTRICT"),
    )
    canonical_code: Mapped[str] = mapped_column(sa.String(100))
    canonical_name: Mapped[str] = mapped_column(sa.String(255))
    normalized_name: Mapped[str] = mapped_column(sa.String(255))
    skill_type: Mapped[str] = mapped_column(sa.String(30), server_default="other")
    parent_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(sa.Text)
    external_system: Mapped[str | None] = mapped_column(sa.String(100))
    external_id: Mapped[str | None] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )


class SkillAlias(V1Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (
        sa.Index(
            "uq_skill_aliases__global",
            "skill_id",
            "normalized_alias",
            unique=True,
            postgresql_where=sa.text("source_id IS NULL"),
        ),
        sa.Index(
            "uq_skill_aliases__source",
            "skill_id",
            "source_id",
            "normalized_alias",
            unique=True,
            postgresql_where=sa.text("source_id IS NOT NULL"),
        ),
        {"schema": "taxonomy"},
    )
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    skill_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("taxonomy.skills.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("ingestion.sources.id", ondelete="SET NULL")
    )
    alias: Mapped[str] = mapped_column(sa.String(500))
    normalized_alias: Mapped[str] = mapped_column(sa.String(500))
    language_code: Mapped[str | None] = mapped_column(sa.String(10))
    confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    is_verified: Mapped[bool] = mapped_column(server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()")
    )
