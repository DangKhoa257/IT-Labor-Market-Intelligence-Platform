"""Two-connection PostgreSQL concurrency guarantees for ingestion."""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from it_labor_market_intelligence.adapters.topdev import TOPDEV_IT_LISTING
from it_labor_market_intelligence.ingestion.cli import PostgreSQLCLIService
from it_labor_market_intelligence.ingestion.repositories import claim_due_task, upsert_raw_object
from it_labor_market_intelligence.ingestion.runner import (
    PlannedTask,
    PostgreSQLRunnerStore,
    RunConfiguration,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="ingestion concurrency tests require a real PostgreSQL database",
)


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL, pool_size=5, max_overflow=0, pool_pre_ping=True)
    yield value
    value.dispose()


@pytest.fixture(autouse=True)
def clean_ingestion(engine: sa.Engine) -> Iterator[None]:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                TRUNCATE TABLE
                    ingestion.crawl_errors, ingestion.extracted_records,
                    ingestion.extraction_runs, ingestion.fetch_events,
                    ingestion.raw_objects, ingestion.crawl_tasks,
                    ingestion.crawl_runs, ingestion.parser_versions,
                    ingestion.source_policies, ingestion.sources
                RESTART IDENTITY CASCADE
                """
            )
        )
    yield


def _configuration(engine: sa.Engine) -> RunConfiguration:
    service = PostgreSQLCLIService(engine, git_commit_sha="1234567")
    service.bootstrap_topdev(False)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE ingestion.source_policies SET
                    robots_review_status='approved', terms_review_status='approved',
                    reviewed_by='concurrency-test', reviewed_at=now()
                """
            )
        )
    service.bootstrap_topdev(True)
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT source.id, policy.id, parser.id, parser.version, parser.schema_version
                FROM ingestion.sources AS source
                JOIN ingestion.source_policies AS policy ON policy.source_id=source.id
                JOIN ingestion.parser_versions AS parser
                  ON parser.source_id=source.id AND parser.is_active
                WHERE source.slug='topdev'
                """
            )
        ).one()
    return RunConfiguration(
        source_id=cast(UUID, row[0]),
        source_slug="topdev",
        source_policy_id=cast(UUID, row[1]),
        parser_version_id=cast(UUID, row[2]),
        requested_limit=1,
        discovery_url=TOPDEV_IT_LISTING,
        mode="fixture",
        run_type="test",
        trigger_type="test",
        parser_version=str(row[3]),
        record_schema_version=str(row[4]),
    )


def _set_timeouts(connection: sa.Connection) -> None:
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text("SET LOCAL statement_timeout = '10s'"))


def test_two_connections_upserting_identical_bytes_reuse_one_raw_object(
    engine: sa.Engine,
) -> None:
    body = b"EXAMPLE_NOT_REAL_DATA concurrent immutable bytes"
    sha256 = hashlib.sha256(body).hexdigest()
    barrier = threading.Barrier(2)

    def upsert() -> int:
        with engine.begin() as connection:
            _set_timeouts(connection)
            barrier.wait(timeout=5)
            return upsert_raw_object(
                connection,
                sha256,
                len(body),
                "tests/fixtures/topdev/job_active.html",
                datetime.now(UTC) + timedelta(days=30),
                mime_type="text/html",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        raw_ids = list(executor.map(lambda _: upsert(), range(2)))

    assert raw_ids[0] == raw_ids[1]
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.raw_objects WHERE sha256=:sha256"),
                {"sha256": sha256},
            )
            == 1
        )


def test_two_connections_claiming_one_task_have_one_successful_claim(
    engine: sa.Engine,
) -> None:
    configuration = _configuration(engine)
    store = PostgreSQLRunnerStore(engine)
    run_id = store.create_run(configuration, datetime.now(UTC))
    store.complete_discovery(
        run_id,
        [
            PlannedTask(
                requested_url="https://topdev.vn/viec-lam/concurrent-fixture-3100099",
                source_job_id="3100099",
                discovery_method="fixture",
            )
        ],
    )
    barrier = threading.Barrier(2)

    def claim() -> sa.Row[Any] | None:
        with engine.begin() as connection:
            _set_timeouts(connection)
            barrier.wait(timeout=5)
            return claim_due_task(connection, run_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim(), range(2)))

    assert sum(item is not None for item in claims) == 1
    with engine.connect() as connection:
        task = connection.execute(
            sa.text(
                """
                SELECT status, attempt_count FROM ingestion.crawl_tasks
                WHERE crawl_run_id=:run_id AND task_type='detail_page'
                """
            ),
            {"run_id": run_id},
        ).one()
    assert tuple(task) == ("running", 1)
