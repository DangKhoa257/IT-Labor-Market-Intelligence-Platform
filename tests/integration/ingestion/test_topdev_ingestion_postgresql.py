"""Real-PostgreSQL fixture ingestion tests; no live source access is permitted."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import NoResultFound

from alembic import command
from it_labor_market_intelligence.adapters.topdev import TOPDEV_IT_LISTING, extract_job_id
from it_labor_market_intelligence.ingestion.adapters.topdev_registration import (
    EnableRejected,
    TopDevRegistration,
)
from it_labor_market_intelligence.ingestion.cli import PostgreSQLCLIService
from it_labor_market_intelligence.ingestion.contracts import FixtureResponse, IngestionAdapter
from it_labor_market_intelligence.ingestion.errors import RetryDecision
from it_labor_market_intelligence.ingestion.runner import (
    CrawlErrorEvidence,
    ExtractionRecord,
    FetchEvidence,
    FixtureTransport,
    IngestionRunner,
    PlannedTask,
    PostgreSQLRunnerStore,
    RunConfiguration,
    RunResult,
    StoredFetch,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="ingestion integration tests require a real PostgreSQL database",
)

FIXTURE_DIR = Path("tests/fixtures/topdev")
ACTIVE_URL = "https://topdev.vn/viec-lam/fixture-active-engineer-3100001"
EXPIRED_URL = "https://topdev.vn/viec-lam/fixture-expired-engineer-3100002"
INVALID_URL = "https://topdev.vn/viec-lam/fixture-invalid-engineer-3100003"
NEGOTIABLE_URL = "https://topdev.vn/viec-lam/fixture-negotiable-engineer-3100004"


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL, pool_pre_ping=True)
    yield value
    value.dispose()


@pytest.fixture(autouse=True)
def clean_ingestion(engine: sa.Engine) -> Iterator[None]:
    _truncate(engine)
    yield
    _truncate(engine)


def _truncate(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                TRUNCATE TABLE
                    ingestion.crawl_errors,
                    ingestion.extracted_records,
                    ingestion.extraction_runs,
                    ingestion.fetch_events,
                    ingestion.raw_objects,
                    ingestion.crawl_tasks,
                    ingestion.crawl_runs,
                    ingestion.parser_versions,
                    ingestion.source_policies,
                    ingestion.sources
                RESTART IDENTITY CASCADE
                """
            )
        )


