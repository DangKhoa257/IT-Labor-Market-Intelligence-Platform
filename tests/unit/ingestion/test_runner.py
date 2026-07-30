from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from it_labor_market_intelligence.adapters.base import (
    ClosedStateDecision,
    FetchResult,
    SourceRawJobRecord,
)
from it_labor_market_intelligence.adapters.topdev import (
    TOPDEV_IT_LISTING,
    TopDevAdapter,
    extract_job_id,
)
from it_labor_market_intelligence.ingestion.contracts import FixtureResponse, IngestionAdapter
from it_labor_market_intelligence.ingestion.errors import RetryDecision
from it_labor_market_intelligence.ingestion.raw_storage import RawStorageDecision
from it_labor_market_intelligence.ingestion.runner import (
    ClaimedTask,
    CrawlErrorEvidence,
    ExtractionRecord,
    FetchEvidence,
    FixtureTransport,
    IngestionRunner,
    PlannedTask,
    RunConfiguration,
    RunCounters,
    RunResult,
    StoredFetch,
    TaskStatus,
    recover_stale_tasks,
    url_allowed_by_policy,
)

NOW = datetime(2026, 7, 30, 3, 0, tzinfo=UTC)
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000001")
POLICY_ID = UUID("00000000-0000-0000-0000-000000000002")
PARSER_ID = UUID("00000000-0000-0000-0000-000000000003")
JOB_1 = "https://topdev.vn/viec-lam/example-one-1001"
JOB_2 = "https://topdev.vn/viec-lam/example-two-1002"


def test_blocked_paths_take_precedence_over_approved_paths() -> None:
    approved = ("/viec-lam/*",)
    blocked = ("/viec-lam/private/*",)

    assert url_allowed_by_policy(JOB_1, approved, blocked) is True
    assert (
        url_allowed_by_policy("https://topdev.vn/viec-lam/private/example-1003", approved, blocked)
        is False
    )
    assert url_allowed_by_policy("https://topdev.vn/companies/example", approved, blocked) is False


class ScriptedAdapter:
    source_slug = "topdev"
    parser_name = "ScriptedAdapter"
    parser_version = "test.v1"
    record_schema_version = "source-raw-job-record.v1"

    def __init__(
        self,
        urls: Sequence[str],
        transport: FixtureTransport,
        *,
        extraction_errors: Mapping[str, Exception] | None = None,
    ) -> None:
        self._urls = tuple(urls)
        self._transport = transport
        self._extraction_errors = dict(extraction_errors or {})

    def discover_job_urls(self, limit: int = 30) -> Sequence[str]:
        return self._urls[:limit]

    def fetch_job_detail(self, url: str) -> FetchResult:
        return self._transport(url)

    def extract_raw_record(self, page: FetchResult) -> SourceRawJobRecord:
        if error := self._extraction_errors.get(page.url):
            raise error
        job_id = page.url.rsplit("-", 1)[-1]
        provenance = ClosedStateDecision(
            state="ACTIVE",
            source_field="test.fixture",
            raw_value="active",
            parsed_datetime=None,
            comparison_timestamp=page.fetched_at,
            decision_method="fixture",
            confidence=1.0,
        )
        return SourceRawJobRecord(
            source="topdev",
            source_job_id=job_id,
            source_url=page.url,
            title_raw=f"Engineer {job_id}",
            source_category_raw="IT",
            discovery_method="curated_it_listing",
            company_name_raw="EXAMPLE_NOT_REAL_DATA",
            location_raw="Ho Chi Minh City",
            salary_raw=None,
            skills_raw=("Python",),
            posted_at_raw=None,
            expires_at_raw=None,
            experience_raw=None,
            employment_type_raw="FULL_TIME",
            description_raw="EXAMPLE_NOT_REAL_DATA fixture description",
            closed_state="ACTIVE",
            closed_state_provenance=provenance,
            collected_at=page.fetched_at,
            content_hash=hashlib.sha256(page.body).hexdigest(),
        )

    def detect_closed_state(self, page: FetchResult) -> ClosedStateDecision:
        return self.extract_raw_record(page).closed_state_provenance


@dataclass
class _Task:
    id: int
    run_id: UUID
    source_id: UUID
    kind: Literal["discovery", "detail_page"]
    status: TaskStatus
    requested_url: str
    source_job_id: str | None
    attempt_count: int = 0
    max_attempts: int = 3
    started_at: datetime | None = None


