"""PostgreSQL health, readiness, and index tests for Migration 007."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event

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

BRIN_INDEXES = {
    "ix_job_observations__observed_at_brin",
    "ix_job_status_events__event_at_brin",
    "ix_job_change_events__detected_at_brin",
    "ix_job_repost_events__detected_at_brin",
    "ix_data_quality_issues__detected_at_brin",
    "ix_fact_job_observations__loaded_at_brin",
    "ix_fact_salary_observations__loaded_at_brin",
}
PARTIAL_INDEXES = {
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


@pytest.mark.parametrize(
    ("result_status", "severity", "expected"),
    [
        ("passed", "critical", "passed"),
        ("warning", "warning", "passed_with_warnings"),
        ("failed", "critical", "failed"),
    ],
)
def test_health_finalizer_calculates_outcome(
    engine: sa.Engine, result_status: str, severity: str, expected: str
) -> None:
    with engine.begin() as connection:
        run = connection.scalar(
            sa.text(
                """INSERT INTO operations.health_check_runs
                (suite_version,environment_name,status,started_at)
                VALUES ('matrix-v1','test','running',now()) RETURNING id"""
            )
        )
        connection.execute(
            sa.text(
                """INSERT INTO operations.health_check_results
                (health_check_run_id,check_code,category,severity,status,message)
                VALUES (:run,:code,'security',:severity,:status,:message)"""
            ),
            {
                "run": run,
                "code": f"check-{result_status}",
                "severity": severity,
                "status": result_status,
                "message": "failure" if result_status == "failed" else None,
            },
        )
        connection.execute(
            sa.text("SELECT operations.finalize_health_check_run_v1(:run)"), {"run": run}
        )
        assert (
            connection.scalar(
                sa.text("SELECT status FROM operations.health_check_runs WHERE id=:run"),
                {"run": run},
            )
            == expected
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """UPDATE operations.health_check_results SET message='changed'
                WHERE health_check_run_id=:run"""
            ),
            {"run": run},
        )


def test_health_result_mutation_serializes_with_finalizer(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        run = connection.scalar(
            sa.text(
                """INSERT INTO operations.health_check_runs
                (suite_version,environment_name,status,started_at)
                VALUES ('concurrency-v1','test','running',now()) RETURNING id"""
            )
        )
        result = connection.scalar(
            sa.text(
                """INSERT INTO operations.health_check_results
                (health_check_run_id,check_code,category,severity,status)
                VALUES (:run,'concurrent-result','security','warning','warning') RETURNING id"""
            ),
            {"run": run},
        )
    child_locked = Event()

    def pass_result() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text(
                    """UPDATE operations.health_check_results
                    SET status='passed' WHERE id=:result"""
                ),
                {"result": result},
            )
            child_locked.set()
            time.sleep(0.3)
            transaction.commit()

    def finalize() -> int:
        assert child_locked.wait(2)
        with engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            connection.execute(
                sa.text("SELECT operations.finalize_health_check_run_v1(:run)"), {"run": run}
            )
            return int(
                connection.scalar(
                    sa.text("SELECT passed_count FROM operations.health_check_runs WHERE id=:run"),
                    {"run": run},
                )
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        insert_future = executor.submit(pass_result)
        finalize_future = executor.submit(finalize)
        insert_future.result(timeout=6)
        assert finalize_future.result(timeout=6) == 1


def test_all_readiness_and_catalog_views_execute(engine: sa.Engine) -> None:
    views = (
        "v_security_privilege_violations",
        "v_unindexed_foreign_keys",
        "v_table_storage_health",
        "v_data_freshness",
        "v_backup_restore_readiness",
        "v_retention_readiness",
        "v_release_readiness",
    )
    with engine.connect() as connection:
        for view in views:
            connection.execute(sa.text(f"SELECT * FROM operations.{view} LIMIT 1")).all()


def test_seven_brin_indexes_are_valid_and_configured(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """SELECT index_relation.relname, access_method.amname, catalog_index.indisvalid,
                          index_relation.reloptions
                FROM pg_index AS catalog_index
                JOIN pg_class AS index_relation ON index_relation.oid=catalog_index.indexrelid
                JOIN pg_am AS access_method ON access_method.oid=index_relation.relam
                WHERE index_relation.relname = ANY(:names)"""
            ),
            {"names": list(BRIN_INDEXES)},
        ).all()
    assert {row[0] for row in rows} == BRIN_INDEXES
    assert all(row[1] == "brin" and row[2] for row in rows)
    assert all("pages_per_range=128" in (row[3] or []) for row in rows)


def test_four_partial_indexes_have_exact_predicates(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        result = connection.execute(
            sa.text(
                """SELECT index_relation.relname,
                              pg_get_expr(catalog_index.indpred,catalog_index.indrelid)
                    FROM pg_index AS catalog_index
                    JOIN pg_class AS index_relation ON index_relation.oid=catalog_index.indexrelid
                    WHERE index_relation.relname = ANY(:names)
                      AND catalog_index.indpred IS NOT NULL"""
            ),
            {"names": list(PARTIAL_INDEXES)},
        ).all()
        rows: dict[str, str] = {str(row[0]): str(row[1]) for row in result}

    def normalize_predicate(predicate: str) -> str:
        normalized = predicate.lower().replace("::character varying", "").replace("::text", "")
        normalized = re.sub(r"=\s*any\s*\(array\[(.*?)\]\[\]\)", r"in(\1)", normalized)
        return re.sub(r"[\s()\"]", "", normalized)

    normalized = {name: normalize_predicate(predicate) for name, predicate in rows.items()}
    assert normalized == {
        "ix_data_quality_issues__open_critical": (
            "statusin('open','acknowledged')andseverityin('error','critical')"
        ),
        "ix_job_search_documents__active_posted": "status='active'",
        "ix_analytics_refresh_runs__running": "status='running'",
        "ix_serving_refresh_runs__running": "status='running'",
    }
