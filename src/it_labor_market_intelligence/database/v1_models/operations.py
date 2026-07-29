"""Schema-qualified models for private operational evidence tables."""

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


class PartitionPolicy(V1Base):
    __tablename__ = "partition_policies"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    target_schema: Mapped[str] = mapped_column(sa.String(63))
    target_table: Mapped[str] = mapped_column(sa.String(63))
    partition_key: Mapped[str] = mapped_column(sa.String(63))
    partition_strategy: Mapped[str] = mapped_column(sa.String(20), server_default="range")
    partition_interval: Mapped[str] = mapped_column(sa.String(20), server_default="month")
    activation_row_threshold: Mapped[int] = mapped_column(sa.BigInteger)
    retention_partition_count: Mapped[int | None]
    status: Mapped[str] = mapped_column(sa.String(20), server_default="advisory")
    approved_by: Mapped[str | None] = mapped_column(sa.String(255))
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    implemented_revision: Mapped[str | None] = mapped_column(sa.String(100))
    rationale: Mapped[str] = mapped_column(sa.Text)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class RetentionPolicy(V1Base):
    __tablename__ = "retention_policies"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    policy_code: Mapped[str] = mapped_column(sa.String(100))
    target_schema: Mapped[str] = mapped_column(sa.String(63))
    target_table: Mapped[str] = mapped_column(sa.String(63))
    record_class: Mapped[str] = mapped_column(sa.String(50))
    time_column: Mapped[str] = mapped_column(sa.String(63))
    archive_after_days: Mapped[int | None]
    delete_after_days: Mapped[int | None]
    batch_size: Mapped[int] = mapped_column(server_default="1000")
    requires_archive: Mapped[bool] = mapped_column(server_default=sa.text("true"))
    legal_hold: Mapped[bool] = mapped_column(server_default=sa.text("false"))
    legal_hold_reason: Mapped[str | None] = mapped_column(sa.Text)
    enabled: Mapped[bool] = mapped_column(server_default=sa.text("false"))
    policy_version: Mapped[str] = mapped_column(sa.String(100))
    selection_contract_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(sa.String(255))
    approved_by: Mapped[str | None] = mapped_column(sa.String(255))
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class RetentionRun(V1Base):
    __tablename__ = "retention_runs"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("operations.retention_policies.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    dry_run: Mapped[bool] = mapped_column(server_default=sa.text("true"))
    cutoff_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    candidate_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    archived_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    deleted_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    skipped_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    failed_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    requested_by: Mapped[str] = mapped_column(sa.String(255))
    delete_authorized_by: Mapped[str | None] = mapped_column(sa.String(255))
    delete_authorized_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class RetentionRunItem(V1Base):
    __tablename__ = "retention_run_items"
    __table_args__ = {"schema": "operations"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    retention_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("operations.retention_runs.id", ondelete="RESTRICT")
    )
    target_record_key: Mapped[str] = mapped_column(sa.Text)
    record_timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="candidate")
    archive_object_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("operations.archive_objects.id", ondelete="RESTRICT")
    )
    record_sha256: Mapped[str | None] = mapped_column(sa.CHAR(64))
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ArchiveManifest(V1Base):
    __tablename__ = "archive_manifests"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    retention_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("operations.retention_runs.id", ondelete="RESTRICT")
    )
    target_schema: Mapped[str] = mapped_column(sa.String(63))
    target_table: Mapped[str] = mapped_column(sa.String(63))
    archive_format: Mapped[str] = mapped_column(sa.String(20))
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    storage_provider: Mapped[str] = mapped_column(sa.String(50))
    manifest_uri: Mapped[str] = mapped_column(sa.Text)
    schema_revision: Mapped[str] = mapped_column(sa.String(100))
    compression: Mapped[str] = mapped_column(sa.String(20), server_default="zstd")
    encryption_method: Mapped[str] = mapped_column(sa.String(50))
    encryption_key_reference: Mapped[str | None] = mapped_column(sa.Text)
    object_count: Mapped[int] = mapped_column(server_default="0")
    row_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    byte_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    min_record_timestamp: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    max_record_timestamp: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    manifest_sha256: Mapped[str | None] = mapped_column(sa.CHAR(64))
    created_by: Mapped[str] = mapped_column(sa.String(255))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(sa.String(255))
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ArchiveObject(V1Base):
    __tablename__ = "archive_objects"
    __table_args__ = {"schema": "operations"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    archive_manifest_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("operations.archive_manifests.id", ondelete="RESTRICT"),
    )
    sequence_number: Mapped[int]
    partition_label: Mapped[str | None] = mapped_column(sa.String(255))
    storage_uri: Mapped[str] = mapped_column(sa.Text)
    content_type: Mapped[str] = mapped_column(sa.String(100))
    compression: Mapped[str] = mapped_column(sa.String(20))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="pending")
    row_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    byte_count: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    min_record_timestamp: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    max_record_timestamp: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    sha256: Mapped[str | None] = mapped_column(sa.CHAR(64))
    provider_etag: Mapped[str | None] = mapped_column(sa.Text)
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class BackupSnapshot(V1Base):
    __tablename__ = "backup_snapshots"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    environment_name: Mapped[str] = mapped_column(sa.String(100))
    provider: Mapped[str] = mapped_column(sa.String(50))
    provider_snapshot_id: Mapped[str] = mapped_column(sa.String(255))
    backup_type: Mapped[str] = mapped_column(sa.String(30))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="requested")
    verification_status: Mapped[str] = mapped_column(sa.String(20), server_default="pending")
    postgres_version: Mapped[str] = mapped_column(sa.String(50))
    alembic_revision: Mapped[str] = mapped_column(sa.String(100))
    database_identifier: Mapped[str] = mapped_column(sa.String(255))
    recovery_point_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(sa.CHAR(64))
    storage_uri: Mapped[str | None] = mapped_column(sa.Text)
    encrypted: Mapped[bool] = mapped_column(server_default=sa.text("true"))
    encryption_method: Mapped[str | None] = mapped_column(sa.String(50))
    encryption_key_reference: Mapped[str | None] = mapped_column(sa.Text)
    retention_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(sa.String(255))
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class RestoreDrill(V1Base):
    __tablename__ = "restore_drills"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    backup_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("operations.backup_snapshots.id", ondelete="RESTRICT"),
    )
    environment_name: Mapped[str] = mapped_column(sa.String(100))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="pending")
    target_alembic_revision: Mapped[str] = mapped_column(sa.String(100))
    initiated_by: Mapped[str] = mapped_column(sa.String(255))
    rto_target_seconds: Mapped[int | None]
    rpo_target_seconds: Mapped[int | None]
    measured_restore_seconds: Mapped[int | None]
    measured_data_loss_seconds: Mapped[int | None]
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class RestoreDrillCheck(V1Base):
    __tablename__ = "restore_drill_checks"
    __table_args__ = {"schema": "operations"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    restore_drill_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("operations.restore_drills.id", ondelete="RESTRICT")
    )
    check_code: Mapped[str] = mapped_column(sa.String(100))
    category: Mapped[str] = mapped_column(sa.String(30))
    severity: Mapped[str] = mapped_column(sa.String(20), server_default="critical")
    required: Mapped[bool] = mapped_column(server_default=sa.text("true"))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="pending")
    expected_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    actual_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class MaintenanceRun(V1Base):
    __tablename__ = "maintenance_runs"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    run_type: Mapped[str] = mapped_column(sa.String(30))
    target_schema: Mapped[str | None] = mapped_column(sa.String(63))
    target_table: Mapped[str | None] = mapped_column(sa.String(63))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="pending")
    dry_run: Mapped[bool] = mapped_column(server_default=sa.text("false"))
    requested_by: Mapped[str] = mapped_column(sa.String(255))
    external_job_reference: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    rows_examined: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    rows_affected: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
    objects_affected: Mapped[int] = mapped_column(server_default="0")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class HealthCheckRun(V1Base):
    __tablename__ = "health_check_runs"
    __table_args__ = {"schema": "operations"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    suite_version: Mapped[str] = mapped_column(sa.String(100))
    environment_name: Mapped[str] = mapped_column(sa.String(100))
    scope: Mapped[str] = mapped_column(sa.String(30), server_default="full")
    status: Mapped[str] = mapped_column(sa.String(30), server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    passed_count: Mapped[int] = mapped_column(server_default="0")
    warning_count: Mapped[int] = mapped_column(server_default="0")
    failed_count: Mapped[int] = mapped_column(server_default="0")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class HealthCheckResult(V1Base):
    __tablename__ = "health_check_results"
    __table_args__ = {"schema": "operations"}
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    health_check_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("operations.health_check_runs.id", ondelete="RESTRICT")
    )
    check_code: Mapped[str] = mapped_column(sa.String(100))
    category: Mapped[str] = mapped_column(sa.String(30))
    severity: Mapped[str] = mapped_column(sa.String(20))
    status: Mapped[str] = mapped_column(sa.String(20))
    object_schema: Mapped[str | None] = mapped_column(sa.String(63))
    object_name: Mapped[str | None] = mapped_column(sa.String(255))
    metric_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(30, 6))
    metric_unit: Mapped[str | None] = mapped_column(sa.String(50))
    threshold_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(sa.Text)
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