class MemoryStore:
    """Persistence-faithful in-memory store used only for runner unit tests."""

    def __init__(self) -> None:
        self.runs: dict[UUID, RunConfiguration] = {}
        self.tasks: list[_Task] = []
        self.fetches: list[dict[str, object]] = []
        self.extractions: list[dict[str, object]] = []
        self.records: list[ExtractionRecord] = []
        self.errors: list[tuple[UUID, CrawlErrorEvidence]] = []
        self.raw_ids: dict[str, int] = {}
        self._run_number = 0

    def create_run(self, configuration: RunConfiguration, started_at: datetime) -> UUID:
        self._run_number += 1
        run_id = UUID(int=100 + self._run_number)
        self.runs[run_id] = configuration
        self.tasks.append(
            _Task(
                id=len(self.tasks) + 1,
                run_id=run_id,
                source_id=configuration.source_id,
                kind="discovery",
                status="running",
                requested_url=configuration.discovery_url,
                source_job_id=None,
                max_attempts=1,
                started_at=started_at,
            )
        )
        return run_id

    def discovery_task_id(self, run_id: UUID) -> int:
        return next(
            task.id for task in self.tasks if task.run_id == run_id and task.kind == "discovery"
        )

    def persist_fetch(
        self,
        run_id: UUID,
        task_id: int,
        source_id: UUID,
        source_job_id: str | None,
        evidence: FetchEvidence,
        raw_decision: RawStorageDecision | None,
    ) -> StoredFetch:
        del source_id
        raw_id: int | None = None
        raw_sha: str | None = None
        if raw_decision is not None:
            raw_sha = raw_decision.sha256
            if raw_decision.should_persist:
                raw_id = self.raw_ids.setdefault(raw_sha, len(self.raw_ids) + 1)
        unchanged = bool(
            evidence.outcome == "success"
            and raw_id is not None
            and source_job_id is not None
            and any(
                item["source_job_id"] == source_job_id
                and item["outcome"] == "success"
                and item["raw_id"] == raw_id
                for item in self.fetches
            )
        )
        fetch_id = len(self.fetches) + 1
        self.fetches.append(
            {
                "id": fetch_id,
                "run_id": run_id,
                "task_id": task_id,
                "source_job_id": source_job_id,
                "outcome": evidence.outcome,
                "status": evidence.http_status,
                "raw_id": raw_id,
                "unchanged": unchanged,
                "attempt": evidence.attempt_number,
            }
        )
        return StoredFetch(fetch_id, raw_id, raw_sha, unchanged)

    def complete_discovery(self, run_id: UUID, tasks: Sequence[PlannedTask]) -> int:
        discovery = self._task(self.discovery_task_id(run_id))
        discovery.status = "succeeded"
        inserted = 0
        for planned in tasks:
            if any(
                task.run_id == run_id
                and task.kind == "detail_page"
                and (
                    task.requested_url == planned.requested_url
                    or task.source_job_id == planned.source_job_id
                )
                for task in self.tasks
            ):
                continue
            self.tasks.append(
                _Task(
                    id=len(self.tasks) + 1,
                    run_id=run_id,
                    source_id=self.runs[run_id].source_id,
                    kind="detail_page",
                    status="pending",
                    requested_url=planned.requested_url,
                    source_job_id=planned.source_job_id,
                    max_attempts=planned.max_attempts,
                )
            )
            inserted += 1
        return inserted

    def fail_discovery(
        self, run_id: UUID, task_id: int, error: CrawlErrorEvidence, finished_at: datetime
    ) -> None:
        del finished_at
        self._task(task_id).status = "failed"
        self.errors.append((run_id, error))

    def claim_task(self, run_id: UUID) -> ClaimedTask | None:
        for task in self.tasks:
            if task.run_id != run_id or task.kind != "detail_page" or task.status != "pending":
                continue
            task.status = "running"
            task.attempt_count += 1
            task.started_at = NOW
            assert task.source_job_id is not None
            return ClaimedTask(
                task.id,
                task.run_id,
                task.source_id,
                task.requested_url,
                task.source_job_id,
                task.attempt_count,
                task.max_attempts,
            )
        return None

    def begin_extraction(
        self,
        run_id: UUID,
        fetch: StoredFetch,
        parser_version_id: UUID,
        started_at: datetime,
    ) -> int:
        extraction_id = len(self.extractions) + 1
        self.extractions.append(
            {
                "id": extraction_id,
                "run_id": run_id,
                "fetch_id": fetch.id,
                "parser_id": parser_version_id,
                "status": "running",
                "started_at": started_at,
            }
        )
        return extraction_id

    def complete_extraction(
        self, extraction_run_id: int, source_id: UUID, fetch: StoredFetch, record: ExtractionRecord
    ) -> None:
        del source_id, fetch
        self.extractions[extraction_run_id - 1]["status"] = "succeeded"
        self.records.append(record)

    def fail_extraction(
        self,
        run_id: UUID,
        extraction_run_id: int,
        source_id: UUID,
        fetch: StoredFetch,
        record: ExtractionRecord,
        error: CrawlErrorEvidence,
    ) -> None:
        del source_id, fetch
        self.extractions[extraction_run_id - 1]["status"] = "failed"
        self.records.append(record)
        self.errors.append((run_id, error))

    def complete_task(self, task_id: int, finished_at: datetime) -> None:
        del finished_at
        self._task(task_id).status = "succeeded"

    def fail_task(
        self,
        task: ClaimedTask,
        error: CrawlErrorEvidence,
        finished_at: datetime,
        retry: RetryDecision,
        *,
        persist_error: bool = True,
    ) -> TaskStatus:
        del finished_at
        stored = self._task(task.id)
        stored.status = (
            "pending" if retry.retryable and task.attempt_number < task.max_attempts else "failed"
        )
        if persist_error:
            self.errors.append((task.run_id, error))
        return stored.status

    def record_error(self, run_id: UUID, error: CrawlErrorEvidence, occurred_at: datetime) -> None:
        del occurred_at
        self.errors.append((run_id, error))

    def skip_pending_tasks(self, run_id: UUID, finished_at: datetime) -> int:
        del finished_at
        skipped = 0
        for task in self.tasks:
            if task.run_id == run_id and task.status == "pending":
                task.status = "skipped"
                skipped += 1
        return skipped

    def has_pending_tasks(self, run_id: UUID) -> bool:
        return any(
            task.run_id == run_id
            and task.kind == "detail_page"
            and task.status in {"pending", "running"}
            for task in self.tasks
        )

    def finalize_run(self, run_id: UUID, finished_at: datetime) -> RunResult:
        del finished_at
        detail = [
            task for task in self.tasks if task.run_id == run_id and task.kind == "detail_page"
        ]
        succeeded = sum(task.status == "succeeded" for task in detail)
        failed = sum(task.status == "failed" for task in detail)
        status: Literal["succeeded", "partially_succeeded", "failed"]
        if succeeded and not failed:
            status = "succeeded"
        elif succeeded:
            status = "partially_succeeded"
        else:
            status = "failed"
        run_fetches = [item for item in self.fetches if item["run_id"] == run_id]
        run_extractions = [item for item in self.extractions if item["run_id"] == run_id]
        extraction_ids = {cast(int, item["id"]) for item in run_extractions}
        run_records = [
            record for index, record in enumerate(self.records, start=1) if index in extraction_ids
        ]
        counters = RunCounters(
            discovered_count=len(detail),
            task_count=sum(task.run_id == run_id for task in self.tasks),
            fetch_success_count=sum(item["outcome"] == "success" for item in run_fetches),
            fetch_failure_count=sum(item["outcome"] != "success" for item in run_fetches),
            unchanged_count=sum(bool(item["unchanged"]) for item in run_fetches),
            extracted_count=len(run_records),
            accepted_count=sum(record.processing_status == "accepted" for record in run_records),
            rejected_count=sum(record.processing_status == "rejected" for record in run_records),
            error_count=sum(error_run_id == run_id for error_run_id, _ in self.errors),
        )
        return RunResult(run_id, status, counters)

    def recover_stale_tasks(self, older_than_seconds: int, recovered_at: datetime) -> int:
        cutoff = recovered_at - timedelta(seconds=older_than_seconds)
        recovered = 0
        for task in self.tasks:
            if task.status != "running" or task.started_at is None or task.started_at >= cutoff:
                continue
            task.status = "failed" if task.attempt_count >= task.max_attempts else "pending"
            recovered += 1
            if task.status == "failed":
                self.errors.append(
                    (
                        task.run_id,
                        CrawlErrorEvidence(
                            stage="task",
                            category="unexpected",
                            message="stale running task exhausted its maximum attempts",
                            retryable=False,
                            task_id=task.id,
                            url=task.requested_url,
                        ),
                    )
                )
        return recovered

    def add_stale_task(self, *, exhausted: bool) -> _Task:
        configuration = _configuration()
        run_id = self.create_run(configuration, NOW - timedelta(hours=1))
        self._task(self.discovery_task_id(run_id)).status = "succeeded"
        task = _Task(
            id=len(self.tasks) + 1,
            run_id=run_id,
            source_id=SOURCE_ID,
            kind="detail_page",
            status="running",
            requested_url=JOB_1,
            source_job_id="1001",
            attempt_count=3 if exhausted else 1,
            max_attempts=3,
            started_at=NOW - timedelta(minutes=10),
        )
        self.tasks.append(task)
        return task

    def _task(self, task_id: int) -> _Task:
        return next(task for task in self.tasks if task.id == task_id)


