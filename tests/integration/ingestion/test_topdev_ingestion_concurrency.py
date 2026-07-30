"""Two-connection PostgreSQL concurrency guarantees for ingestion."""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from it_labor_market_intelligence.adapters.base import FetchResult
from it_labor_market_intelligence.adapters.topdev import TOPDEV_IT_LISTING
from it_labor_market_intelligence.ingestion.cli import (
    CLIRejected,
    PostgreSQLCLIService,
    PostgreSQLLiveSourceLease,
    RunPlan,
)
from it_labor_market_intelligence.ingestion.repositories import claim_due_task, upsert_raw_object
from it_labor_market_intelligence.ingestion.runner import (
    FetchEvidence,
    PlannedTask,
    PostgreSQLRunnerStore,
    RunConfiguration,
)

FIXTURE_DIR = Path("tests/fixtures/topdev")

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
                SELECT source.id, policy.id, parser.id, parser.version, parser.schema_version,
                       policy.policy_version, policy.minimum_request_interval_seconds,
                       policy.maximum_requests_per_run, policy.maximum_concurrent_requests,
                       policy.approved_paths, policy.blocked_paths,
                       policy.raw_retention_days, policy.description_retention_days,
                       policy.allow_raw_storage, policy.allow_description_storage
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
        policy_version=str(row[5]),
        minimum_request_interval_seconds=float(row[6]),
        maximum_requests_per_run=int(row[7]),
        maximum_concurrent_requests=int(row[8]),
        approved_paths=tuple(cast(list[str], row[9])),
        blocked_paths=tuple(cast(list[str], row[10])),
        raw_retention_days=cast(int | None, row[11]),
        description_retention_days=cast(int | None, row[12]),
        allow_raw_storage=bool(row[13]),
        allow_description_storage=bool(row[14]),
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
    base = datetime(2026, 7, 30, tzinfo=UTC)
    expiries = (base + timedelta(days=10), base + timedelta(days=90))

    def upsert(expires_at: datetime) -> int:
        with engine.begin() as connection:
            _set_timeouts(connection)
            barrier.wait(timeout=5)
            return upsert_raw_object(
                connection,
                sha256,
                len(body),
                "tests/fixtures/topdev/job_active.html",
                expires_at,
                mime_type="text/html",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        raw_ids = list(executor.map(upsert, expiries))

    assert raw_ids[0] == raw_ids[1]
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.raw_objects WHERE sha256=:sha256"),
                {"sha256": sha256},
            )
            == 1
        )
        assert connection.scalar(
            sa.text("SELECT expires_at FROM ingestion.raw_objects WHERE sha256=:sha256"),
            {"sha256": sha256},
        ) == max(expiries)


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


class _ConcurrencyLiveTransport:
    def __init__(self, fetched_at: datetime, *, fail: bool = False) -> None:
        self.fetched_at = fetched_at
        self.fail = fail
        self.calls: list[str] = []
        self.redirect_validator: Any = None

    def set_redirect_validator(self, validator: Any) -> None:
        self.redirect_validator = validator

    def __call__(self, url: str) -> FetchResult:
        self.calls.append(url)
        if self.fail:
            raise RuntimeError("EXAMPLE_NOT_REAL_DATA live transport failure")
        return FetchResult(url, 200, b"<html></html>", self.fetched_at, "text/html")


def _live_plan(configuration: RunConfiguration) -> RunPlan:
    return RunPlan(
        replace(
            configuration,
            mode="live",
            run_type="manual",
            trigger_type="manual",
        ),
        source_enabled=True,
        policy_approved=True,
        policy_maximum=configuration.maximum_requests_per_run,
        fixture_dir=None,
    )


def test_live_source_lease_rejects_second_process_before_run_or_transport(
    engine: sa.Engine,
) -> None:
    configuration = _configuration(engine)
    plan = _live_plan(configuration)
    transport = _ConcurrencyLiveTransport(datetime.now(UTC))
    service = PostgreSQLCLIService(engine, live_transport_factory=lambda _: transport)

    with PostgreSQLLiveSourceLease.acquire(engine, configuration.source_id):
        with pytest.raises(CLIRejected, match="source lease"):
            service.execute_run(plan)

    assert transport.calls == []
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM ingestion.crawl_runs")) == 0


def test_live_source_lease_releases_after_exception(engine: sa.Engine) -> None:
    configuration = _configuration(engine)
    plan = _live_plan(configuration)

    def broken_factory(_: float) -> _ConcurrencyLiveTransport:
        raise RuntimeError("EXAMPLE_NOT_REAL_DATA factory failure")

    with pytest.raises(RuntimeError, match="factory failure"):
        PostgreSQLCLIService(engine, live_transport_factory=broken_factory).execute_run(plan)

    with PostgreSQLLiveSourceLease.acquire(engine, configuration.source_id):
        pass


def test_subsequent_live_run_waits_from_prior_persisted_fetch(engine: sa.Engine) -> None:
    configuration = replace(_configuration(engine), minimum_request_interval_seconds=10.0)
    store = PostgreSQLRunnerStore(engine)
    prior_fetch_at = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
    run_id = store.create_run(configuration, prior_fetch_at)
    discovery_task = store.discovery_task_id(run_id)
    store.persist_fetch(
        run_id,
        discovery_task,
        configuration.source_id,
        None,
        FetchEvidence(
            requested_url=TOPDEV_IT_LISTING,
            resolved_url=TOPDEV_IT_LISTING,
            http_status=200,
            content_type="text/html",
            response_bytes=0,
            duration_ms=0,
            attempt_number=1,
            outcome="success",
            fetched_at=prior_fetch_at,
        ),
        None,
    )
    store.complete_discovery(run_id, [])
    store.finalize_run(run_id, prior_fetch_at)

    waits: list[float] = []
    now = prior_fetch_at + timedelta(seconds=3)
    transport = _ConcurrencyLiveTransport(now)
    result = PostgreSQLCLIService(
        engine,
        now=lambda: now,
        sleep=waits.append,
        live_transport_factory=lambda _: transport,
    ).execute_run(_live_plan(configuration))

    assert waits == [7.0]
    assert transport.calls == [TOPDEV_IT_LISTING]
    assert result.status == "failed"


def test_fixture_execution_does_not_acquire_live_source_lease(engine: sa.Engine) -> None:
    configuration = _configuration(engine)
    plan = RunPlan(
        configuration,
        source_enabled=True,
        policy_approved=True,
        policy_maximum=configuration.maximum_requests_per_run,
        fixture_dir=FIXTURE_DIR,
    )

    with PostgreSQLLiveSourceLease.acquire(engine, configuration.source_id):
        result = PostgreSQLCLIService(engine).execute_run(plan)

    assert result.status == "succeeded"
