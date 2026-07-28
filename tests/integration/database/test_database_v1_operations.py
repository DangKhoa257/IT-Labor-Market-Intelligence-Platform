"""PostgreSQL integration tests for Database V1 Migration 007 operations contracts."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import DBAPIError, IntegrityError

from alembic import command

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Database V1 operations integration tests require PostgreSQL",
)

OPERATIONS_TABLES = {
    "partition_policies",
    "retention_policies",
    "retention_runs",
    "retention_run_items",
    "archive_manifests",
    "archive_objects",
    "backup_snapshots",
    "restore_drills",
    "restore_drill_checks",
    "maintenance_runs",
    "health_check_runs",
    "health_check_results",
}
OPERATIONS_VIEWS = {
    "v_security_privilege_violations",
    "v_unindexed_foreign_keys",
    "v_table_storage_health",
    "v_data_freshness",
    "v_backup_restore_readiness",
    "v_retention_readiness",
    "v_release_readiness",
}
OPERATIONS_FUNCTIONS = {
    "assert_security_baseline_v1",
    "authorize_retention_delete_v1",
    "finalize_archive_manifest_v1",
    "finalize_backup_snapshot_v1",
    "finalize_restore_drill_v1",
    "finalize_health_check_run_v1",
}
ADDITIVE_INDEXES = {
    "ix_job_observations__observed_at_brin",
    "ix_job_status_events__event_at_brin",
    "ix_job_change_events__detected_at_brin",
    "ix_job_repost_events__detected_at_brin",
    "ix_data_quality_issues__detected_at_brin",
    "ix_fact_job_observations__loaded_at_brin",
    "ix_fact_salary_observations__loaded_at_brin",
    "ix_data_quality_issues__open_critical",
    "ix_job_search_documents__active_posted",
    "ix_analytics_refresh_runs__running",
    "ix_serving_refresh_runs__running",
}


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL)
    yield value
    value.dispose()


def _reject(engine: sa.Engine, statement: str, **parameters: object) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text(statement), parameters)


def _backup(connection: sa.Connection, suffix: str) -> UUID:
    return connection.scalar(
        sa.text(
            """
            INSERT INTO operations.backup_snapshots (
                environment_name, provider, provider_snapshot_id, backup_type, status,
                postgres_version, alembic_revision, database_identifier, recovery_point_at,
                started_at, finished_at, size_bytes, checksum_sha256, storage_uri,
                encryption_method
            ) VALUES (
                'test', 'test-provider', :suffix, 'logical', 'succeeded', '16',
                '20260728_0007', 'test-db', now(), now() - interval '1 minute', now(),
                1, repeat('a', 64), 's3://test-bucket/backup', 'kms'
            ) RETURNING id
            """
        ),
        {"suffix": suffix},
    )


def test_inventory_security_baseline_and_additive_indexes(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names(schema="operations")) == OPERATIONS_TABLES
    assert set(inspector.get_view_names(schema="operations")) == OPERATIONS_VIEWS
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        assert revision == "20260728_0007"
        functions = set(
            connection.scalars(
                sa.text(
                    """SELECT proname FROM pg_proc
                    JOIN pg_namespace ON pg_namespace.oid=pronamespace
                    WHERE nspname='operations' AND proname = ANY(:names)"""
                ),
                {"names": list(OPERATIONS_FUNCTIONS)},
            )
        )
        assert functions == OPERATIONS_FUNCTIONS
        baseline = connection.execute(
            sa.text("SELECT operations.assert_security_baseline_v1()")
        ).scalar()
        assert baseline == ""
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM pg_policies WHERE schemaname='operations'")
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.text(
                    """SELECT count(*) FROM pg_class AS relation JOIN pg_namespace AS namespace
                ON namespace.oid=relation.relnamespace WHERE namespace.nspname='operations'
                AND relation.relkind='r' AND NOT relation.relispartition"""
                )
            )
            == 12
        )
        index_names = set(
            connection.scalars(
                sa.text("SELECT indexname FROM pg_indexes WHERE indexname = ANY(:names)"),
                {"names": list(ADDITIVE_INDEXES)},
            )
        )
        assert index_names == ADDITIVE_INDEXES
        assert connection.scalar(sa.text("SELECT count(*) FROM operations.partition_policies")) == 6


def test_security_baseline_detects_transient_unsafe_grant(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text("GRANT SELECT ON operations.partition_policies TO anon"))
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM operations.v_security_privilege_violations")
                )
                > 0
            )
            with pytest.raises(DBAPIError) as error:
                connection.execute(sa.text("SELECT operations.assert_security_baseline_v1()"))
            assert getattr(error.value.orig, "sqlstate", None) == "23514"
        finally:
            transaction.rollback()


def test_partition_and_retention_policy_guards(engine: sa.Engine) -> None:
    _reject(
        engine,
        """INSERT INTO operations.partition_policies
        (target_schema,target_table,partition_key,activation_row_threshold,rationale)
        VALUES ('history','job_observations','not_a_column',100,'test')""",
    )
    _reject(
        engine,
        """INSERT INTO operations.retention_policies
        (policy_code,target_schema,target_table,record_class,time_column,delete_after_days,
         policy_version,created_by,enabled)
        VALUES (
            'bad-window','history','job_observations','other','observed_at',-1,'v1','test',false
        )""",
    )
    _reject(
        engine,
        """INSERT INTO operations.retention_policies
        (policy_code,target_schema,target_table,record_class,time_column,delete_after_days,
         policy_version,created_by,enabled)
        VALUES (
            'unapproved-enabled','history','job_observations','other','observed_at',1,'v1','test',true
        )""",
    )


def test_backup_finalizer_immutability_and_health_finalizer(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        backup_id = _backup(connection, "backup-finalizer")
        connection.execute(
            sa.text("SELECT operations.finalize_backup_snapshot_v1(:id, 'reviewer')"),
            {"id": backup_id},
        )
        assert (
            connection.scalar(
                sa.text("SELECT verification_status FROM operations.backup_snapshots WHERE id=:id"),
                {"id": backup_id},
            )
            == "verified"
        )
        health_id = connection.scalar(
            sa.text(
                """INSERT INTO operations.health_check_runs
                (suite_version,environment_name,status,started_at)
                VALUES ('v1','test','running',now()) RETURNING id"""
            )
        )
        connection.execute(
            sa.text(
                """INSERT INTO operations.health_check_results
                (health_check_run_id,check_code,category,severity,status,finished_at)
                VALUES (:id,'security','security','critical','passed',now())"""
            ),
            {"id": health_id},
        )
        connection.execute(
            sa.text("SELECT operations.finalize_health_check_run_v1(:id)"), {"id": health_id}
        )
        assert (
            connection.scalar(
                sa.text("SELECT status FROM operations.health_check_runs WHERE id=:id"),
                {"id": health_id},
            )
            == "passed"
        )
    _reject(
        engine,
        """UPDATE operations.backup_snapshots SET provider='changed'
        WHERE provider_snapshot_id='backup-finalizer'""",
    )


def test_backup_finalization_serializes_concurrent_mutation(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        backup_id = _backup(connection, "backup-concurrency")
    ready = Event()

    def finalize() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(
                sa.text("SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='5s'")
            )
            connection.execute(
                sa.text("SELECT operations.finalize_backup_snapshot_v1(:id, 'reviewer')"),
                {"id": backup_id},
            )
            ready.set()
            # The concurrent UPDATE must wait on this row lock until commit.
            time.sleep(0.3)
            transaction.commit()

    def mutate() -> str:
        assert ready.wait(2)
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(
                sa.text("SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='5s'")
            )
            with pytest.raises(DBAPIError) as error:
                connection.execute(
                    sa.text(
                        "UPDATE operations.backup_snapshots SET provider='changed' WHERE id=:id"
                    ),
                    {"id": backup_id},
                )
            transaction.rollback()
            return str(getattr(error.value.orig, "sqlstate", ""))

    with ThreadPoolExecutor(max_workers=2) as executor:
        finalizer = executor.submit(finalize)
        mutation = executor.submit(mutate)
        assert finalizer.result(timeout=5) is None
        assert mutation.result(timeout=5) == "23514"


def test_downgrade_and_reupgrade_preserve_prior_api(engine: sa.Engine) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "20260727_0006")
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT to_regclass('operations.partition_policies')"))
                is None
            )
            assert (
                connection.scalar(
                    sa.text(
                        """SELECT count(*) FROM pg_proc AS function
                        JOIN pg_namespace AS namespace ON namespace.oid=function.pronamespace
                        WHERE namespace.nspname='api' AND function.proname='search_jobs_v1'"""
                    )
                )
                == 1
            )
    finally:
        command.upgrade(config, "head")
    with engine.connect() as connection:
        baseline = connection.execute(
            sa.text("SELECT operations.assert_security_baseline_v1()")
        ).scalar()
        assert baseline == ""