def _configuration(**overrides: object) -> RunConfiguration:
    values: dict[str, object] = {
        "source_id": SOURCE_ID,
        "source_slug": "topdev",
        "source_policy_id": POLICY_ID,
        "parser_version_id": PARSER_ID,
        "requested_limit": 10,
        "discovery_url": TOPDEV_IT_LISTING,
        "mode": "fixture",
        "run_type": "test",
        "trigger_type": "test",
    }
    values.update(overrides)
    return RunConfiguration(**values)  # type: ignore[arg-type]


def _response(url: str, status: int = 200, body: bytes = b"fixture-v1") -> FixtureResponse:
    return FixtureResponse(url, status, body, NOW, "text/html", {"Content-Type": "text/html"})


def _runner(
    urls: Sequence[str],
    responses: Mapping[str, Sequence[FixtureResponse | Exception]],
    *,
    store: MemoryStore | None = None,
    configuration: RunConfiguration | None = None,
    extraction_errors: Mapping[str, Exception] | None = None,
    retry_policy: Callable[[int | None, int, int | None], RetryDecision] | None = None,
) -> tuple[IngestionRunner, MemoryStore, FixtureTransport]:
    memory_store = store or MemoryStore()
    transport = FixtureTransport(
        responses,
        fixture_keys={
            url: f"tests/fixtures/topdev/{url.rsplit('-', 1)[-1]}.html" for url in responses
        },
        now=lambda: NOW,
    )
    adapter = ScriptedAdapter(urls, transport, extraction_errors=extraction_errors)
    runner = IngestionRunner(
        adapter=adapter,
        store=memory_store,
        configuration=configuration or _configuration(requested_limit=max(1, len(urls))),
        source_job_id_from_url=lambda url: url.rsplit("-", 1)[-1],
        transport_observer=transport,
        now=lambda: NOW,
        monotonic=lambda: 1.0,
        retry_policy=retry_policy,
    )
    return runner, memory_store, transport


