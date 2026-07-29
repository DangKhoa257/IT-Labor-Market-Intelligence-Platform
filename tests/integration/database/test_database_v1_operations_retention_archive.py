"""PostgreSQL retention/archive state and locking tests for Migration 007."""

from __future__ import annotations

import os
from collections.abc import Iterator
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