def _body(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def _listing(urls: Sequence[str]) -> bytes:
    links = "".join(f'<a href="{url}">EXAMPLE_NOT_REAL_DATA</a>' for url in urls)
    return f"<!doctype html><html><body>{links}</body></html>".encode()


def _response(
    url: str,
    fixture_name: str,
    *,
    status: int = 200,
    headers: Mapping[str, str] | None = None,
) -> FixtureResponse:
    return FixtureResponse(
        url=url,
        status=status,
        body=_body(fixture_name),
        fetched_at=datetime.now(UTC),
        content_type="text/html; charset=utf-8",
        headers=headers or {"Content-Type": "text/html; charset=utf-8"},
    )


def _bootstrap(
    engine: sa.Engine,
    *,
    raw_retention_days: int | None = 30,
    allow_raw_storage: bool = True,
    allow_description_storage: bool = True,
) -> RunConfiguration:
    service = PostgreSQLCLIService(engine, git_commit_sha="1234567")
    service.bootstrap_topdev(False)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE ingestion.source_policies SET
                    robots_review_status='approved', terms_review_status='approved',
                    reviewed_by='integration-test', reviewed_at=now(),
                    raw_retention_days=:retention,
                    allow_raw_storage=:allow_raw,
                    allow_description_storage=:allow_description,
                    notes='EXAMPLE_NOT_REAL_DATA approved fixture policy'
                WHERE policy_version='topdev-policy-v1'
                """
            ),
            {
                "retention": raw_retention_days,
                "allow_raw": allow_raw_storage,
                "allow_description": allow_description_storage,
            },
        )
    service.bootstrap_topdev(True)
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT source.id, policy.id, parser.id, parser.version,
                       parser.schema_version, policy.raw_retention_days,
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
        raw_retention_days=cast(int | None, row[5]),
        allow_raw_storage=bool(row[6]),
        allow_description_storage=bool(row[7]),
        git_commit_sha="1234567",
        parser_version=str(row[3]),
        record_schema_version=str(row[4]),
    )


def _run(
    engine: sa.Engine,
    configuration: RunConfiguration,
    urls: Sequence[str],
    detail_responses: Mapping[str, Sequence[FixtureResponse | Exception]],
    *,
    retry_policy: Callable[[int | None, int, int | None], RetryDecision] | None = None,
) -> tuple[UUID, RunResult]:
    listing = FixtureResponse(
        url=TOPDEV_IT_LISTING,
        status=200,
        body=_listing(urls),
        fetched_at=datetime.now(UTC),
        content_type="text/html",
    )
    responses: dict[str, Sequence[FixtureResponse | Exception]] = {
        TOPDEV_IT_LISTING: [listing],
        **detail_responses,
    }
    fixture_keys: dict[str, str | Sequence[str | None]] = {
        TOPDEV_IT_LISTING: "tests/fixtures/topdev/discovery_page_1.html"
    }
    for url, sequence in detail_responses.items():
        fixture_keys[url] = [
            _fixture_key_for_item(item) if isinstance(item, FixtureResponse) else None
            for item in sequence
        ]
    transport = FixtureTransport(responses, fixture_keys=fixture_keys)
    adapter = TopDevRegistration().adapter(transport)
    runner = IngestionRunner(
        adapter=cast(IngestionAdapter, adapter),
        store=PostgreSQLRunnerStore(engine),
        configuration=configuration,
        source_job_id_from_url=extract_job_id,
        transport_observer=transport,
        retry_policy=retry_policy,
    )
    result = runner.run()
    return result.run_id, result


def _fixture_key_for_item(response: FixtureResponse) -> str:
    for path in FIXTURE_DIR.glob("*.html"):
        if path.read_bytes() == response.body:
            return path.as_posix()
    raise AssertionError("fixture response bytes must come from tests/fixtures/topdev")


def replace_limit(configuration: RunConfiguration, limit: int) -> RunConfiguration:
    return replace(configuration, requested_limit=max(1, limit))


def test_bootstrap_idempotency_policy_preservation_enable_and_parser_rotation(
    engine: sa.Engine,
) -> None:
    service = PostgreSQLCLIService(engine, git_commit_sha="abcdef1")
    first = service.bootstrap_topdev(False)
    second = service.bootstrap_topdev(False)
    assert first.source_id == second.source_id
    assert first.source_enabled is second.source_enabled is False
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM ingestion.sources")) == 1
        assert connection.scalar(sa.text("SELECT count(*) FROM ingestion.source_policies")) == 1
        assert connection.scalar(sa.text("SELECT count(*) FROM ingestion.parser_versions")) == 1

    with pytest.raises(EnableRejected):
        service.bootstrap_topdev(True)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT is_enabled FROM ingestion.sources WHERE slug='topdev'")
            )
            is False
        )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE ingestion.source_policies SET
                    robots_review_status='approved', terms_review_status='approved',
                    reviewed_by='operator', reviewed_at=now(), notes='preserve-this-review'
                """
            )
        )
        connection.execute(sa.text("UPDATE ingestion.parser_versions SET is_active=false"))
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.parser_versions (
                    source_id, parser_name, version, schema_version, is_active
                ) VALUES (
                    :source_id, 'TopDevAdapter', 'topdev.v0',
                    'source-raw-job-record.v0', true
                )
                """
            ),
            {"source_id": first.source_id},
        )

    enabled = service.bootstrap_topdev(True)
    assert enabled.source_enabled is True
    with engine.connect() as connection:
        policy = connection.execute(
            sa.text(
                """
                SELECT notes, robots_review_status, terms_review_status
                FROM ingestion.source_policies
                """
            )
        ).one()
        assert tuple(policy) == ("preserve-this-review", "approved", "approved")
        parsers = connection.execute(
            sa.text(
                """
                SELECT version, is_active, retired_at, configuration_hash, git_commit_sha
                FROM ingestion.parser_versions ORDER BY version
                """
            )
        ).all()
    assert [(row[0], row[1]) for row in parsers] == [
        ("topdev.v0", False),
        ("topdev.v1", True),
    ]
    assert parsers[0][2] is not None
    assert parsers[1][3] == TopDevRegistration().configuration_hash()
    assert parsers[1][4] == "abcdef1"


def test_complete_fixture_ingestion_persists_full_lineage_and_counters(
    engine: sa.Engine,
) -> None:
    configuration = _bootstrap(engine)
    urls = [ACTIVE_URL, ACTIVE_URL, EXPIRED_URL, INVALID_URL, NEGOTIABLE_URL]
    run_id, result = _run(
        engine,
        replace_limit(configuration, 4),
        urls,
        {
            ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")],
            EXPIRED_URL: [_response(EXPIRED_URL, "job_expired.html")],
            INVALID_URL: [_response(INVALID_URL, "job_invalid.html")],
            NEGOTIABLE_URL: [_response(NEGOTIABLE_URL, "job_negotiable_salary.html")],
        },
    )
    assert result.status == "partially_succeeded"
    with engine.connect() as connection:
        run = (
            connection.execute(
                sa.text("SELECT * FROM ingestion.crawl_runs WHERE id=:run_id"), {"run_id": run_id}
            )
            .mappings()
            .one()
        )
        assert run["status"] == "partially_succeeded"
        assert run["started_at"] is not None and run["finished_at"] >= run["started_at"]
        assert {
            key: run[key]
            for key in (
                "discovered_count",
                "task_count",
                "fetch_success_count",
                "fetch_failure_count",
                "extracted_count",
                "accepted_count",
                "rejected_count",
                "error_count",
            )
        } == {
            "discovered_count": 4,
            "task_count": 5,
            "fetch_success_count": 5,
            "fetch_failure_count": 0,
            "extracted_count": 4,
            "accepted_count": 3,
            "rejected_count": 1,
            "error_count": 1,
        }
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.crawl_tasks WHERE crawl_run_id=:run_id"),
                {"run_id": run_id},
            )
            == 5
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.fetch_events WHERE crawl_run_id=:run_id"),
                {"run_id": run_id},
            )
            == 5
        )
        assert (
            connection.scalar(
                sa.text(
                    """
                SELECT count(*) FROM ingestion.fetch_events
                WHERE crawl_run_id=:run_id AND raw_object_id IS NOT NULL
                """
                ),
                {"run_id": run_id},
            )
            == 5
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM ingestion.extraction_runs WHERE crawl_run_id=:run_id"
                ),
                {"run_id": run_id},
            )
            == 4
        )
        statuses = connection.execute(
            sa.text(
                """
                SELECT processing_status, count(*)
                FROM ingestion.extracted_records AS record
                JOIN ingestion.extraction_runs AS extraction
                  ON extraction.id=record.extraction_run_id
                WHERE extraction.crawl_run_id=:run_id
                GROUP BY processing_status ORDER BY processing_status
                """
            ),
            {"run_id": run_id},
        ).all()
        assert [tuple(row) for row in statuses] == [("accepted", 3), ("rejected", 1)]
        error_message = connection.scalar(
            sa.text(
                "SELECT sanitized_message FROM ingestion.crawl_errors WHERE crawl_run_id=:run_id"
            ),
            {"run_id": run_id},
        )
        assert (
            error_message and "<html" not in error_message and "postgresql://" not in error_message
        )


def test_raw_dedup_changed_evidence_and_unchanged_counter(engine: sa.Engine) -> None:
    configuration = _bootstrap(engine)
    _, first = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")]},
    )
    _, unchanged = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")]},
    )
    _, changed = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active_changed.html")]},
    )
    assert first.counters.unchanged_count == 0
    assert unchanged.counters.unchanged_count == 1
    assert changed.counters.unchanged_count == 0
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM ingestion.raw_objects")) == 3


@pytest.mark.parametrize("retention_days", [30, None])
def test_raw_retention_expiry_follows_policy(engine: sa.Engine, retention_days: int | None) -> None:
    configuration = _bootstrap(engine, raw_retention_days=retention_days)
    run_id, _ = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")]},
    )
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """
                SELECT raw.expires_at, fetch_event.fetched_at
                FROM ingestion.fetch_events AS fetch_event
                JOIN ingestion.raw_objects AS raw ON raw.id=fetch_event.raw_object_id
                WHERE fetch_event.crawl_run_id=:run_id
                """
            ),
            {"run_id": run_id},
        ).all()
    assert rows
    if retention_days is None:
        assert all(row[0] is None for row in rows)
    else:
        assert all(row[0] - row[1] == timedelta(days=retention_days) for row in rows)


def test_raw_and_description_storage_suppression(engine: sa.Engine) -> None:
    configuration = _bootstrap(engine, allow_raw_storage=False, allow_description_storage=False)
    run_id, result = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")]},
    )
    assert result.status == "succeeded"
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM ingestion.raw_objects")) == 0
        assert (
            connection.scalar(
                sa.text(
                    """
                SELECT count(*) FROM ingestion.fetch_events
                WHERE crawl_run_id=:run_id AND raw_object_id IS NOT NULL
                """
                ),
                {"run_id": run_id},
            )
            == 0
        )
        payload = connection.scalar(
            sa.text(
                """
                SELECT direct_payload_json FROM ingestion.extracted_records AS record
                JOIN ingestion.extraction_runs AS extraction
                  ON extraction.id=record.extraction_run_id
                WHERE extraction.crawl_run_id=:run_id
                """
            ),
            {"run_id": run_id},
        )
    assert payload["description_raw"] is None
    assert payload["description_storage_suppressed"] is True


@pytest.mark.parametrize(
    ("first_response", "expected_outcome"),
    [
        (
            _response(ACTIVE_URL, "response_429.html", status=429, headers={"Retry-After": "1"}),
            "http_error",
        ),
        (TimeoutError("fixture timeout token=SECRET_VALUE"), "timeout"),
    ],
)
def test_retryable_attempt_then_success_persists_each_fetch(
    engine: sa.Engine,
    first_response: FixtureResponse | Exception,
    expected_outcome: str,
) -> None:
    configuration = _bootstrap(engine)

    def immediate_retry(status: int | None, attempt: int, retry_after: int | None) -> RetryDecision:
        del status, attempt, retry_after
        return RetryDecision(True, 0)

    run_id, result = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [first_response, _response(ACTIVE_URL, "job_active.html")]},
        retry_policy=immediate_retry,
    )
    assert result.status == "succeeded"
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """
                SELECT fetch_outcome, attempt_number
                FROM ingestion.fetch_events AS fetch_event
                JOIN ingestion.crawl_tasks AS task ON task.id=fetch_event.crawl_task_id
                WHERE fetch_event.crawl_run_id=:run_id AND task.task_type='detail_page'
                ORDER BY fetch_event.id
                """
            ),
            {"run_id": run_id},
        ).all()
        assert [tuple(row) for row in rows] == [(expected_outcome, 1), ("success", 2)]
        messages = connection.scalars(
            sa.text(
                "SELECT sanitized_message FROM ingestion.crawl_errors WHERE crawl_run_id=:run_id"
            ),
            {"run_id": run_id},
        ).all()
    assert len(messages) == 1
    assert "SECRET_VALUE" not in messages[0]


def test_http_403_is_not_retried(engine: sa.Engine) -> None:
    configuration = _bootstrap(engine)
    run_id, result = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "response_403.html", status=403)]},
    )
    assert result.status == "failed"
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    """
                SELECT count(*) FROM ingestion.fetch_events AS fetch_event
                JOIN ingestion.crawl_tasks AS task ON task.id=fetch_event.crawl_task_id
                WHERE fetch_event.crawl_run_id=:run_id AND task.task_type='detail_page'
                """
                ),
                {"run_id": run_id},
            )
            == 1
        )


def test_planning_and_extraction_are_idempotent(engine: sa.Engine) -> None:
    configuration = _bootstrap(engine)
    run_id, _ = _run(
        engine,
        configuration,
        [ACTIVE_URL, ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")]},
    )
    store = PostgreSQLRunnerStore(engine)
    planned = PlannedTask(ACTIVE_URL, "3100001", "curated_it_listing")
    assert store.complete_discovery(run_id, [planned, planned]) == 0
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    """
                SELECT count(*) FROM ingestion.crawl_tasks
                WHERE crawl_run_id=:run_id AND task_type='detail_page'
                """
                ),
                {"run_id": run_id},
            )
            == 1
        )
        row = connection.execute(
            sa.text(
                """
                SELECT extraction.id, extraction.fetch_event_id,
                       extraction.raw_object_id, record.source_job_id,
                       record.record_schema_version, record.direct_payload_json,
                       record.direct_hash, record.extracted_at, record.id
                FROM ingestion.extraction_runs AS extraction
                JOIN ingestion.extracted_records AS record
                  ON record.extraction_run_id=extraction.id
                WHERE extraction.crawl_run_id=:run_id
                """
            ),
            {"run_id": run_id},
        ).one()
    fetch = StoredFetch(int(row[1]), cast(int | None, row[2]), None, False)
    assert (
        store.begin_extraction(run_id, fetch, configuration.parser_version_id, datetime.now(UTC))
        == row[0]
    )
    record = ExtractionRecord(
        source_job_id=str(row[3]),
        record_schema_version=str(row[4]),
        direct_payload=cast(dict[str, Any], row[5]),
        direct_hash=str(row[6]),
        extracted_at=cast(datetime, row[7]),
        processing_status="accepted",
    )
    store.complete_extraction(int(row[0]), configuration.source_id, fetch, record)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.extracted_records WHERE id=:id"),
                {"id": row[8]},
            )
            == 1
        )


def test_source_lineage_mismatches_are_rejected_or_prevented(engine: sa.Engine) -> None:
    configuration = _bootstrap(engine)
    with engine.begin() as connection:
        other_source = cast(
            UUID,
            connection.scalar(
                sa.text(
                    """
                    INSERT INTO ingestion.sources (
                        slug, display_name, base_url, status, is_enabled
                    ) VALUES ('other-source', 'Other', 'https://other.test', 'approved', true)
                    RETURNING id
                    """
                )
            ),
        )
        other_policy = cast(
            UUID,
            connection.scalar(
                sa.text(
                    """
                    INSERT INTO ingestion.source_policies (
                        source_id, policy_version, robots_review_status, terms_review_status
                    ) VALUES (:source, 'other-v1', 'approved', 'approved') RETURNING id
                    """
                ),
                {"source": other_source},
            ),
        )
        other_parser = cast(
            UUID,
            connection.scalar(
                sa.text(
                    """
                    INSERT INTO ingestion.parser_versions (
                        source_id, parser_name, version, schema_version, is_active
                    ) VALUES (:source, 'OtherParser', '1', 'other.v1', true) RETURNING id
                    """
                ),
                {"source": other_source},
            ),
        )
    store = PostgreSQLRunnerStore(engine)
    cross_configuration = replace(
        configuration,
        source_policy_id=other_policy,
        parser_version_id=other_parser,
    )
    with pytest.raises(NoResultFound):
        store.create_run(cross_configuration, datetime.now(UTC))

    run_id = store.create_run(configuration, datetime.now(UTC))
    with engine.begin() as connection:
        cross_task_id = int(
            connection.scalar(
                sa.text(
                    """
                    INSERT INTO ingestion.crawl_tasks (
                        crawl_run_id, source_id, task_type, source_job_id, requested_url,
                        max_attempts
                    ) VALUES (
                        :run_id, :other_source, 'detail_page', 'cross',
                        'https://topdev.vn/viec-lam/cross-3999999', 3
                    ) RETURNING id
                    """
                ),
                {"run_id": run_id, "other_source": other_source},
            )
        )
    assert store.claim_task(run_id) is None
    evidence = FetchEvidence(
        requested_url="https://topdev.vn/viec-lam/cross-3999999",
        resolved_url=None,
        http_status=403,
        content_type="text/html",
        response_bytes=0,
        duration_ms=1,
        attempt_number=1,
        outcome="http_error",
        fetched_at=datetime.now(UTC),
    )
    with pytest.raises(NoResultFound):
        store.persist_fetch(run_id, cross_task_id, other_source, "cross", evidence, None)
    with pytest.raises(ValueError, match="lineage"):
        store.record_error(
            run_id,
            CrawlErrorEvidence(
                stage="task",
                category="unexpected",
                message="safe mismatch",
                retryable=False,
                task_id=cross_task_id,
                url="https://topdev.vn/viec-lam/cross-3999999",
            ),
            datetime.now(UTC),
        )

    valid_run_id, _ = _run(
        engine,
        configuration,
        [ACTIVE_URL],
        {ACTIVE_URL: [_response(ACTIVE_URL, "job_active.html")]},
    )
    with engine.connect() as connection:
        valid = connection.execute(
            sa.text(
                """
                SELECT extraction.id, fetch_event.id, fetch_event.raw_object_id,
                       record.id, record.direct_payload_json, record.direct_hash,
                       record.extracted_at
                FROM ingestion.extraction_runs AS extraction
                JOIN ingestion.fetch_events AS fetch_event
                  ON fetch_event.id=extraction.fetch_event_id
                JOIN ingestion.extracted_records AS record
                  ON record.extraction_run_id=extraction.id
                WHERE extraction.crawl_run_id=:run_id
                """
            ),
            {"run_id": valid_run_id},
        ).one()
    stored_fetch = StoredFetch(int(valid[1]), cast(int | None, valid[2]), None, False)
    with pytest.raises(NoResultFound):
        store.begin_extraction(valid_run_id, stored_fetch, other_parser, datetime.now(UTC))
    before_id = int(valid[3])
    mismatched_record = ExtractionRecord(
        source_job_id="3100001",
        record_schema_version="source-raw-job-record.v1",
        direct_payload=cast(dict[str, Any], valid[4]),
        direct_hash=str(valid[5]),
        extracted_at=cast(datetime, valid[6]),
        processing_status="accepted",
    )
    store.complete_extraction(int(valid[0]), other_source, stored_fetch, mismatched_record)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.extracted_records WHERE id!=:id"),
                {"id": before_id},
            )
            == 0
        )


def test_stale_recovery_respects_attempts_and_terminal_runs(engine: sa.Engine) -> None:
    configuration = _bootstrap(engine)
    store = PostgreSQLRunnerStore(engine)
    run_id = store.create_run(configuration, datetime.now(UTC) - timedelta(hours=1))
    store.complete_discovery(
        run_id,
        [
            PlannedTask(ACTIVE_URL, "3100001", "fixture"),
            PlannedTask(EXPIRED_URL, "3100002", "fixture"),
        ],
    )
    terminal_run_id = store.create_run(configuration, datetime.now(UTC) - timedelta(hours=1))
    store.complete_discovery(terminal_run_id, [PlannedTask(NEGOTIABLE_URL, "3100004", "fixture")])
    stale_at = datetime.now(UTC) - timedelta(minutes=10)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE ingestion.crawl_tasks SET
                    status='running', attempt_count=CASE
                      WHEN source_job_id='3100001' THEN 1 ELSE 3 END,
                    started_at=:stale_at
                WHERE crawl_run_id=:run_id AND task_type='detail_page'
                """
            ),
            {"run_id": run_id, "stale_at": stale_at},
        )
        connection.execute(
            sa.text(
                """
                UPDATE ingestion.crawl_runs
                SET status='succeeded', finished_at=now()
                WHERE id=:terminal_run_id
                """
            ),
            {"terminal_run_id": terminal_run_id},
        )
        connection.execute(
            sa.text(
                """
                UPDATE ingestion.crawl_tasks SET status='running', attempt_count=1,
                    started_at=:stale_at
                WHERE crawl_run_id=:terminal_run_id AND task_type='detail_page'
                """
            ),
            {"terminal_run_id": terminal_run_id, "stale_at": stale_at},
        )
    assert store.recover_stale_tasks(60, datetime.now(UTC)) == 2
    with engine.connect() as connection:
        statuses = connection.execute(
            sa.text(
                """
                SELECT source_job_id, status FROM ingestion.crawl_tasks
                WHERE crawl_run_id=:run_id AND task_type='detail_page'
                ORDER BY source_job_id
                """
            ),
            {"run_id": run_id},
        ).all()
        terminal_status = connection.scalar(
            sa.text(
                """
                SELECT status FROM ingestion.crawl_tasks
                WHERE crawl_run_id=:run_id AND task_type='detail_page'
                """
            ),
            {"run_id": terminal_run_id},
        )
        errors = connection.scalar(
            sa.text("SELECT count(*) FROM ingestion.crawl_errors WHERE crawl_run_id=:run_id"),
            {"run_id": run_id},
        )
    assert [tuple(row) for row in statuses] == [
        ("3100001", "pending"),
        ("3100002", "failed"),
    ]
    assert terminal_status == "running"
    assert errors == 1
