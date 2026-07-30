"""Transaction-bounded, source-independent ingestion runner.

The runner calls an existing source adapter for discovery and extraction while
the store owns all PostgreSQL transactions.  No transaction remains open
during adapter network work, parsing, rate limiting, or retry scheduling.
"""

from __future__ import annotations

import dataclasses
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from fnmatch import fnmatchcase
from threading import Lock
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlparse
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from it_labor_market_intelligence.adapters.base import FetchResult, SourceRawJobRecord

from .contracts import FetchTransport, FixtureResponse, IngestionAdapter, JsonValue
from .errors import RetryDecision, retry_decision
from .hashing import direct_payload_sha256
from .raw_storage import (
    RawStorageDecision,
    fixture_raw_decision,
    inline_json_raw_decision,
    suppressed_raw_decision,
)
from .repositories import claim_due_task, upsert_raw_storage_decision
from .sanitization import sanitize_error, sanitize_headers

RunStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "partially_succeeded",
    "failed",
    "cancelled",
]
TaskStatus = Literal["pending", "running", "succeeded", "failed", "cancelled", "skipped"]
FetchOutcome = Literal[
    "success",
    "http_error",
    "network_error",
    "timeout",
    "blocked_by_policy",
    "robots_disallowed",
    "invalid_content",
    "cancelled",
    "other_error",
]
ErrorStage = Literal[
    "policy",
    "discovery",
    "task",
    "fetch",
    "raw_storage",
    "extraction",
    "validation",
    "processing",
    "other",
]
ErrorCategory = Literal[
    "robots_disallowed",
    "policy_blocked",
    "http_error",
    "network_error",
    "timeout",
    "invalid_url",
    "invalid_content",
    "parse_error",
    "schema_error",
    "storage_error",
    "database_error",
    "rate_limited",
    "unexpected",
]


@dataclass(frozen=True, slots=True)
class RunConfiguration:
    """Resolved immutable identity and policy for one crawl run."""

    source_id: UUID
    source_slug: str
    source_policy_id: UUID
    parser_version_id: UUID
    requested_limit: int
    discovery_url: str
    mode: Literal["fixture", "live"] = "fixture"
    run_type: Literal["scheduled", "manual", "backfill", "test"] = "test"
    trigger_type: Literal["manual", "scheduler", "github_actions", "api", "system", "test"] = "test"
    policy_version: str = "unknown"
    minimum_request_interval_seconds: float = 2.0
    maximum_requests_per_run: int = 30
    maximum_concurrent_requests: int = 1
    approved_paths: tuple[str, ...] = ("/",)
    blocked_paths: tuple[str, ...] = ()
    raw_retention_days: int | None = 30
    description_retention_days: int | None = 90
    allow_raw_storage: bool = True
    allow_description_storage: bool = True
    fail_fast: bool = False
    git_commit_sha: str | None = None
    pipeline_version_id: UUID | None = None
    parser_version: str = "unknown"
    record_schema_version: str = "source-raw-job-record.v1"

    def __post_init__(self) -> None:
        if not 1 <= self.requested_limit <= 30:
            raise ValueError("requested_limit must be between 1 and 30")
        if not self.source_slug.strip():
            raise ValueError("source_slug must not be blank")
        if not self.discovery_url.strip():
            raise ValueError("discovery_url must not be blank")
        if self.raw_retention_days is not None and self.raw_retention_days < 0:
            raise ValueError("raw_retention_days must not be negative")
        if self.description_retention_days is not None and self.description_retention_days < 0:
            raise ValueError("description_retention_days must not be negative")
        if self.minimum_request_interval_seconds < 0:
            raise ValueError("minimum_request_interval_seconds must not be negative")
        if self.maximum_requests_per_run < 1:
            raise ValueError("maximum_requests_per_run must be at least 1")
        if self.maximum_concurrent_requests < 1:
            raise ValueError("maximum_concurrent_requests must be at least 1")
        if not self.policy_version.strip():
            raise ValueError("policy_version must not be blank")
        _validate_path_patterns(self.approved_paths, "approved_paths")
        _validate_path_patterns(self.blocked_paths, "blocked_paths")

    def safe_configuration_json(self) -> dict[str, JsonValue]:
        """Return non-secret operator settings suitable for JSONB."""

        configuration: dict[str, JsonValue] = {
            "source_slug": self.source_slug,
            "discovery_url": self.discovery_url,
            "mode": self.mode,
            "requested_limit": self.requested_limit,
            "policy_version": self.policy_version,
            "minimum_request_interval_seconds": self.minimum_request_interval_seconds,
            "maximum_requests_per_run": self.maximum_requests_per_run,
            "maximum_concurrent_requests": self.maximum_concurrent_requests,
            "approved_paths": list(self.approved_paths),
            "blocked_paths": list(self.blocked_paths),
            "raw_retention_days": self.raw_retention_days,
            "description_retention_days": self.description_retention_days,
            "allow_raw_storage": self.allow_raw_storage,
            "allow_description_storage": self.allow_description_storage,
            "fail_fast": self.fail_fast,
            "parser_version": self.parser_version,
            "record_schema_version": self.record_schema_version,
        }
        configuration["policy_execution_hash"] = self.policy_execution_hash()
        return configuration

    def policy_execution_contract(self) -> dict[str, JsonValue]:
        """Return exactly the behavior-affecting source policy fields."""

        return {
            "policy_version": self.policy_version,
            "minimum_request_interval_seconds": self.minimum_request_interval_seconds,
            "maximum_requests_per_run": self.maximum_requests_per_run,
            "maximum_concurrent_requests": self.maximum_concurrent_requests,
            "approved_paths": list(self.approved_paths),
            "blocked_paths": list(self.blocked_paths),
            "raw_retention_days": self.raw_retention_days,
            "description_retention_days": self.description_retention_days,
            "allow_raw_storage": self.allow_raw_storage,
            "allow_description_storage": self.allow_description_storage,
        }

    def policy_execution_hash(self) -> str:
        return direct_payload_sha256(cast(dict[str, Any], self.policy_execution_contract()))


@dataclass(frozen=True, slots=True)
class PlannedTask:
    requested_url: str
    source_job_id: str
    discovery_method: str
    max_attempts: int = 3
    payload: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    id: int
    run_id: UUID
    source_id: UUID
    requested_url: str
    source_job_id: str
    attempt_number: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class FetchEvidence:
    requested_url: str
    resolved_url: str | None
    http_status: int | None
    content_type: str | None
    response_bytes: int | None
    duration_ms: int
    attempt_number: int
    outcome: FetchOutcome
    fetched_at: datetime
    request_headers: Mapping[str, str] = field(default_factory=dict)
    response_headers: Mapping[str, str] = field(default_factory=dict)
    robots_allowed: bool | None = True


@dataclass(frozen=True, slots=True)
class StoredFetch:
    id: int
    raw_object_id: int | None
    raw_sha256: str | None
    unchanged: bool
    storage_error: str | None = None


@dataclass(frozen=True, slots=True)
class CrawlErrorEvidence:
    stage: ErrorStage
    category: ErrorCategory
    message: str
    retryable: bool
    task_id: int | None = None
    fetch_event_id: int | None = None
    extraction_run_id: int | None = None
    source_job_id: str | None = None
    url: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractionRecord:
    source_job_id: str
    record_schema_version: str
    direct_payload: dict[str, JsonValue]
    direct_hash: str
    extracted_at: datetime
    processing_status: Literal["accepted", "rejected"]
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RunCounters:
    discovered_count: int = 0
    task_count: int = 0
    fetch_success_count: int = 0
    fetch_failure_count: int = 0
    unchanged_count: int = 0
    extracted_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    error_count: int = 0


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: UUID
    status: RunStatus
    counters: RunCounters


