"""Focused PostgreSQL lifecycle tests for Migration 007 backup evidence."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from alembic import command

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Database V1 operations integration tests require PostgreSQL",
)


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL)
    yield value
    value.dispose()


def _verified_backup(connection: sa.Connection, suffix: str) -> UUID:
    backup_id = cast(
        UUID,
        connection.scalar(
            sa.text(
                """INSERT INTO operations.backup_snapshots (
                environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
                alembic_revision,database_identifier,recovery_point_at,started_at,finished_at,
                size_bytes,checksum_sha256,storage_uri,encryption_method,encryption_key_reference
                ) VALUES ('test','provider',:suffix,'logical','succeeded','16','20260728_0007',
                'database',now(),now()-interval '1 minute',now(),1,repeat('b',64),
                's3://bucket/backup','kms','kms://key/backup') RETURNING id"""
            ),
            {"suffix": suffix},
        ),
    )
    connection.execute(
        sa.text("SELECT operations.finalize_backup_snapshot_v1(:id, 'reviewer')"),
        {"id": backup_id},
    )
    return backup_id


@pytest.mark.parametrize(
    "statement",
    [
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier,started_at) VALUES
        ('test','provider','bad-requested-time','logical','requested','16','20260728_0007','database',now())""",
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier,finished_at) VALUES
        ('test','provider','bad-requested-finish','logical','requested','16','007','database',now())""",
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier) VALUES
        ('test','provider','bad-running-start','logical','running','16','007','database')""",
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier,started_at,finished_at) VALUES
        ('test','provider','bad-running-finish','logical','running','16','007','database',now(),now())""",
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier,recovery_point_at,finished_at) VALUES
        ('test','provider','bad-success-start','logical','succeeded','16','007','database',now(),now())""",
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier,recovery_point_at,started_at) VALUES
        ('test','provider','bad-success-finish','logical','succeeded','16','007','database',now(),now())""",
        """INSERT INTO operations.backup_snapshots
        (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
        alembic_revision,database_identifier,error_message,finished_at) VALUES
        ('test','provider','bad-failed-start','logical','failed','16','007','database','error',now())""",
    ],
)
def test_backup_timestamp_matrix_rejects_invalid_rows(engine: sa.Engine, statement: str) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text(statement))


def test_verified_backup_expiry_and_deletion_preserve_all_evidence(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        backup_id = _verified_backup(connection, "verified-expiry")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text("SET LOCAL ROLE service_role"))
        connection.execute(
            sa.text(
                """UPDATE operations.backup_snapshots
                SET status='expired', storage_uri='s3://bucket/changed' WHERE id=:id"""
            ),
            {"id": backup_id},
        )
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE operations.backup_snapshots SET status='expired' WHERE id=:id"),
            {"id": backup_id},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """UPDATE operations.backup_snapshots
                SET status='deleted', metadata_json=jsonb_build_object('changed', true)
                WHERE id=:id"""
            ),
            {"id": backup_id},
        )
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE operations.backup_snapshots SET status='deleted' WHERE id=:id"),
            {"id": backup_id},
        )


def test_backup_rejects_direct_succeeded_to_deleted(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        backup_id = _verified_backup(connection, "no-direct-delete")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE operations.backup_snapshots SET status='deleted' WHERE id=:id"),
            {"id": backup_id},
        )


@pytest.mark.parametrize(
    ("initial_status", "initial_times", "new_status", "new_times"),
    [
        ("requested", "", "expired", ",started_at=now(),finished_at=now()"),
        ("running", ",started_at", "expired", ",finished_at=now()"),
        ("running", ",started_at", "requested", ",started_at=NULL"),
        (
            "succeeded",
            ",recovery_point_at,started_at,finished_at",
            "running",
            ",finished_at=NULL",
        ),
        (
            "failed",
            ",started_at,finished_at,error_message",
            "running",
            ",finished_at=NULL",
        ),
    ],
)
def test_backup_rejects_invalid_lifecycle_transitions(
    engine: sa.Engine,
    initial_status: str,
    initial_times: str,
    new_status: str,
    new_times: str,
) -> None:
    values = {
        "": "",
        ",started_at": ",now()",
        ",recovery_point_at,started_at,finished_at": ",now(),now(),now()",
        ",started_at,finished_at,error_message": ",now(),now(),'error'",
    }
    suffix = uuid4().hex
    with engine.begin() as connection:
        backup = connection.scalar(
            sa.text(
                f"""INSERT INTO operations.backup_snapshots
                (environment_name,provider,provider_snapshot_id,backup_type,status,
                 postgres_version,alembic_revision,database_identifier,encrypted{initial_times})
                VALUES ('test','provider',:suffix,'logical',:status,'16','007','database'
                        ,false{values[initial_times]}) RETURNING id"""
            ),
            {"suffix": suffix, "status": initial_status},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text("SET LOCAL ROLE service_role"))
        connection.execute(
            sa.text(
                f"""UPDATE operations.backup_snapshots
                SET status=:status{new_times} WHERE id=:id"""
            ),
            {"status": new_status, "id": backup},
        )


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "postgresql://database",
        "s3://user@bucket/object",
        "s3://bucket/object?token=value",
        "s3://bucket/object#fragment",
        "s3://bucket/password=value",
        "s3://bucket/sk-secretvalue",
        "s3://bucket/eyJtokenvalue",
        "s3://bucket/-----BEGIN-private",
    ],
)
def test_backup_rejects_unsafe_storage_and_key_locations(
    engine: sa.Engine, unsafe_value: str
) -> None:
    for column in ("storage_uri", "encryption_key_reference"):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                sa.text(
                    f"""INSERT INTO operations.backup_snapshots
                    (environment_name,provider,provider_snapshot_id,backup_type,status,
                     postgres_version,alembic_revision,database_identifier,encryption_method,
                     {column}) VALUES ('test','provider',:suffix,'logical','requested','16',
                     '007','database','kms',:value)"""
                ),
                {"suffix": uuid4().hex, "value": unsafe_value},
            )


def test_backup_finalizer_rejects_missing_and_unencrypted_evidence(engine: sa.Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("SELECT operations.finalize_backup_snapshot_v1(:id,'reviewer')"),
            {"id": uuid4()},
        )
    with engine.begin() as connection:
        backup = connection.scalar(
            sa.text(
                """INSERT INTO operations.backup_snapshots
                (environment_name,provider,provider_snapshot_id,backup_type,status,
                 postgres_version,alembic_revision,database_identifier,recovery_point_at,
                 started_at,finished_at,size_bytes,checksum_sha256,storage_uri,encrypted)
                VALUES ('test','provider',:suffix,'logical','succeeded','16','20260728_0007',
                        'database',now(),now(),now(),1,repeat('a',64),'s3://bucket/plain',false)
                RETURNING id"""
            ),
            {"suffix": uuid4().hex},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("SELECT operations.finalize_backup_snapshot_v1(:id,'reviewer')"),
            {"id": backup},
        )


MANDATORY_RESTORE_CHECKS = (
    "alembic_revision",
    "schema_inventory",
    "row_count_baseline",
    "foreign_key_constraints",
    "api_contract",
    "security_grants_rls",
    "sample_query_smoke",
    "backup_checksum",
)


@pytest.mark.parametrize("missing_code", MANDATORY_RESTORE_CHECKS)
def test_restore_finalizer_requires_each_mandatory_check(
    engine: sa.Engine, missing_code: str
) -> None:
    with engine.begin() as connection:
        backup = _verified_backup(connection, f"missing-{missing_code}-{uuid4().hex}")
        drill = connection.scalar(
            sa.text(
                """INSERT INTO operations.restore_drills
                (backup_snapshot_id,environment_name,status,target_alembic_revision,initiated_by,
                 measured_restore_seconds,started_at)
                VALUES (:backup,'test','running','20260728_0007','test',10,now()) RETURNING id"""
            ),
            {"backup": backup},
        )
        for code in MANDATORY_RESTORE_CHECKS:
            if code == missing_code:
                continue
            actual = (
                {"revision": "20260728_0007"}
                if code == "alembic_revision"
                else {"checksum": "b" * 64}
                if code == "backup_checksum"
                else {}
            )
            connection.execute(
                sa.text(
                    """INSERT INTO operations.restore_drill_checks
                    (restore_drill_id,check_code,category,severity,required,status,actual_json,
                     finished_at) VALUES (:drill,:code,'migration','critical',true,'passed',
                     CAST(:actual AS jsonb),now())"""
                ),
                {"drill": drill, "code": code, "actual": json.dumps(actual)},
            )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("SELECT operations.finalize_restore_drill_v1(:drill)"), {"drill": drill}
        )


@pytest.mark.parametrize(
    ("bad_code", "bad_actual"),
    [
        ("alembic_revision", '{"revision":"wrong"}'),
        ("backup_checksum", '{"checksum":"wrong"}'),
    ],
)
def test_restore_finalizer_rejects_revision_and_checksum_mismatch(
    engine: sa.Engine, bad_code: str, bad_actual: str
) -> None:
    with engine.begin() as connection:
        backup = _verified_backup(connection, f"mismatch-{bad_code}-{uuid4().hex}")
        drill = connection.scalar(
            sa.text(
                """INSERT INTO operations.restore_drills
                (backup_snapshot_id,environment_name,status,target_alembic_revision,initiated_by,
                 measured_restore_seconds,started_at)
                VALUES (:backup,'test','running','20260728_0007','test',10,now()) RETURNING id"""
            ),
            {"backup": backup},
        )
        for code in MANDATORY_RESTORE_CHECKS:
            actual = (
                bad_actual
                if code == bad_code
                else '{"revision":"20260728_0007"}'
                if code == "alembic_revision"
                else '{"checksum":"' + "b" * 64 + '"}'
                if code == "backup_checksum"
                else "{}"
            )
            connection.execute(
                sa.text(
                    """INSERT INTO operations.restore_drill_checks
                    (restore_drill_id,check_code,category,severity,required,status,actual_json,
                     finished_at) VALUES (:drill,:code,'migration','critical',true,'passed',
                     CAST(:actual AS jsonb),now())"""
                ),
                {"drill": drill, "code": code, "actual": actual},
            )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("SELECT operations.finalize_restore_drill_v1(:drill)"), {"drill": drill}
        )


def test_restore_check_mutation_serializes_with_finalizer(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        backup = _verified_backup(connection, "restore-concurrency")
        drill = connection.scalar(
            sa.text(
                """INSERT INTO operations.restore_drills
                (backup_snapshot_id,environment_name,status,target_alembic_revision,initiated_by,
                 measured_restore_seconds,started_at)
                VALUES (:backup,'test','running','20260728_0007','test',10,now()) RETURNING id"""
            ),
            {"backup": backup},
        )
        connection.execute(
            sa.text(
                """INSERT INTO operations.restore_drill_checks
                (restore_drill_id,check_code,category,severity,required,status,actual_json,finished_at)
                SELECT :drill,code,'migration','critical',true,'passed',
                       CASE WHEN code='alembic_revision'
                            THEN jsonb_build_object('revision','20260728_0007')
                            ELSE '{}'::jsonb END,now()
                FROM unnest(ARRAY['alembic_revision','schema_inventory','row_count_baseline',
                  'foreign_key_constraints','api_contract','security_grants_rls',
                  'sample_query_smoke']) AS code"""
            ),
            {"drill": drill},
        )
        checksum_check = connection.scalar(
            sa.text(
                """INSERT INTO operations.restore_drill_checks
                (restore_drill_id,check_code,category,severity,required,status)
                VALUES (:drill,'backup_checksum','backup','critical',true,'pending') RETURNING id"""
            ),
            {"drill": drill},
        )
    drill_locked = Event()

    def pass_checksum_check() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text(
                    """UPDATE operations.restore_drill_checks
                    SET status='passed',actual_json=jsonb_build_object('checksum',repeat('b',64)),
                        finished_at=now() WHERE id=:check"""
                ),
                {"check": checksum_check},
            )
            drill_locked.set()
            time.sleep(0.3)
            transaction.commit()

    def finalize() -> str:
        assert drill_locked.wait(2)
        with engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            return str(
                connection.scalar(
                    sa.text("SELECT (operations.finalize_restore_drill_v1(:drill)).status"),
                    {"drill": drill},
                )
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        check_future = executor.submit(pass_checksum_check)
        finalizer_future = executor.submit(finalize)
        check_future.result(timeout=6)
        assert finalizer_future.result(timeout=6) == "succeeded"