def test_successful_fixture_run_uses_existing_topdev_adapter() -> None:
    job_url = "https://topdev.vn/viec-lam/example-platform-engineer-2086809"
    listing = f'<html><a href="{job_url}">job</a></html>'.encode()
    job = b"""<html><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting",
     "title":"Platform Engineer","description":"EXAMPLE_NOT_REAL_DATA description",
     "hiringOrganization":{"name":"EXAMPLE_NOT_REAL_DATA"}}
    </script></html>"""
    transport = FixtureTransport(
        {
            TOPDEV_IT_LISTING: [_response(TOPDEV_IT_LISTING, body=listing)],
            job_url: [_response(job_url, body=job)],
        },
        fixture_keys={
            TOPDEV_IT_LISTING: "tests/fixtures/topdev/discovery_page_1.html",
            job_url: "tests/fixtures/topdev/job_active.html",
        },
        now=lambda: NOW,
    )
    adapter = TopDevAdapter(transport=transport)
    store = MemoryStore()

    result = IngestionRunner(
        adapter=cast(IngestionAdapter, adapter),
        store=store,
        configuration=_configuration(requested_limit=1),
        source_job_id_from_url=extract_job_id,
        transport_observer=transport,
        now=lambda: NOW,
        monotonic=lambda: 1.0,
    ).run()

    assert result.status == "succeeded"
    assert result.counters == RunCounters(
        discovered_count=1,
        task_count=2,
        fetch_success_count=2,
        extracted_count=1,
        accepted_count=1,
    )
    assert store.records[0].direct_payload["title_raw"] == "Platform Engineer"


def test_duplicate_discovery_urls_create_one_detail_task() -> None:
    runner, store, _ = _runner([JOB_1, JOB_1, JOB_1], {JOB_1: [_response(JOB_1)]})

    result = runner.run()

    assert result.status == "succeeded"
    assert result.counters.discovered_count == 1
    assert result.counters.task_count == 2