@dataclass(frozen=True, slots=True)
class TransportAttempt:
    requested_url: str
    response: FetchResult | None
    error: Exception | None
    occurred_at: datetime
    fixture_key: str | None


class FixtureTransport:
    """Deterministic URL-mapped transport accepted by source adapters.

    Each URL maps to a sequence so retries can deterministically return, for
    example, HTTP 429 followed by HTTP 200.  The transport never uses network
    access and records attempts so listing-page fetches performed inside the
    existing adapter can receive full ingestion lineage.
    """

    def __init__(
        self,
        responses: Mapping[str, Sequence[FixtureResponse | Exception]],
        *,
        fixture_keys: Mapping[str, str | Sequence[str | None]] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._responses = {url: deque(sequence) for url, sequence in responses.items()}
        if any(not sequence for sequence in self._responses.values()):
            raise ValueError("fixture response sequences must not be empty")
        self._fixture_keys: dict[str, str | deque[str | None]] = {}
        for url, value in (fixture_keys or {}).items():
            self._fixture_keys[url] = value if isinstance(value, str) else deque(value)
        self._now = now or (lambda: datetime.now(UTC))
        self._attempts: list[TransportAttempt] = []

    def __call__(self, url: str) -> FetchResult:
        try:
            sequence = self._responses[url]
        except KeyError as error:
            missing = RuntimeError(f"no fixture response registered for URL: {url}")
            self._record(url, None, missing)
            raise missing from error
        if not sequence:
            exhausted = RuntimeError(f"fixture response sequence exhausted for URL: {url}")
            self._record(url, None, exhausted)
            raise exhausted

        item = sequence.popleft()
        if isinstance(item, Exception):
            self._record(url, None, item)
            raise item
        response = item.as_fetch_result()
        self._record(url, response, None)
        return response

    def _record(self, url: str, response: FetchResult | None, error: Exception | None) -> None:
        occurred_at = response.fetched_at if response is not None else self._now()
        self._attempts.append(
            TransportAttempt(
                requested_url=url,
                response=response,
                error=error,
                occurred_at=occurred_at,
                fixture_key=self._next_fixture_key(url),
            )
        )

    def _next_fixture_key(self, url: str) -> str | None:
        value = self._fixture_keys.get(url)
        if isinstance(value, deque):
            return value.popleft() if value else None
        return value

    def drain_attempts(self) -> tuple[TransportAttempt, ...]:
        attempts = tuple(self._attempts)
        self._attempts.clear()
        return attempts


class AttemptObserver(Protocol):
    def drain_attempts(self) -> tuple[TransportAttempt, ...]: ...


class ObservedTransport:
    """Record transport attempts without changing response data or retry behavior."""

    def __init__(self, transport: FetchTransport, *, now: Callable[[], datetime]) -> None:
        self._transport = transport
        self._now = now
        self._attempts: list[TransportAttempt] = []

    def __call__(self, url: str) -> FetchResult:
        try:
            response = self._transport(url)
        except Exception as error:
            self._attempts.append(TransportAttempt(url, None, error, self._now(), None))
            raise
        self._attempts.append(TransportAttempt(url, response, None, response.fetched_at, None))
        return response

    def drain_attempts(self) -> tuple[TransportAttempt, ...]:
        attempts = tuple(self._attempts)
        self._attempts.clear()
        return attempts


class PolicyViolationError(ValueError):
    """Raised before transport work when the snapshotted live policy forbids it."""


class PolicyEnforcingTransport:
    """Enforce URL, request-count, and concurrency limits around live transport."""

    def __init__(
        self,
        transport: FetchTransport,
        *,
        approved_paths: Sequence[str],
        blocked_paths: Sequence[str],
        maximum_requests: int,
        maximum_concurrent_requests: int,
        initial_request_count: int = 0,
    ) -> None:
        self._transport = transport
        self._approved_paths = tuple(approved_paths)
        self._blocked_paths = tuple(blocked_paths)
        self._maximum_requests = maximum_requests
        self._maximum_concurrent_requests = maximum_concurrent_requests
        if not 0 <= initial_request_count <= maximum_requests:
            raise ValueError("initial_request_count must fit within the request limit")
        self._request_count = initial_request_count
        self._active_count = 0
        self._lock = Lock()

    def __call__(self, url: str) -> FetchResult:
        self._validate_url(url)
        with self._lock:
            if self._request_count >= self._maximum_requests:
                raise PolicyViolationError("source policy maximum request count was reached")
            if self._active_count >= self._maximum_concurrent_requests:
                raise PolicyViolationError("source policy maximum concurrency was reached")
            self._request_count += 1
            self._active_count += 1
        try:
            return self._transport(url)
        finally:
            with self._lock:
                self._active_count -= 1

    def validate_redirect_target(self, url: str) -> None:
        """Validate and reserve one policy request slot for a redirect target."""

        self._validate_url(url)
        with self._lock:
            if self._request_count >= self._maximum_requests:
                raise PolicyViolationError("source policy maximum request count was reached")
            self._request_count += 1

    def _validate_url(self, url: str) -> None:
        if not url_allowed_by_policy(url, self._approved_paths, self._blocked_paths):
            raise PolicyViolationError("requested URL is blocked or not approved by source policy")


class RunnerStore(Protocol):
    """Short-transaction persistence boundary consumed by the runner."""

    def create_run(self, configuration: RunConfiguration, started_at: datetime) -> UUID: ...

    def discovery_task_id(self, run_id: UUID) -> int: ...

    def persist_fetch(
        self,
        run_id: UUID,
        task_id: int,
        source_id: UUID,
        source_job_id: str | None,
        evidence: FetchEvidence,
        raw_decision: RawStorageDecision | None,
    ) -> StoredFetch: ...

    def complete_discovery(self, run_id: UUID, tasks: Sequence[PlannedTask]) -> int: ...

    def fail_discovery(
        self, run_id: UUID, task_id: int, error: CrawlErrorEvidence, finished_at: datetime
    ) -> None: ...

    def claim_task(self, run_id: UUID) -> ClaimedTask | None: ...

    def begin_extraction(
        self,
        run_id: UUID,
        fetch: StoredFetch,
        parser_version_id: UUID,
        started_at: datetime,
    ) -> int: ...

    def complete_extraction(
        self, extraction_run_id: int, source_id: UUID, fetch: StoredFetch, record: ExtractionRecord
    ) -> None: ...

    def fail_extraction(
        self,
        run_id: UUID,
        extraction_run_id: int,
        source_id: UUID,
        fetch: StoredFetch,
        record: ExtractionRecord,
        error: CrawlErrorEvidence,
    ) -> None: ...

    def complete_task(self, task_id: int, finished_at: datetime) -> None: ...

    def fail_task(
        self,
        task: ClaimedTask,
        error: CrawlErrorEvidence,
        finished_at: datetime,
        retry: RetryDecision,
        *,
        persist_error: bool = True,
    ) -> TaskStatus: ...

    def record_error(
        self, run_id: UUID, error: CrawlErrorEvidence, occurred_at: datetime
    ) -> None: ...

    def skip_pending_tasks(self, run_id: UUID, finished_at: datetime) -> int: ...

    def has_pending_tasks(self, run_id: UUID) -> bool: ...

    def request_attempt_count(self, run_id: UUID) -> int: ...

    def exhaust_pending_tasks_for_budget(self, run_id: UUID, finished_at: datetime) -> int: ...

    def finalize_run(self, run_id: UUID, finished_at: datetime) -> RunResult: ...

    def recover_stale_tasks(self, older_than_seconds: int, recovered_at: datetime) -> int: ...


class PostgreSQLRunnerStore:
    """PostgreSQL implementation whose public methods are one transaction each."""

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def _begin(self) -> AbstractContextManager[sa.Connection]:
        return self._engine.begin()

    def create_run(self, configuration: RunConfiguration, started_at: datetime) -> UUID:
        with self._begin() as connection:
            run_id = connection.execute(
                sa.text(
                    """
                    INSERT INTO ingestion.crawl_runs (
                        source_id, source_policy_id, parser_version_id,
                        pipeline_version_id, run_type, trigger_type, status,
                        requested_limit, configuration_json, git_commit_sha, started_at
                    )
                    SELECT :source_id, policy.id, parser.id, :pipeline_id,
                           :run_type, :trigger_type, 'running', :requested_limit,
                           :configuration, :git_sha, :started_at
                    FROM ingestion.source_policies AS policy
                    JOIN ingestion.parser_versions AS parser
                      ON parser.id=:parser_id AND parser.source_id=:source_id
                    WHERE policy.id=:policy_id AND policy.source_id=:source_id
                    RETURNING id
                    """
                ).bindparams(sa.bindparam("configuration", type_=JSONB)),
                {
                    "source_id": configuration.source_id,
                    "policy_id": configuration.source_policy_id,
                    "parser_id": configuration.parser_version_id,
                    "pipeline_id": configuration.pipeline_version_id,
                    "run_type": configuration.run_type,
                    "trigger_type": configuration.trigger_type,
                    "requested_limit": configuration.requested_limit,
                    "configuration": configuration.safe_configuration_json(),
                    "git_sha": configuration.git_commit_sha,
                    "started_at": started_at,
                },
            ).scalar_one()
            typed_run_id = cast(UUID, run_id)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO ingestion.crawl_tasks (
                        crawl_run_id, source_id, task_type, status, requested_url,
                        discovery_method, attempt_count, max_attempts, started_at
                    ) VALUES (
                        :run_id, :source_id, 'discovery', 'running', :url,
                        'curated_it_listing', 1, 1, :started_at
                    )
                    """
                ),
                {
                    "run_id": typed_run_id,
                    "source_id": configuration.source_id,
                    "url": configuration.discovery_url,
                    "started_at": started_at,
                },
            )
            return typed_run_id

    def discovery_task_id(self, run_id: UUID) -> int:
        with self._begin() as connection:
            value = connection.execute(
                sa.text(
                    """
                    SELECT id FROM ingestion.crawl_tasks
                    WHERE crawl_run_id = :run_id AND task_type = 'discovery'
                    """
                ),
                {"run_id": run_id},
            ).scalar_one()
            return int(value)

    def persist_fetch(
        self,
        run_id: UUID,
        task_id: int,
        source_id: UUID,
        source_job_id: str | None,
        evidence: FetchEvidence,
        raw_decision: RawStorageDecision | None,
    ) -> StoredFetch:
        raw_object_id: int | None = None
        storage_error: str | None = None
        with self._begin() as connection:
            if raw_decision is not None:
                try:
                    with connection.begin_nested():
                        raw_object_id = upsert_raw_storage_decision(connection, raw_decision)
                except (sa.exc.SQLAlchemyError, ValueError) as error:
                    storage_error = sanitize_error(str(error)) or "raw storage failed"

            unchanged = False
            if evidence.outcome == "success" and raw_object_id is not None and source_job_id:
                unchanged = bool(
                    connection.execute(
                        sa.text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM ingestion.fetch_events AS previous_fetch
                                JOIN ingestion.crawl_tasks AS previous_task
                                  ON previous_task.id = previous_fetch.crawl_task_id
                                WHERE previous_fetch.source_id = :source_id
                                  AND previous_task.source_job_id = :source_job_id
                                  AND previous_fetch.fetch_outcome = 'success'
                                  AND previous_fetch.raw_object_id = :raw_object_id
                            )
                            """
                        ),
                        {
                            "source_id": source_id,
                            "source_job_id": source_job_id,
                            "raw_object_id": raw_object_id,
                        },
                    ).scalar_one()
                )

            fetch_id = connection.execute(
                sa.text(
                    """
                    INSERT INTO ingestion.fetch_events (
                        crawl_run_id, crawl_task_id, source_id, raw_object_id,
                        requested_url, resolved_url, http_status, content_type,
                        response_bytes, duration_ms, attempt_number, robots_allowed,
                        fetch_outcome, etag, last_modified, request_headers_json,
                        response_headers_json, fetched_at
                    )
                    SELECT run.id, task.id, run.source_id, :raw_object_id,
                           :requested_url, :resolved_url, :http_status, :content_type,
                           :response_bytes, :duration_ms, :attempt_number, :robots_allowed,
                           :outcome, :etag, :last_modified, :request_headers,
                           :response_headers, :fetched_at
                    FROM ingestion.crawl_runs AS run
                    JOIN ingestion.crawl_tasks AS task
                      ON task.id=:task_id
                     AND task.crawl_run_id=run.id
                     AND task.source_id=run.source_id
                    WHERE run.id=:run_id AND run.source_id=:source_id
                    RETURNING id
                    """
                )
                .bindparams(sa.bindparam("request_headers", type_=JSONB))
                .bindparams(sa.bindparam("response_headers", type_=JSONB)),
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "source_id": source_id,
                    "raw_object_id": raw_object_id,
                    "requested_url": evidence.requested_url,
                    "resolved_url": evidence.resolved_url,
                    "http_status": evidence.http_status,
                    "content_type": evidence.content_type,
                    "response_bytes": evidence.response_bytes,
                    "duration_ms": evidence.duration_ms,
                    "attempt_number": evidence.attempt_number,
                    "robots_allowed": evidence.robots_allowed,
                    "outcome": evidence.outcome,
                    "etag": _header_value(evidence.response_headers, "etag"),
                    "last_modified": _header_value(evidence.response_headers, "last-modified"),
                    "request_headers": sanitize_headers(evidence.request_headers),
                    "response_headers": sanitize_headers(evidence.response_headers),
                    "fetched_at": evidence.fetched_at,
                },
            ).scalar_one()
            return StoredFetch(
                id=int(fetch_id),
                raw_object_id=raw_object_id,
                raw_sha256=raw_decision.sha256 if raw_decision is not None else None,
                unchanged=unchanged,
                storage_error=storage_error,
            )

    def complete_discovery(self, run_id: UUID, tasks: Sequence[PlannedTask]) -> int:
        with self._begin() as connection:
            connection.execute(
                sa.text("SELECT id FROM ingestion.crawl_runs WHERE id=:run_id FOR UPDATE"),
                {"run_id": run_id},
            ).one()
            inserted = 0
            statement = sa.text(
                """
                INSERT INTO ingestion.crawl_tasks (
                    crawl_run_id, source_id, task_type, source_job_id,
                    requested_url, discovery_method, max_attempts, task_payload_json
                )
                SELECT :run_id, run.source_id, 'detail_page', :source_job_id,
                       :requested_url, :discovery_method, :max_attempts, :payload
                FROM ingestion.crawl_runs AS run WHERE run.id = :run_id
                ON CONFLICT DO NOTHING
                """
            ).bindparams(sa.bindparam("payload", type_=JSONB))
            for task in tasks:
                result = connection.execute(
                    statement,
                    {
                        "run_id": run_id,
                        "source_job_id": task.source_job_id,
                        "requested_url": task.requested_url,
                        "discovery_method": task.discovery_method,
                        "max_attempts": task.max_attempts,
                        "payload": task.payload,
                    },
                )
                inserted += result.rowcount or 0
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks
                    SET status='succeeded', finished_at=now(), updated_at=now()
                    WHERE crawl_run_id=:run_id AND task_type='discovery'
                    """
                ),
                {"run_id": run_id},
            )
            return inserted

    def fail_discovery(
        self, run_id: UUID, task_id: int, error: CrawlErrorEvidence, finished_at: datetime
    ) -> None:
        with self._begin() as connection:
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks
                    SET status='failed', finished_at=:finished_at, updated_at=:finished_at
                    WHERE id=:task_id
                    """
                ),
                {"task_id": task_id, "finished_at": finished_at},
            )
            self._insert_error(connection, run_id, error, finished_at)

    def claim_task(self, run_id: UUID) -> ClaimedTask | None:
        with self._begin() as connection:
            row = claim_due_task(connection, run_id)
            if row is None:
                return None
            values = row._mapping
            requested_url = cast(str | None, values["requested_url"])
            source_job_id = cast(str | None, values["source_job_id"])
            if requested_url is None or source_job_id is None:
                raise ValueError("claimed detail task is missing its source identity")
            return ClaimedTask(
                id=int(values["id"]),
                run_id=cast(UUID, values["crawl_run_id"]),
                source_id=cast(UUID, values["source_id"]),
                requested_url=requested_url,
                source_job_id=source_job_id,
                attempt_number=int(values["attempt_count"]),
                max_attempts=int(values["max_attempts"]),
            )

    def begin_extraction(
        self,
        run_id: UUID,
        fetch: StoredFetch,
        parser_version_id: UUID,
        started_at: datetime,
    ) -> int:
        with self._begin() as connection:
            value = connection.execute(
                sa.text(
                    """
                    INSERT INTO ingestion.extraction_runs (
                        crawl_run_id, fetch_event_id, raw_object_id,
                        parser_version_id, status, started_at
                    )
                    SELECT fetch_event.crawl_run_id, fetch_event.id, fetch_event.raw_object_id,
                           parser.id, 'running', :started_at
                    FROM ingestion.fetch_events AS fetch_event
                    JOIN ingestion.parser_versions AS parser
                      ON parser.id=:parser_id AND parser.source_id=fetch_event.source_id
                    WHERE fetch_event.id=:fetch_id AND fetch_event.crawl_run_id=:run_id
                    ON CONFLICT (fetch_event_id, parser_version_id) DO UPDATE
                    SET fetch_event_id=EXCLUDED.fetch_event_id
                    RETURNING id
                    """
                ),
                {
                    "run_id": run_id,
                    "fetch_id": fetch.id,
                    "raw_object_id": fetch.raw_object_id,
                    "parser_id": parser_version_id,
                    "started_at": started_at,
                },
            ).scalar_one()
            return int(value)

    def complete_extraction(
        self, extraction_run_id: int, source_id: UUID, fetch: StoredFetch, record: ExtractionRecord
    ) -> None:
        with self._begin() as connection:
            self._insert_record(connection, extraction_run_id, source_id, fetch, record)
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.extraction_runs
                    SET status='succeeded', finished_at=:finished_at,
                        record_count=1, error_count=0
                    WHERE id=:extraction_id
                    """
                ),
                {"extraction_id": extraction_run_id, "finished_at": record.extracted_at},
            )

    def fail_extraction(
        self,
        run_id: UUID,
        extraction_run_id: int,
        source_id: UUID,
        fetch: StoredFetch,
        record: ExtractionRecord,
        error: CrawlErrorEvidence,
    ) -> None:
        with self._begin() as connection:
            self._insert_record(connection, extraction_run_id, source_id, fetch, record)
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.extraction_runs
                    SET status='failed', finished_at=:finished_at,
                        record_count=1, error_count=1
                    WHERE id=:extraction_id
                    """
                ),
                {"extraction_id": extraction_run_id, "finished_at": record.extracted_at},
            )
            self._insert_error(connection, run_id, error, record.extracted_at)

    def _insert_record(
        self,
        connection: sa.Connection,
        extraction_run_id: int,
        source_id: UUID,
        fetch: StoredFetch,
        record: ExtractionRecord,
    ) -> None:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.extracted_records (
                    extraction_run_id, source_id, source_job_id, fetch_event_id,
                    raw_object_id, record_schema_version, direct_payload_json,
                    direct_hash, processing_status, rejection_reason, extracted_at
                )
                SELECT extraction.id, fetch_event.source_id, task.source_job_id, fetch_event.id,
                       fetch_event.raw_object_id, :schema_version, :payload,
                       :direct_hash, :processing_status, :rejection_reason, :extracted_at
                FROM ingestion.extraction_runs AS extraction
                JOIN ingestion.fetch_events AS fetch_event
                  ON fetch_event.id=:fetch_id
                 AND fetch_event.id=extraction.fetch_event_id
                 AND fetch_event.source_id=:source_id
                JOIN ingestion.crawl_tasks AS task
                  ON task.id=fetch_event.crawl_task_id
                 AND task.source_id=fetch_event.source_id
                 AND task.source_job_id=:source_job_id
                WHERE extraction.id=:extraction_id
                ON CONFLICT (extraction_run_id, source_id, source_job_id) DO NOTHING
                """
            ).bindparams(sa.bindparam("payload", type_=JSONB)),
            {
                "extraction_id": extraction_run_id,
                "source_id": source_id,
                "source_job_id": record.source_job_id,
                "fetch_id": fetch.id,
                "raw_object_id": fetch.raw_object_id,
                "schema_version": record.record_schema_version,
                "payload": record.direct_payload,
                "direct_hash": record.direct_hash,
                "processing_status": record.processing_status,
                "rejection_reason": record.rejection_reason,
                "extracted_at": record.extracted_at,
            },
        )

    def complete_task(self, task_id: int, finished_at: datetime) -> None:
        with self._begin() as connection:
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks
                    SET status='succeeded',
                        finished_at=GREATEST(:finished_at, started_at),
                        updated_at=GREATEST(:finished_at, started_at)
                    WHERE id=:task_id AND status='running'
                    """
                ),
                {"task_id": task_id, "finished_at": finished_at},
            )

    def fail_task(
        self,
        task: ClaimedTask,
        error: CrawlErrorEvidence,
        finished_at: datetime,
        retry: RetryDecision,
        *,
        persist_error: bool = True,
    ) -> TaskStatus:
        will_retry = retry.retryable and task.attempt_number < task.max_attempts
        status: TaskStatus = "pending" if will_retry else "failed"
        scheduled_for = (
            finished_at + timedelta(seconds=retry.delay_seconds or 0) if will_retry else None
        )
        with self._begin() as connection:
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks
                    SET status=:status, scheduled_for=:scheduled_for,
                        finished_at=GREATEST(:finished_at, started_at),
                        updated_at=GREATEST(:finished_at, started_at)
                    WHERE id=:task_id AND status='running'
                    """
                ),
                {
                    "task_id": task.id,
                    "status": status,
                    "scheduled_for": scheduled_for,
                    "finished_at": finished_at,
                },
            )
            if persist_error:
                self._insert_error(connection, task.run_id, error, finished_at)
        return status

    def record_error(self, run_id: UUID, error: CrawlErrorEvidence, occurred_at: datetime) -> None:
        with self._begin() as connection:
            self._insert_error(connection, run_id, error, occurred_at)

    def skip_pending_tasks(self, run_id: UUID, finished_at: datetime) -> int:
        with self._begin() as connection:
            result = connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks
                    SET status='skipped', started_at=COALESCE(started_at, :finished_at),
                        finished_at=:finished_at, updated_at=:finished_at
                    WHERE crawl_run_id=:run_id AND status='pending'
                    """
                ),
                {"run_id": run_id, "finished_at": finished_at},
            )
            return result.rowcount or 0

    def has_pending_tasks(self, run_id: UUID) -> bool:
        with self._begin() as connection:
            return bool(
                connection.execute(
                    sa.text(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM ingestion.crawl_tasks
                            WHERE crawl_run_id=:run_id AND status IN ('pending','running')
                        )
                        """
                    ),
                    {"run_id": run_id},
                ).scalar_one()
            )

    def request_attempt_count(self, run_id: UUID) -> int:
        with self._begin() as connection:
            return int(
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM ingestion.fetch_events WHERE crawl_run_id=:run_id"
                    ),
                    {"run_id": run_id},
                )
                or 0
            )

    def exhaust_pending_tasks_for_budget(self, run_id: UUID, finished_at: datetime) -> int:
        """Terminalize all remaining work once without inventing fetch attempts."""

        with self._begin() as connection:
            exhausted = connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks AS task
                    SET status='failed', scheduled_for=NULL,
                        started_at=COALESCE(task.started_at, :finished_at),
                        finished_at=:finished_at, updated_at=:finished_at
                    FROM ingestion.crawl_runs AS run
                    WHERE task.crawl_run_id=run.id AND run.id=:run_id
                      AND run.status='running' AND task.status='pending'
                    RETURNING task.id
                    """
                ),
                {"run_id": run_id, "finished_at": finished_at},
            ).all()
            if exhausted:
                self._insert_error(
                    connection,
                    run_id,
                    CrawlErrorEvidence(
                        stage="policy",
                        category="policy_blocked",
                        message="source policy request budget exhausted",
                        retryable=False,
                        task_id=int(exhausted[0][0]),
                        error_code="policy_request_budget_exhausted",
                        details={"terminalized_task_count": len(exhausted)},
                    ),
                    finished_at,
                )
            return len(exhausted)

    def finalize_run(self, run_id: UUID, finished_at: datetime) -> RunResult:
        with self._begin() as connection:
            connection.execute(
                sa.text("SELECT id FROM ingestion.crawl_runs WHERE id=:run_id FOR UPDATE"),
                {"run_id": run_id},
            ).one()
            detail_counts = connection.execute(
                sa.text(
                    """
                    SELECT
                        count(*) FILTER (WHERE status='succeeded') AS succeeded,
                        count(*) FILTER (WHERE status='failed') AS failed
                    FROM ingestion.crawl_tasks
                    WHERE crawl_run_id=:run_id AND task_type='detail_page'
                    """
                ),
                {"run_id": run_id},
            ).one()
            succeeded = int(detail_counts[0])
            failed = int(detail_counts[1])
            status: RunStatus
            if succeeded and not failed:
                status = "succeeded"
            elif succeeded:
                status = "partially_succeeded"
            else:
                status = "failed"

            counter_row = connection.execute(
                sa.text(
                    """
                    SELECT
                      (SELECT count(*) FROM ingestion.crawl_tasks
                       WHERE crawl_run_id=:run_id AND task_type='detail_page'),
                      (SELECT count(*) FROM ingestion.crawl_tasks
                       WHERE crawl_run_id=:run_id),
                      (SELECT count(*) FROM ingestion.fetch_events
                       WHERE crawl_run_id=:run_id AND fetch_outcome='success'),
                      (SELECT count(*) FROM ingestion.fetch_events
                       WHERE crawl_run_id=:run_id AND fetch_outcome!='success'),
                      (SELECT count(*)
                       FROM ingestion.fetch_events AS current_fetch
                       JOIN ingestion.crawl_tasks AS current_task
                         ON current_task.id=current_fetch.crawl_task_id
                       WHERE current_fetch.crawl_run_id=:run_id
                         AND current_fetch.fetch_outcome='success'
                         AND current_fetch.raw_object_id IS NOT NULL
                         AND current_task.source_job_id IS NOT NULL
                         AND EXISTS (
                           SELECT 1
                           FROM ingestion.fetch_events AS previous_fetch
                           JOIN ingestion.crawl_tasks AS previous_task
                             ON previous_task.id=previous_fetch.crawl_task_id
                           WHERE previous_fetch.source_id=current_fetch.source_id
                             AND previous_task.source_job_id=current_task.source_job_id
                             AND previous_fetch.fetch_outcome='success'
                             AND previous_fetch.raw_object_id=current_fetch.raw_object_id
                             AND previous_fetch.id<current_fetch.id
                         )),
                      (SELECT count(*) FROM ingestion.extracted_records AS record
                       JOIN ingestion.extraction_runs AS extraction
                         ON extraction.id=record.extraction_run_id
                       WHERE extraction.crawl_run_id=:run_id),
                      (SELECT count(*) FROM ingestion.extracted_records AS record
                       JOIN ingestion.extraction_runs AS extraction
                         ON extraction.id=record.extraction_run_id
                       WHERE extraction.crawl_run_id=:run_id
                         AND record.processing_status='accepted'),
                      (SELECT count(*) FROM ingestion.extracted_records AS record
                       JOIN ingestion.extraction_runs AS extraction
                         ON extraction.id=record.extraction_run_id
                       WHERE extraction.crawl_run_id=:run_id
                         AND record.processing_status='rejected'),
                      (SELECT count(*) FROM ingestion.crawl_errors
                       WHERE crawl_run_id=:run_id)
                    """
                ),
                {"run_id": run_id},
            ).one()
            counters = RunCounters(*(int(value) for value in counter_row))
            connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_runs SET
                      status=:status, finished_at=:finished_at,
                      discovered_count=:discovered_count, task_count=:task_count,
                      fetch_success_count=:fetch_success_count,
                      fetch_failure_count=:fetch_failure_count,
                      unchanged_count=:unchanged_count, extracted_count=:extracted_count,
                      accepted_count=:accepted_count, rejected_count=:rejected_count,
                      error_count=:error_count, updated_at=:finished_at
                    WHERE id=:run_id
                    """
                ),
                {
                    "run_id": run_id,
                    "status": status,
                    "finished_at": finished_at,
                    **dataclasses.asdict(counters),
                },
            )
            return RunResult(run_id=run_id, status=status, counters=counters)

    def recover_stale_tasks(self, older_than_seconds: int, recovered_at: datetime) -> int:
        if older_than_seconds < 1:
            raise ValueError("older_than_seconds must be at least 1")
        cutoff = recovered_at - timedelta(seconds=older_than_seconds)
        with self._begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    UPDATE ingestion.crawl_tasks AS task
                    SET status=CASE
                          WHEN task.attempt_count >= task.max_attempts THEN 'failed'
                          ELSE 'pending'
                        END,
                        scheduled_for=CASE
                          WHEN task.attempt_count >= task.max_attempts THEN NULL
                          ELSE :recovered_at
                        END,
                        finished_at=:recovered_at,
                        updated_at=:recovered_at
                    FROM ingestion.crawl_runs AS run
                    WHERE task.crawl_run_id=run.id
                      AND run.status='running'
                      AND task.status='running'
                      AND task.started_at<:cutoff
                    RETURNING task.id, task.crawl_run_id, task.source_id,
                              task.source_job_id, task.requested_url, task.status
                    """
                ),
                {"cutoff": cutoff, "recovered_at": recovered_at},
            ).all()
            for row in rows:
                if row._mapping["status"] != "failed":
                    continue
                evidence = CrawlErrorEvidence(
                    stage="task",
                    category="unexpected",
                    message="stale running task exhausted its maximum attempts",
                    retryable=False,
                    task_id=int(row._mapping["id"]),
                    source_job_id=cast(str | None, row._mapping["source_job_id"]),
                    url=cast(str | None, row._mapping["requested_url"]),
                    error_code="stale_task_exhausted",
                )
                self._insert_error(
                    connection,
                    cast(UUID, row._mapping["crawl_run_id"]),
                    evidence,
                    recovered_at,
                    source_id=cast(UUID, row._mapping["source_id"]),
                )
            return len(rows)

    def _insert_error(
        self,
        connection: sa.Connection,
        run_id: UUID,
        error: CrawlErrorEvidence,
        occurred_at: datetime,
        *,
        source_id: UUID | None = None,
    ) -> None:
        safe_message = sanitize_error(error.message) or "ingestion error"
        result = connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.crawl_errors (
                    crawl_run_id, crawl_task_id, fetch_event_id, extraction_run_id,
                    source_id, stage, category, error_code, retryable, source_job_id,
                    url, http_status, sanitized_message, details_json, occurred_at
                )
                SELECT :run_id, :task_id, :fetch_id, :extraction_id,
                       COALESCE(:source_id, run.source_id), :stage, :category,
                       :error_code, :retryable, :source_job_id, :url, :http_status,
                       :message, :details, :occurred_at
                FROM ingestion.crawl_runs AS run
                WHERE run.id=:run_id
                  AND (CAST(:source_id AS uuid) IS NULL OR :source_id=run.source_id)
                  AND (CAST(:task_id AS bigint) IS NULL OR EXISTS (
                    SELECT 1 FROM ingestion.crawl_tasks AS task
                    WHERE task.id=:task_id AND task.crawl_run_id=run.id
                      AND task.source_id=run.source_id
                  ))
                  AND (CAST(:fetch_id AS bigint) IS NULL OR EXISTS (
                    SELECT 1 FROM ingestion.fetch_events AS fetch_event
                    WHERE fetch_event.id=:fetch_id AND fetch_event.crawl_run_id=run.id
                      AND fetch_event.source_id=run.source_id
                  ))
                  AND (CAST(:extraction_id AS bigint) IS NULL OR EXISTS (
                    SELECT 1 FROM ingestion.extraction_runs AS extraction
                    JOIN ingestion.fetch_events AS extraction_fetch
                      ON extraction_fetch.id=extraction.fetch_event_id
                    WHERE extraction.id=:extraction_id
                      AND extraction.crawl_run_id=run.id
                      AND extraction_fetch.source_id=run.source_id
                  ))
                """
            ).bindparams(sa.bindparam("details", type_=JSONB)),
            {
                "run_id": run_id,
                "task_id": error.task_id,
                "fetch_id": error.fetch_event_id,
                "extraction_id": error.extraction_run_id,
                "source_id": source_id,
                "stage": error.stage,
                "category": error.category,
                "error_code": error.error_code,
                "retryable": error.retryable,
                "source_job_id": error.source_job_id,
                "url": error.url,
                "http_status": error.http_status,
                "message": safe_message,
                "details": {key: value for key, value in error.details.items() if key != "run_id"},
                "occurred_at": occurred_at,
            },
        )
        if result.rowcount != 1:
            raise ValueError("crawl error lineage does not match its crawl run source")


class IngestionRunner:
    """Execute one bounded crawl run with persisted evidence at every stage."""

    def __init__(
        self,
        *,
        adapter: IngestionAdapter,
        store: RunnerStore,
        configuration: RunConfiguration,
        source_job_id_from_url: Callable[[str], str],
        transport_observer: AttemptObserver | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        retry_policy: Callable[[int | None, int, int | None], RetryDecision] | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._configuration = configuration
        self._source_job_id_from_url = source_job_id_from_url
        self._transport_observer = transport_observer
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._retry_policy = retry_policy or retry_decision

    def run(self) -> RunResult:
        started_at = self._aware_now()
        run_id = self._store.create_run(self._configuration, started_at)
        discovery_task_id = self._store.discovery_task_id(run_id)
        self._discard_observed_attempts()
        try:
            discovery_budget = (
                self._configuration.maximum_requests_per_run - self._configuration.requested_limit
                if self._configuration.mode == "live"
                else None
            )
            urls = self._adapter.discover_job_urls(
                self._configuration.requested_limit,
                request_budget=discovery_budget,
            )
        except Exception as error:
            self._persist_discovery_attempts(run_id, discovery_task_id)
            evidence = CrawlErrorEvidence(
                stage="discovery",
                category=_exception_category(error),
                message=str(error),
                retryable=False,
                task_id=discovery_task_id,
                url=self._configuration.discovery_url,
                error_code=type(error).__name__,
            )
            self._store.fail_discovery(run_id, discovery_task_id, evidence, self._aware_now())
            return self._store.finalize_run(run_id, self._aware_now())

        discovery_attempts = self._persist_discovery_attempts(run_id, discovery_task_id)
        if not urls:
            evidence = CrawlErrorEvidence(
                stage="policy" if self._configuration.mode == "live" else "discovery",
                category=(
                    "policy_blocked" if self._configuration.mode == "live" else "invalid_content"
                ),
                message="no job URL discovered within the allowed discovery request budget",
                retryable=False,
                task_id=discovery_task_id,
                url=self._configuration.discovery_url,
                error_code="policy_discovery_budget_exhausted",
            )
            self._store.fail_discovery(run_id, discovery_task_id, evidence, self._aware_now())
            return self._store.finalize_run(run_id, self._aware_now())
        try:
            planned_tasks = self._plan_tasks(urls)
            if self._configuration.mode == "live":
                available_first_attempts = max(
                    0,
                    self._configuration.maximum_requests_per_run - discovery_attempts,
                )
                planned_tasks = planned_tasks[:available_first_attempts]
            if not planned_tasks:
                raise PolicyViolationError(
                    "no detail task fits within the source policy request budget"
                )
        except Exception as error:
            evidence = CrawlErrorEvidence(
                stage="discovery",
                category=_exception_category(error),
                message=str(error),
                retryable=False,
                task_id=discovery_task_id,
                url=self._configuration.discovery_url,
                error_code=type(error).__name__,
            )
            self._store.fail_discovery(run_id, discovery_task_id, evidence, self._aware_now())
            return self._store.finalize_run(run_id, self._aware_now())
        self._store.complete_discovery(run_id, planned_tasks)

        return self.resume(run_id)

    def resume(self, run_id: UUID) -> RunResult:
        """Process currently due tasks for an already-created running crawl run."""

        while True:
            if (
                self._configuration.mode == "live"
                and self._store.request_attempt_count(run_id)
                >= self._configuration.maximum_requests_per_run
            ):
                self._store.exhaust_pending_tasks_for_budget(run_id, self._aware_now())
                break
            task = self._store.claim_task(run_id)
            if task is None:
                break
            exhausted = self._execute_task(task)
            if exhausted and self._configuration.fail_fast:
                self._store.skip_pending_tasks(run_id, self._aware_now())
                break

        if self._store.has_pending_tasks(run_id):
            return RunResult(run_id=run_id, status="running", counters=RunCounters())
        return self._store.finalize_run(run_id, self._aware_now())

    def _plan_tasks(self, urls: Sequence[str]) -> tuple[PlannedTask, ...]:
        planned: list[PlannedTask] = []
        seen_urls: set[str] = set()
        seen_ids: set[str] = set()
        for url in urls:
            if len(planned) >= self._configuration.requested_limit:
                break
            if url in seen_urls:
                continue
            if self._configuration.mode == "live" and not url_allowed_by_policy(
                url,
                self._configuration.approved_paths,
                self._configuration.blocked_paths,
            ):
                raise PolicyViolationError(
                    "discovered URL is blocked or not approved by source policy"
                )
            source_job_id = self._source_job_id_from_url(url)
            if source_job_id in seen_ids:
                continue
            discovery_method = "curated_it_listing"
            method_for = getattr(self._adapter, "discovery_method_for", None)
            if callable(method_for):
                discovery_method = str(method_for(url))
            planned.append(
                PlannedTask(
                    requested_url=url,
                    source_job_id=source_job_id,
                    discovery_method=discovery_method,
                    payload={"discovered_url": url},
                )
            )
            seen_urls.add(url)
            seen_ids.add(source_job_id)
        return tuple(planned)

    def _execute_task(self, task: ClaimedTask) -> bool:
        self._discard_observed_attempts()
        started = self._monotonic()
        try:
            page = self._adapter.fetch_job_detail(task.requested_url)
        except Exception as error:
            duration_ms = max(0, round((self._monotonic() - started) * 1000))
            observed = self._take_single_observed_attempt()
            occurred_at = observed.occurred_at if observed is not None else self._aware_now()
            category = _exception_category(error)
            if isinstance(error, PolicyViolationError):
                policy_error = CrawlErrorEvidence(
                    stage="policy",
                    category="policy_blocked",
                    message=str(error),
                    retryable=False,
                    task_id=task.id,
                    source_job_id=task.source_job_id,
                    url=task.requested_url,
                    error_code=type(error).__name__,
                    details={"attempt_number": task.attempt_number},
                )
                status = self._store.fail_task(
                    task,
                    policy_error,
                    occurred_at,
                    RetryDecision(False, None),
                )
                return status == "failed"
            outcome: FetchOutcome
            if category == "timeout":
                outcome = "timeout"
            elif category == "network_error":
                outcome = "network_error"
            else:
                outcome = "other_error"
            evidence = FetchEvidence(
                requested_url=task.requested_url,
                resolved_url=None,
                http_status=None,
                content_type=None,
                response_bytes=None,
                duration_ms=duration_ms,
                attempt_number=task.attempt_number,
                outcome=outcome,
                fetched_at=occurred_at,
            )
            stored = self._store.persist_fetch(
                task.run_id, task.id, task.source_id, task.source_job_id, evidence, None
            )
            retry = (
                self._retry_policy(None, task.attempt_number, None)
                if category in {"timeout", "network_error"}
                else RetryDecision(False, None)
            )
            error_evidence = self._fetch_error(task, stored, evidence, error, retry.retryable)
            status = self._store.fail_task(task, error_evidence, self._aware_now(), retry)
            return status == "failed"

        duration_ms = max(0, round((self._monotonic() - started) * 1000))
        observed = self._take_single_observed_attempt()
        headers = page.headers
        fixture_key = observed.fixture_key if observed is not None else None
        outcome = _http_outcome(page.status)
        evidence = FetchEvidence(
            requested_url=task.requested_url,
            resolved_url=page.url,
            http_status=page.status,
            content_type=page.content_type,
            response_bytes=len(page.body),
            duration_ms=duration_ms,
            attempt_number=task.attempt_number,
            outcome=outcome,
            fetched_at=page.fetched_at,
            response_headers=headers,
        )
        raw_decision = self._raw_decision(page, fixture_key)
        stored = self._store.persist_fetch(
            task.run_id, task.id, task.source_id, task.source_job_id, evidence, raw_decision
        )
        self._record_storage_error(task, stored)
        if page.status < 200 or page.status >= 400:
            retry_after = _parse_retry_after(headers, self._aware_now())
            retry = self._retry_policy(page.status, task.attempt_number, retry_after)
            http_error = RuntimeError(f"detail request returned HTTP {page.status}")
            error_evidence = self._fetch_error(task, stored, evidence, http_error, retry.retryable)
            status = self._store.fail_task(task, error_evidence, self._aware_now(), retry)
            return status == "failed"

        extraction_id = self._store.begin_extraction(
            task.run_id,
            stored,
            self._configuration.parser_version_id,
            self._aware_now(),
        )
        try:
            source_record = self._adapter.extract_raw_record(page)
            self._validate_record(task, source_record)
            extracted = self._accepted_record(source_record, stored)
        except Exception as error:
            rejected = self._rejected_record(task, stored, error)
            error_evidence = CrawlErrorEvidence(
                stage="extraction",
                category=_exception_category(error, parsing=True),
                message=str(error),
                retryable=False,
                task_id=task.id,
                fetch_event_id=stored.id,
                extraction_run_id=extraction_id,
                source_job_id=task.source_job_id,
                url=task.requested_url,
                error_code=type(error).__name__,
                details={
                    "run_id": str(task.run_id),
                    "parser_version": self._configuration.parser_version,
                },
            )
            self._store.fail_extraction(
                task.run_id,
                extraction_id,
                task.source_id,
                stored,
                rejected,
                error_evidence,
            )
            status = self._store.fail_task(
                task,
                dataclasses.replace(error_evidence, extraction_run_id=extraction_id),
                self._aware_now(),
                RetryDecision(False, None),
                persist_error=False,
            )
            return status == "failed"

        self._store.complete_extraction(extraction_id, task.source_id, stored, extracted)
        self._store.complete_task(task.id, self._aware_now())
        return False

    def _raw_decision(self, page: FetchResult, fixture_key: str | None) -> RawStorageDecision:
        if self._configuration.mode == "fixture" and self._configuration.allow_raw_storage:
            if fixture_key is not None:
                return fixture_raw_decision(
                    page.body,
                    fixture_key,
                    page.fetched_at,
                    self._configuration.raw_retention_days,
                    mime_type=page.content_type,
                )
            return suppressed_raw_decision(
                page.body,
                page.fetched_at,
                self._configuration.raw_retention_days,
                policy_allows_storage=True,
                mime_type=page.content_type,
            )
        if page.content_type and "json" in page.content_type.casefold():
            return inline_json_raw_decision(
                page.body,
                page.fetched_at,
                self._configuration.raw_retention_days,
                allow_raw_storage=self._configuration.allow_raw_storage,
                mime_type=page.content_type,
            )
        return suppressed_raw_decision(
            page.body,
            page.fetched_at,
            self._configuration.raw_retention_days,
            policy_allows_storage=self._configuration.allow_raw_storage,
            mime_type=page.content_type,
        )

    def _persist_discovery_attempts(self, run_id: UUID, task_id: int) -> int:
        if self._transport_observer is None:
            return 0
        attempts = self._transport_observer.drain_attempts()
        for number, attempt in enumerate(attempts, start=1):
            if attempt.response is None:
                outcome: FetchOutcome = (
                    "timeout" if isinstance(attempt.error, TimeoutError) else "network_error"
                )
                evidence = FetchEvidence(
                    requested_url=attempt.requested_url,
                    resolved_url=None,
                    http_status=None,
                    content_type=None,
                    response_bytes=None,
                    duration_ms=0,
                    attempt_number=number,
                    outcome=outcome,
                    fetched_at=attempt.occurred_at,
                )
                raw_decision = None
            else:
                response = attempt.response
                evidence = FetchEvidence(
                    requested_url=attempt.requested_url,
                    resolved_url=response.url,
                    http_status=response.status,
                    content_type=response.content_type,
                    response_bytes=len(response.body),
                    duration_ms=0,
                    attempt_number=number,
                    outcome=_http_outcome(response.status),
                    fetched_at=response.fetched_at,
                    response_headers=response.headers,
                )
                raw_decision = self._raw_decision(response, attempt.fixture_key)
            stored = self._store.persist_fetch(
                run_id,
                task_id,
                self._configuration.source_id,
                None,
                evidence,
                raw_decision,
            )
            if stored.storage_error is not None:
                self._store.record_error(
                    run_id,
                    CrawlErrorEvidence(
                        stage="raw_storage",
                        category="storage_error",
                        message=stored.storage_error,
                        retryable=False,
                        task_id=task_id,
                        fetch_event_id=stored.id,
                        url=attempt.requested_url,
                        error_code="raw_storage_failed",
                    ),
                    attempt.occurred_at,
                )
        return len(attempts)

    def _validate_record(self, task: ClaimedTask, record: SourceRawJobRecord) -> None:
        if record.source != self._configuration.source_slug:
            raise ValueError("extracted record source does not match crawl source")
        if record.source_job_id != task.source_job_id:
            raise ValueError("extracted record source job ID does not match task identity")
        if record.source_url != task.requested_url:
            raise ValueError("extracted record URL does not match task URL")
        if not record.title_raw.strip() or not record.description_raw.strip():
            raise ValueError("extracted record is missing required direct evidence")

    def _accepted_record(self, record: SourceRawJobRecord, fetch: StoredFetch) -> ExtractionRecord:
        description: JsonValue = (
            record.description_raw if self._configuration.allow_description_storage else None
        )
        provenance = record.closed_state_provenance
        payload: dict[str, JsonValue] = {
            "source": record.source,
            "source_job_id": record.source_job_id,
            "source_url": record.source_url,
            "title_raw": record.title_raw,
            "source_category_raw": record.source_category_raw,
            "discovery_method": record.discovery_method,
            "company_name_raw": record.company_name_raw,
            "location_raw": record.location_raw,
            "salary_raw": record.salary_raw,
            "skills_raw": list(record.skills_raw) if record.skills_raw is not None else None,
            "posted_at_raw": record.posted_at_raw,
            "expires_at_raw": record.expires_at_raw,
            "experience_raw": record.experience_raw,
            "employment_type_raw": record.employment_type_raw,
            "description_raw": description,
            "description_storage_suppressed": not self._configuration.allow_description_storage,
            "closed_state": record.closed_state,
            "closed_state_provenance": {
                "state": provenance.state,
                "source_field": provenance.source_field,
                "raw_value": provenance.raw_value,
                "parsed_datetime": _isoformat(provenance.parsed_datetime),
                "comparison_timestamp": _isoformat(provenance.comparison_timestamp),
                "decision_method": provenance.decision_method,
                "confidence": provenance.confidence,
            },
            "collected_at": _isoformat(record.collected_at),
            "content_hash": record.content_hash,
            "response_hash": fetch.raw_sha256,
        }
        return ExtractionRecord(
            source_job_id=record.source_job_id,
            record_schema_version=self._configuration.record_schema_version,
            direct_payload=payload,
            direct_hash=direct_payload_sha256(cast(dict[str, Any], payload)),
            extracted_at=self._aware_now(),
            processing_status="accepted",
        )

    def _rejected_record(
        self, task: ClaimedTask, fetch: StoredFetch, error: Exception
    ) -> ExtractionRecord:
        reason = sanitize_error(str(error)) or "extraction rejected"
        payload: dict[str, JsonValue] = {
            "source": self._configuration.source_slug,
            "source_job_id": task.source_job_id,
            "source_url": task.requested_url,
            "response_hash": fetch.raw_sha256,
            "rejection_reason": reason,
        }
        return ExtractionRecord(
            source_job_id=task.source_job_id,
            record_schema_version=self._configuration.record_schema_version,
            direct_payload=payload,
            direct_hash=direct_payload_sha256(cast(dict[str, Any], payload)),
            extracted_at=self._aware_now(),
            processing_status="rejected",
            rejection_reason=reason,
        )

    def _fetch_error(
        self,
        task: ClaimedTask,
        stored: StoredFetch,
        evidence: FetchEvidence,
        error: Exception,
        retryable: bool,
    ) -> CrawlErrorEvidence:
        return CrawlErrorEvidence(
            stage="fetch",
            category=_fetch_category(evidence),
            message=str(error),
            retryable=retryable,
            task_id=task.id,
            fetch_event_id=stored.id,
            source_job_id=task.source_job_id,
            url=task.requested_url,
            http_status=evidence.http_status,
            error_code=type(error).__name__,
            details={"attempt_number": task.attempt_number},
        )

    def _record_storage_error(self, task: ClaimedTask, fetch: StoredFetch) -> None:
        if fetch.storage_error is None:
            return
        self._store.record_error(
            task.run_id,
            CrawlErrorEvidence(
                stage="raw_storage",
                category="storage_error",
                message=fetch.storage_error,
                retryable=False,
                task_id=task.id,
                fetch_event_id=fetch.id,
                source_job_id=task.source_job_id,
                url=task.requested_url,
                error_code="raw_storage_failed",
            ),
            self._aware_now(),
        )

    def _discard_observed_attempts(self) -> None:
        if self._transport_observer is not None:
            self._transport_observer.drain_attempts()

    def _take_single_observed_attempt(self) -> TransportAttempt | None:
        if self._transport_observer is None:
            return None
        attempts = self._transport_observer.drain_attempts()
        return attempts[-1] if attempts else None

    def _aware_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("runner clock must return timezone-aware timestamps")
        return value


def recover_stale_tasks(
    store: RunnerStore | sa.Connection,
    older_than_seconds: int,
    *,
    now: datetime | None = None,
) -> int:
    """Requeue or exhaust stale running tasks without touching terminal runs."""

    recovered_at = now or datetime.now(UTC)
    if recovered_at.tzinfo is None or recovered_at.utcoffset() is None:
        raise ValueError("recovery timestamp must be timezone-aware")
    if isinstance(store, sa.Connection):
        if older_than_seconds < 1:
            raise ValueError("older_than_seconds must be at least 1")
        cutoff = recovered_at - timedelta(seconds=older_than_seconds)
        result = store.execute(
            sa.text(
                """
                UPDATE ingestion.crawl_tasks AS task
                SET status=CASE
                      WHEN task.attempt_count >= task.max_attempts THEN 'failed'
                      ELSE 'pending'
                    END,
                    scheduled_for=CASE
                      WHEN task.attempt_count >= task.max_attempts THEN NULL
                      ELSE :recovered_at
                    END,
                    finished_at=:recovered_at,
                    updated_at=:recovered_at
                FROM ingestion.crawl_runs AS run
                WHERE task.crawl_run_id=run.id
                  AND run.status='running'
                  AND task.status='running'
                  AND task.started_at<:cutoff
                """
            ),
            {"cutoff": cutoff, "recovered_at": recovered_at},
        )
        return result.rowcount or 0
    return store.recover_stale_tasks(older_than_seconds, recovered_at)


def _http_outcome(status: int) -> FetchOutcome:
    return "success" if 200 <= status <= 399 else "http_error"


def _fetch_category(evidence: FetchEvidence) -> ErrorCategory:
    if evidence.outcome == "blocked_by_policy":
        return "policy_blocked"
    if evidence.outcome == "timeout":
        return "timeout"
    if evidence.outcome == "network_error":
        return "network_error"
    if evidence.http_status == 429:
        return "rate_limited"
    return "http_error"


def _exception_category(error: Exception, *, parsing: bool = False) -> ErrorCategory:
    if isinstance(error, PolicyViolationError):
        return "policy_blocked"
    if isinstance(error, TimeoutError):
        return "timeout"
    if parsing:
        return "parse_error" if isinstance(error, ValueError) else "unexpected"
    if isinstance(error, (ConnectionError, OSError)):
        return "network_error"
    if isinstance(error, ValueError):
        return "invalid_url"
    return "unexpected"


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    name = name.casefold()
    return next((value for key, value in headers.items() if key.casefold() == name), None)


def _parse_retry_after(headers: Mapping[str, str], now: datetime) -> int | None:
    value = _header_value(headers, "retry-after")
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None or retry_at.utcoffset() is None:
            return None
        seconds = round((retry_at - now).total_seconds())
    return seconds if 0 < seconds <= 300 else None


def _validate_path_patterns(patterns: Sequence[str], field_name: str) -> None:
    for pattern in patterns:
        if not pattern or not pattern.startswith("/") or "?" in pattern or "#" in pattern:
            raise ValueError(f"{field_name} must contain absolute URL-path patterns")


def _path_matches(path: str, pattern: str) -> bool:
    if pattern == "/":
        return True
    if any(character in pattern for character in "*["):
        return fnmatchcase(path, pattern)
    normalized = pattern.rstrip("/")
    return path == normalized or path.startswith(f"{normalized}/")


def url_blocked_by_policy(url: str, blocked_paths: Sequence[str]) -> bool:
    path = urlparse(url).path or "/"
    return any(_path_matches(path, pattern) for pattern in blocked_paths)


def url_allowed_by_policy(
    url: str, approved_paths: Sequence[str], blocked_paths: Sequence[str]
) -> bool:
    """Apply blocked-before-approved URL path policy semantics."""

    path = urlparse(url).path or "/"
    if url_blocked_by_policy(url, blocked_paths):
        return False
    return any(_path_matches(path, pattern) for pattern in approved_paths)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("direct evidence datetimes must be timezone-aware")
    return value.isoformat()
