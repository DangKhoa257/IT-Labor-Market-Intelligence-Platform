"""PostgreSQL retention/archive state and locking tests for Migration 007."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import cast
from uuid import UUID

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


def _authorized_run(connection: sa.Connection, item_count: int = 1) -> tuple[UUID, list[int]]:
    policy = cast(
        UUID,
        connection.scalar(
            sa.text(
                """INSERT INTO operations.retention_policies
                (policy_code,target_schema,target_table,record_class,time_column,
                 delete_after_days,requires_archive,enabled,policy_version,created_by,
                 approved_by,approved_at)
                VALUES ('matrix-no-archive','history','job_observations','other','observed_at',
                        30,false,true,'v1','test','reviewer',now())
                ON CONFLICT (policy_code) DO UPDATE SET updated_at=now() RETURNING id"""
            ),
        ),
    )
    run = cast(
        UUID,
        connection.scalar(
            sa.text(
                """INSERT INTO operations.retention_runs
                (policy_id,status,dry_run,cutoff_at,candidate_count,requested_by,started_at)
                VALUES (:policy,'running',false,now(),:count,'test',now()) RETURNING id"""
            ),
            {"policy": policy, "count": item_count},
        ),
    )
    ids = list(
        connection.scalars(
            sa.text(
                """INSERT INTO operations.retention_run_items
                (retention_run_id,target_record_key,record_timestamp)
                SELECT :run, 'record-' || value, now() FROM generate_series(1,:count) AS value
                RETURNING id"""
            ),
            {"run": run, "count": item_count},
        )
    )
    connection.execute(
        sa.text("SELECT operations.authorize_retention_delete_v1(:run,'reviewer')"),
        {"run": run},
    )
    return run, ids


def test_authorized_item_can_be_deleted_and_parent_can_succeed(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        run, items = _authorized_run(connection)
        connection.execute(
            sa.text("UPDATE operations.retention_run_items SET status='deleted' WHERE id=:id"),
            {"id": items[0]},
        )
        connection.execute(
            sa.text("UPDATE operations.retention_runs SET status='deleting' WHERE id=:run"),
            {"run": run},
        )
        connection.execute(
            sa.text(
                """UPDATE operations.retention_runs
                SET status='succeeded',deleted_count=1,finished_at=now() WHERE id=:run"""
            ),
            {"run": run},
        )


def test_authorized_item_can_be_deleted_while_parent_is_deleting(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        run, items = _authorized_run(connection)
        connection.execute(
            sa.text("UPDATE operations.retention_runs SET status='deleting' WHERE id=:run"),
            {"run": run},
        )
        connection.execute(
            sa.text("UPDATE operations.retention_run_items SET status='deleted' WHERE id=:id"),
            {"id": items[0]},
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "target_record_key='changed'",
        "record_timestamp=now()+interval '1 day'",
        "record_sha256=repeat('a',64)",
        "error_message='changed'",
    ],
)
def test_authorized_deletion_rejects_evidence_mutation(engine: sa.Engine, mutation: str) -> None:
    with engine.begin() as connection:
        _, items = _authorized_run(connection)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                f"""UPDATE operations.retention_run_items
                SET status='deleted',{mutation} WHERE id=:id"""
            ),
            {"id": items[0]},
        )


def test_insert_delete_and_status_jump_after_authorization_are_rejected(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        run, items = _authorized_run(connection)
    statements = (
        (
            """INSERT INTO operations.retention_run_items
            (retention_run_id,target_record_key,record_timestamp) VALUES (:run,'late',now())""",
            {"run": run},
        ),
        ("DELETE FROM operations.retention_run_items WHERE id=:id", {"id": items[0]}),
    )
    for statement, parameters in statements:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement), parameters)


def test_terminal_parent_rejects_all_item_mutation(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        run, items = _authorized_run(connection)
        connection.execute(
            sa.text("UPDATE operations.retention_run_items SET status='deleted' WHERE id=:id"),
            {"id": items[0]},
        )
        connection.execute(
            sa.text("UPDATE operations.retention_runs SET status='deleting' WHERE id=:run"),
            {"run": run},
        )
        connection.execute(
            sa.text(
                """UPDATE operations.retention_runs
                SET status='succeeded',deleted_count=1,finished_at=now() WHERE id=:run"""
            ),
            {"run": run},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE operations.retention_run_items SET updated_at=now() WHERE id=:id"),
            {"id": items[0]},
        )


def test_item_insert_serializes_with_retention_authorization(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        policy = connection.scalar(
            sa.text(
                "SELECT id FROM operations.retention_policies WHERE policy_code='matrix-no-archive'"
            )
        )
        run = connection.scalar(
            sa.text(
                """INSERT INTO operations.retention_runs
                (policy_id,status,dry_run,cutoff_at,candidate_count,requested_by,started_at)
                VALUES (:policy,'running',false,now(),1,'test',now()) RETURNING id"""
            ),
            {"policy": policy},
        )
    child_locked = Event()

    def insert_item() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text(
                    """INSERT INTO operations.retention_run_items
                    (retention_run_id,target_record_key,record_timestamp)
                    VALUES (:run,'concurrent-item',now())"""
                ),
                {"run": run},
            )
            child_locked.set()
            time.sleep(0.3)
            transaction.commit()

    def authorize() -> str:
        assert child_locked.wait(2)
        with engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            return str(
                connection.scalar(
                    sa.text(
                        "SELECT (operations.authorize_retention_delete_v1(:run,'reviewer')).status"
                    ),
                    {"run": run},
                )
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        child_future = executor.submit(insert_item)
        authorization_future = executor.submit(authorize)
        child_future.result(timeout=6)
        assert authorization_future.result(timeout=6) == "delete_authorized"


def test_legal_hold_update_serializes_with_retention_authorization(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        policy = connection.scalar(
            sa.text(
                """INSERT INTO operations.retention_policies
                (policy_code,target_schema,target_table,record_class,time_column,delete_after_days,
                 requires_archive,enabled,policy_version,created_by,approved_by,approved_at)
                VALUES ('concurrency-legal-hold','ingestion','fetch_events','operational_log',
                        'fetched_at',30,false,true,'v1','test','reviewer',now())
                ON CONFLICT (policy_code) DO UPDATE SET legal_hold=false,
                    legal_hold_reason=NULL,updated_at=now() RETURNING id"""
            )
        )
        run = connection.scalar(
            sa.text(
                """INSERT INTO operations.retention_runs
                (policy_id,status,dry_run,cutoff_at,candidate_count,requested_by,started_at)
                VALUES (:policy,'running',false,now(),1,'test',now()) RETURNING id"""
            ),
            {"policy": policy},
        )
        connection.execute(
            sa.text(
                """INSERT INTO operations.retention_run_items
                (retention_run_id,target_record_key,record_timestamp)
                VALUES (:run,'held-item',now())"""
            ),
            {"run": run},
        )
    policy_locked = Event()

    def apply_hold() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text(
                    """UPDATE operations.retention_policies
                    SET legal_hold=true,legal_hold_reason='review' WHERE id=:policy"""
                ),
                {"policy": policy},
            )
            policy_locked.set()
            time.sleep(0.3)
            transaction.commit()

    def authorize() -> str:
        assert policy_locked.wait(2)
        with pytest.raises(IntegrityError) as error, engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text("SELECT operations.authorize_retention_delete_v1(:run,'reviewer')"),
                {"run": run},
            )
        return str(getattr(error.value.orig, "sqlstate", ""))

    with ThreadPoolExecutor(max_workers=2) as executor:
        hold_future = executor.submit(apply_hold)
        authorization_future = executor.submit(authorize)
        hold_future.result(timeout=6)
        assert authorization_future.result(timeout=6) == "23514"


def test_archive_object_insert_serializes_with_manifest_finalizer(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        manifest = connection.scalar(
            sa.text(
                """INSERT INTO operations.archive_manifests
                (target_schema,target_table,archive_format,status,storage_provider,manifest_uri,
                 schema_revision,encryption_method,object_count,row_count,byte_count,
                 min_record_timestamp,max_record_timestamp,manifest_sha256,created_by,
                 started_at,completed_at)
                VALUES ('history','job_observations','parquet','written','test',
                        's3://bucket/concurrent-manifest','20260728_0007','none',1,1,1,
                        '2026-01-01 UTC','2026-01-01 UTC',repeat('a',64),'test',now(),now())
                RETURNING id"""
            )
        )
    manifest_locked = Event()

    def insert_object() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text(
                    """INSERT INTO operations.archive_objects
                    (archive_manifest_id,sequence_number,storage_uri,content_type,compression,
                     status,row_count,byte_count,min_record_timestamp,max_record_timestamp,
                     sha256,verified_at)
                    VALUES (:manifest,1,'s3://bucket/concurrent-object','application/parquet',
                            'none','verified',1,1,'2026-01-01 UTC','2026-01-01 UTC',
                            repeat('b',64),now())"""
                ),
                {"manifest": manifest},
            )
            manifest_locked.set()
            time.sleep(0.3)
            transaction.commit()

    def finalize() -> str:
        assert manifest_locked.wait(2)
        with engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            return str(
                connection.scalar(
                    sa.text(
                        """SELECT (operations.finalize_archive_manifest_v1(
                        :manifest,'reviewer')).status"""
                    ),
                    {"manifest": manifest},
                )
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        object_future = executor.submit(insert_object)
        finalizer_future = executor.submit(finalize)
        object_future.result(timeout=6)
        assert finalizer_future.result(timeout=6) == "verified"