def test_partial_success_has_persisted_success_and_failure() -> None:
    runner, _, _ = _runner(
        [JOB_1, JOB_2],
        {JOB_1: [_response(JOB_1)], JOB_2: [_response(JOB_2, 403)]},
    )

    result = runner.run()

    assert result.status == "partially_succeeded"
    assert result.counters.accepted_count == 1
    assert result.counters.fetch_failure_count == 1
    assert result.counters.error_count == 1


def test_all_tasks_failed_produces_failed_run() -> None:
    runner, _, _ = _runner(
        [JOB_1, JOB_2],
        {JOB_1: [_response(JOB_1, 403)], JOB_2: [_response(JOB_2, 410)]},
    )

    result = runner.run()

    assert result.status == "failed"
    assert result.counters.fetch_success_count == 0
    assert result.counters.fetch_failure_count == 2
    assert result.counters.accepted_count == 0


def test_retryable_failure_then_success_persists_both_attempts() -> None:
    def immediate_retry(status: int | None, attempt: int, retry_after: int | None) -> RetryDecision:
        del status, attempt, retry_after
        return RetryDecision(True, 0)

    runner, store, _ = _runner(
        [JOB_1],
        {JOB_1: [_response(JOB_1, 503), _response(JOB_1)]},
        retry_policy=immediate_retry,
    )

    result = runner.run()

    assert result.status == "succeeded"
    assert [item["status"] for item in store.fetches] == [503, 200]
    assert [item["attempt"] for item in store.fetches] == [1, 2]
    assert result.counters.fetch_failure_count == 1
    assert result.counters.fetch_success_count == 1


def test_non_retryable_403_is_attempted_once() -> None:
    runner, store, _ = _runner([JOB_1], {JOB_1: [_response(JOB_1, 403)]})

    result = runner.run()

    assert result.status == "failed"
    assert len(store.fetches) == 1
    assert store.fetches[0]["attempt"] == 1
    assert store.tasks[-1].attempt_count == 1


def test_unchanged_and_changed_response_bodies_are_database_derived() -> None:
    store = MemoryStore()
    first, _, _ = _runner([JOB_1], {JOB_1: [_response(JOB_1, body=b"v1")]}, store=store)
    unchanged, _, _ = _runner([JOB_1], {JOB_1: [_response(JOB_1, body=b"v1")]}, store=store)
    changed, _, _ = _runner([JOB_1], {JOB_1: [_response(JOB_1, body=b"v2")]}, store=store)

    first_result = first.run()
    unchanged_result = unchanged.run()
    changed_result = changed.run()

    assert first_result.counters.unchanged_count == 0
    assert unchanged_result.counters.unchanged_count == 1
    assert changed_result.counters.unchanged_count == 0


def test_fail_fast_skips_unstarted_tasks_after_first_terminal_failure() -> None:
    runner, store, _ = _runner(
        [JOB_1, JOB_2],
        {JOB_1: [_response(JOB_1, 403)], JOB_2: [_response(JOB_2)]},
        configuration=_configuration(requested_limit=2, fail_fast=True),
    )

    result = runner.run()

    assert result.status == "failed"
    assert len(store.fetches) == 1
    assert [task.status for task in store.tasks if task.kind == "detail_page"] == [
        "failed",
        "skipped",
    ]


def test_stale_task_recovery_requeues_retryable_and_fails_exhausted() -> None:
    store = MemoryStore()
    retryable = store.add_stale_task(exhausted=False)
    exhausted = store.add_stale_task(exhausted=True)

    recovered = recover_stale_tasks(store, 60, now=NOW)

    assert recovered == 2
    assert retryable.status == "pending"
    assert exhausted.status == "failed"
    assert store.errors[-1][1].error_code is None


def test_counters_and_terminal_status_include_rejected_extraction() -> None:
    runner, _, _ = _runner(
        [JOB_1, JOB_2],
        {JOB_1: [_response(JOB_1)], JOB_2: [_response(JOB_2)]},
        extraction_errors={JOB_2: ValueError("invalid JobPosting JSON-LD token=secret")},
    )

    result = runner.run()

    assert result.status == "partially_succeeded"
    assert result.counters == RunCounters(
        discovered_count=2,
        task_count=3,
        fetch_success_count=2,
        extracted_count=2,
        accepted_count=1,
        rejected_count=1,
        error_count=1,
    )
