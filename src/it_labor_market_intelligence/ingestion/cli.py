"""Secret-safe operator CLI for the bounded TopDev ingestion worker."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO, cast
from urllib.parse import urljoin, urlparse, urlunparse
from uuid import UUID

import sqlalchemy as sa

from it_labor_market_intelligence.adapters.topdev import (
    TOPDEV_IT_LISTING,
    PoliteUrllibTransport,
    extract_job_id,
)

from .adapters.topdev_registration import (
    BootstrapResult,
    EnableRejected,
    ParserVersionConflict,
    PolicyState,
    SourceState,
    TopDevRegistration,
    discover_git_commit_sha,
    enable_topdev,
    register_topdev,
)
from .contracts import FetchTransport, FixtureResponse, IngestionAdapter, JsonValue
from .runner import (
    FixtureTransport,
    IngestionRunner,
    ObservedTransport,
    PolicyEnforcingTransport,
    PostgreSQLRunnerStore,
    RunConfiguration,
    RunResult,
    url_allowed_by_policy,
    url_blocked_by_policy,
)
from .sanitization import sanitize_error

EXIT_SUCCEEDED = 0
EXIT_PARTIALLY_SUCCEEDED = 2
EXIT_CONFIGURATION_REJECTED = 3
EXIT_ALL_TASKS_FAILED = 4
EXIT_INTERNAL_FAILURE = 5


class CLIRejected(ValueError):
    """An operator request rejected before ingestion writes begin."""


@dataclass(frozen=True, slots=True)
class RunRequest:
    source: str
    limit: int | None
    mode: Literal["fixture", "live"]
    trigger: Literal["manual", "scheduled", "backfill", "test"]
    fixture_dir: Path | None
    fail_fast: bool
    dry_run: bool


@dataclass(frozen=True, slots=True)
class RunPlan:
    configuration: RunConfiguration
    source_enabled: bool
    policy_approved: bool
    policy_maximum: int
    fixture_dir: Path | None
    requests_already_attempted: int = 0

    def safe_summary(self) -> dict[str, JsonValue]:
        return {
            "allow_description_storage": self.configuration.allow_description_storage,
            "allow_raw_storage": self.configuration.allow_raw_storage,
            "command": "run",
            "dry_run": True,
            "fail_fast": self.configuration.fail_fast,
            "limit": self.configuration.requested_limit,
            "mode": self.configuration.mode,
            "policy_maximum": self.policy_maximum,
            "source": self.configuration.source_slug,
            "trigger": self.configuration.trigger_type,
        }


class CLIService(Protocol):
    def bootstrap_topdev(self, enable: bool) -> BootstrapResult: ...

    def plan_run(self, request: RunRequest) -> RunPlan: ...

    def execute_run(self, plan: RunPlan) -> RunResult: ...

    def retry_run(self, run_id: UUID, fixture_dir: Path | None) -> RunResult: ...

    def inspect_run(self, run_id: UUID) -> dict[str, JsonValue]: ...

    def requeue_stale(self, older_than_seconds: int) -> int: ...


class PostgreSQLBootstrapRepository:
    """Registration statements scoped to a caller-owned transaction."""

    def __init__(self, connection: sa.Connection) -> None:
        self._connection = connection

    def upsert_source(self, registration: TopDevRegistration) -> SourceState:
        row = self._connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.sources (
                    slug, display_name, base_url, source_type, country_code,
                    status, is_enabled
                ) VALUES (
                    :slug, :display_name, :base_url, :source_type, :country_code,
                    'researching', false
                )
                ON CONFLICT (slug) DO UPDATE SET
                    display_name=EXCLUDED.display_name,
                    base_url=EXCLUDED.base_url,
                    source_type=EXCLUDED.source_type,
                    country_code=EXCLUDED.country_code,
                    updated_at=now()
                RETURNING id, is_enabled
                """
            ),
            {
                "slug": registration.slug,
                "display_name": registration.display_name,
                "base_url": registration.base_url,
                "source_type": registration.source_type,
                "country_code": registration.country_code,
            },
        ).one()
        return SourceState(id=cast(UUID, row[0]), enabled=bool(row[1]))

    def has_reviewed_policy(self, source_id: UUID) -> bool:
        return bool(
            self._connection.execute(
                sa.text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM ingestion.source_policies
                        WHERE source_id=:source_id
                          AND (robots_review_status!='not_reviewed'
                               OR terms_review_status!='not_reviewed'
                               OR reviewed_at IS NOT NULL)
                    )
                    """
                ),
                {"source_id": source_id},
            ).scalar_one()
        )

    def insert_default_policy(self, source_id: UUID, registration: TopDevRegistration) -> bool:
        result = self._connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.source_policies (
                    source_id, policy_version, robots_review_status,
                    terms_review_status, approved_paths, blocked_paths,
                    minimum_request_interval_seconds, maximum_requests_per_run,
                    maximum_concurrent_requests, raw_retention_days,
                    description_retention_days, allow_raw_storage,
                    allow_description_storage, notes
                ) VALUES (
                    :source_id, :policy_version, 'not_reviewed', 'not_reviewed',
                    '["/viec-lam/*", "/detail-jobs/*"]'::jsonb,
                    '[]'::jsonb, 2.000, 30, 1, 30, 90,
                    true, true, 'Bootstrap defaults; requires explicit robots and terms review.'
                )
                ON CONFLICT (source_id, policy_version) DO NOTHING
                """
            ),
            {"source_id": source_id, "policy_version": registration.policy_version},
        )
        return bool(result.rowcount)

    def current_approved_policy(self, source_id: UUID, at: datetime) -> PolicyState | None:
        row = self._connection.execute(
            sa.text(
                """
                SELECT id, policy_version, minimum_request_interval_seconds,
                       maximum_requests_per_run, maximum_concurrent_requests,
                       approved_paths, blocked_paths, raw_retention_days,
                       description_retention_days, allow_raw_storage,
                       allow_description_storage
                FROM ingestion.source_policies
                WHERE source_id=:source_id
                  AND robots_review_status='approved'
                  AND terms_review_status='approved'
                  AND valid_from<=:at
                  AND (valid_to IS NULL OR valid_to>:at)
                ORDER BY valid_from DESC, created_at DESC, id
                LIMIT 1
                """
            ),
            {"source_id": source_id, "at": at},
        ).first()
        if row is None:
            return None
        return PolicyState(
            id=cast(UUID, row[0]),
            policy_version=str(row[1]),
            minimum_request_interval_seconds=float(row[2]),
            maximum_requests_per_run=int(row[3]),
            maximum_concurrent_requests=int(row[4]),
            approved_paths=_path_tuple(row[5], "approved_paths"),
            blocked_paths=_path_tuple(row[6], "blocked_paths"),
            raw_retention_days=cast(int | None, row[7]),
            description_retention_days=cast(int | None, row[8]),
            allow_raw_storage=bool(row[9]),
            allow_description_storage=bool(row[10]),
        )

    def rotate_parser(
        self,
        source_id: UUID,
        registration: TopDevRegistration,
        configuration_hash: str,
        git_commit_sha: str | None,
        at: datetime,
    ) -> None:
        self._connection.execute(
            sa.text("SELECT id FROM ingestion.sources WHERE id=:source_id FOR UPDATE"),
            {"source_id": source_id},
        ).one()
        existing = self._connection.execute(
            sa.text(
                """
                SELECT id, schema_version, configuration_hash
                FROM ingestion.parser_versions
                WHERE source_id=:source_id AND parser_name=:parser_name
                  AND version=:version
                FOR UPDATE
                """
            ),
            {
                "source_id": source_id,
                "parser_name": registration.parser_name,
                "version": registration.parser_version,
            },
        ).first()
        if existing is not None and (
            str(existing[1]) != registration.schema_version
            or cast(str | None, existing[2]) != configuration_hash
        ):
            raise ParserVersionConflict(
                "parser version already exists with different schema or configuration; "
                "increment ADAPTER_VERSION"
            )
        if existing is None:
            parser_id = cast(
                UUID,
                self._connection.execute(
                    sa.text(
                        """
                        INSERT INTO ingestion.parser_versions (
                            source_id, parser_name, version, schema_version,
                            git_commit_sha, configuration_hash, is_active
                        ) VALUES (
                            :source_id, :parser_name, :version, :schema_version,
                            :git_sha, :configuration_hash, false
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "source_id": source_id,
                        "parser_name": registration.parser_name,
                        "version": registration.parser_version,
                        "schema_version": registration.schema_version,
                        "git_sha": git_commit_sha,
                        "configuration_hash": configuration_hash,
                    },
                ).scalar_one(),
            )
        else:
            parser_id = cast(UUID, existing[0])

        self._connection.execute(
            sa.text(
                """
                UPDATE ingestion.parser_versions
                SET is_active=false,
                    retired_at=COALESCE(retired_at, GREATEST(:at, created_at))
                WHERE source_id=:source_id AND parser_name=:parser_name
                  AND is_active AND id!=:parser_id
                """
            ),
            {
                "source_id": source_id,
                "parser_name": registration.parser_name,
                "parser_id": parser_id,
                "at": at,
            },
        )
        self._connection.execute(
            sa.text(
                """
                UPDATE ingestion.parser_versions
                SET is_active=true, retired_at=NULL
                WHERE id=:parser_id
                """
            ),
            {"parser_id": parser_id},
        )

    def enable_source(self, source_id: UUID, at: datetime) -> None:
        self._connection.execute(
            sa.text(
                """
                UPDATE ingestion.sources
                SET status='approved', is_enabled=true, updated_at=:at
                WHERE id=:source_id
                """
            ),
            {"source_id": source_id, "at": at},
        )


class PostgreSQLCLIService:
    """Database-backed CLI operations with explicit read/write boundaries."""

    def __init__(
        self,
        engine: sa.Engine,
        *,
        now: Callable[[], datetime] | None = None,
        git_commit_sha: str | None = None,
        live_transport_factory: Callable[[float], FetchTransport] | None = None,
    ) -> None:
        self._engine = engine
        self._now = now or (lambda: datetime.now(UTC))
        self._git_commit_sha = git_commit_sha
        self._live_transport_factory = live_transport_factory or PoliteUrllibTransport

    def bootstrap_topdev(self, enable: bool) -> BootstrapResult:
        now = self._aware_now()
        with self._engine.begin() as connection:
            result = register_topdev(
                PostgreSQLBootstrapRepository(connection),
                git_commit_sha=self._git_commit_sha or discover_git_commit_sha(),
                now=now,
            )
        if not enable:
            return result
        with self._engine.begin() as connection:
            enable_topdev(
                PostgreSQLBootstrapRepository(connection),
                result.source_id,
                now=now,
            )
        return replace(result, source_enabled=True)

    def plan_run(self, request: RunRequest) -> RunPlan:
        if request.source != "topdev":
            raise CLIRejected("source must be topdev")
        now = self._aware_now()
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        """
                    SELECT source.id AS source_id, source.is_enabled,
                           policy.id AS policy_id, policy.policy_version,
                           policy.robots_review_status,
                           policy.terms_review_status,
                           policy.minimum_request_interval_seconds,
                           policy.maximum_requests_per_run,
                           policy.maximum_concurrent_requests,
                           policy.approved_paths, policy.blocked_paths,
                           policy.raw_retention_days,
                           policy.description_retention_days,
                           policy.allow_raw_storage,
                           policy.allow_description_storage,
                           parser.id AS parser_id, parser.version AS parser_version,
                           parser.schema_version
                    FROM ingestion.sources AS source
                    JOIN LATERAL (
                        SELECT * FROM ingestion.source_policies
                        WHERE source_id=source.id AND valid_from<=:at
                          AND (valid_to IS NULL OR valid_to>:at)
                        ORDER BY valid_from DESC, created_at DESC, id
                        LIMIT 1
                    ) AS policy ON true
                    JOIN ingestion.parser_versions AS parser
                      ON parser.source_id=source.id
                     AND parser.parser_name='TopDevAdapter'
                     AND parser.is_active
                    WHERE source.slug='topdev'
                    """
                    ),
                    {"at": now},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CLIRejected("TopDev source, current policy, or active parser is not configured")

        policy_maximum = min(30, int(row["maximum_requests_per_run"]))
        limit = min(10, policy_maximum) if request.limit is None else request.limit
        if not 1 <= limit <= policy_maximum:
            raise CLIRejected(f"limit must be between 1 and {policy_maximum}")
        policy_approved = (
            row["robots_review_status"] == "approved" and row["terms_review_status"] == "approved"
        )
        approved_paths = _path_tuple(row["approved_paths"], "approved_paths")
        blocked_paths = _path_tuple(row["blocked_paths"], "blocked_paths")
        run_type, trigger_type = _trigger_types(request.trigger)
        configuration = RunConfiguration(
            source_id=cast(UUID, row["source_id"]),
            source_slug="topdev",
            source_policy_id=cast(UUID, row["policy_id"]),
            parser_version_id=cast(UUID, row["parser_id"]),
            requested_limit=limit,
            discovery_url=TOPDEV_IT_LISTING,
            mode=request.mode,
            run_type=run_type,
            trigger_type=trigger_type,
            policy_version=str(row["policy_version"]),
            minimum_request_interval_seconds=float(row["minimum_request_interval_seconds"]),
            maximum_requests_per_run=int(row["maximum_requests_per_run"]),
            maximum_concurrent_requests=int(row["maximum_concurrent_requests"]),
            approved_paths=approved_paths,
            blocked_paths=blocked_paths,
            raw_retention_days=cast(int | None, row["raw_retention_days"]),
            description_retention_days=cast(int | None, row["description_retention_days"]),
            allow_raw_storage=bool(row["allow_raw_storage"]),
            allow_description_storage=bool(row["allow_description_storage"]),
            fail_fast=request.fail_fast,
            git_commit_sha=self._git_commit_sha or discover_git_commit_sha(),
            parser_version=str(row["parser_version"]),
            record_schema_version=str(row["schema_version"]),
        )
        plan = RunPlan(
            configuration=configuration,
            source_enabled=bool(row["is_enabled"]),
            policy_approved=policy_approved,
            policy_maximum=policy_maximum,
            fixture_dir=request.fixture_dir,
        )
        _validate_plan(plan)
        return plan

    def execute_run(self, plan: RunPlan) -> RunResult:
        _validate_plan(plan)
        runner = self._runner_for_plan(plan)
        return runner.run()

    def retry_run(self, run_id: UUID, fixture_dir: Path | None) -> RunResult:
        now = self._aware_now()
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        """
                    SELECT run.source_id, source.slug, run.source_policy_id,
                           run.parser_version_id, run.requested_limit,
                           run.configuration_json, run.run_type, run.trigger_type,
                           run.git_commit_sha, run.status,
                           parser.version AS parser_version, parser.schema_version,
                           source.is_enabled,
                           original_policy.robots_review_status AS original_robots_status,
                           original_policy.terms_review_status AS original_terms_status,
                           current_policy.robots_review_status AS current_robots_status,
                           current_policy.terms_review_status AS current_terms_status,
                           current_policy.blocked_paths AS current_blocked_paths,
                           (SELECT count(*) FROM ingestion.fetch_events AS fetch_event
                            WHERE fetch_event.crawl_run_id=run.id) AS attempted_requests
                    FROM ingestion.crawl_runs AS run
                    JOIN ingestion.sources AS source ON source.id=run.source_id
                    JOIN ingestion.source_policies AS original_policy
                      ON original_policy.id=run.source_policy_id
                    JOIN ingestion.parser_versions AS parser ON parser.id=run.parser_version_id
                    LEFT JOIN LATERAL (
                        SELECT policy.robots_review_status, policy.terms_review_status,
                               policy.blocked_paths
                        FROM ingestion.source_policies AS policy
                        WHERE policy.source_id=run.source_id AND policy.valid_from<=:at
                          AND (policy.valid_to IS NULL OR policy.valid_to>:at)
                        ORDER BY policy.valid_from DESC, policy.created_at DESC, policy.id
                        LIMIT 1
                    ) AS current_policy ON true
                    WHERE run.id=:run_id
                    """
                    ),
                    {"run_id": run_id, "at": now},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise CLIRejected("crawl run was not found")
        if row["status"] != "running":
            raise CLIRejected("only a running crawl run can be retried")
        configuration = _configuration_from_snapshot(
            cast(Mapping[str, object], row["configuration_json"]),
            source_id=cast(UUID, row["source_id"]),
            source_slug=str(row["slug"]),
            source_policy_id=cast(UUID, row["source_policy_id"]),
            parser_version_id=cast(UUID, row["parser_version_id"]),
            requested_limit=int(row["requested_limit"]),
            run_type=cast(Any, row["run_type"]),
            trigger_type=cast(Any, row["trigger_type"]),
            git_commit_sha=cast(str | None, row["git_commit_sha"]),
            parser_version=str(row["parser_version"]),
            schema_version=str(row["schema_version"]),
        )
        if configuration.mode == "live":
            if not bool(row["is_enabled"]):
                raise CLIRejected("live retry is no longer authorized because source is disabled")
            if (
                row["original_robots_status"] != "approved"
                or row["original_terms_status"] != "approved"
                or row["current_robots_status"] != "approved"
                or row["current_terms_status"] != "approved"
            ):
                raise CLIRejected("live retry is no longer authorized by source policy")
            current_blocked = _path_tuple(row["current_blocked_paths"], "blocked_paths")
            with self._engine.connect() as connection:
                continuation_urls = connection.scalars(
                    sa.text(
                        """
                        SELECT requested_url FROM ingestion.crawl_tasks
                        WHERE crawl_run_id=:run_id AND status IN ('pending', 'running')
                          AND requested_url IS NOT NULL
                        ORDER BY id
                        """
                    ),
                    {"run_id": run_id},
                ).all()
            if any(url_blocked_by_policy(str(url), current_blocked) for url in continuation_urls):
                raise CLIRejected("live retry is blocked by the current source policy")
        plan = RunPlan(
            configuration=configuration,
            source_enabled=bool(row["is_enabled"]),
            policy_approved=(
                row["current_robots_status"] == "approved"
                and row["current_terms_status"] == "approved"
            ),
            policy_maximum=min(30, configuration.maximum_requests_per_run),
            fixture_dir=fixture_dir,
            requests_already_attempted=int(row["attempted_requests"]),
        )
        _validate_plan(plan)
        return self._runner_for_plan(plan).resume(run_id)

    def inspect_run(self, run_id: UUID) -> dict[str, JsonValue]:
        with self._engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    """
                    SELECT run.id, source.slug, run.status, run.requested_limit,
                           run.configuration_json->>'mode', run.started_at, run.finished_at,
                           run.discovered_count, run.task_count,
                           run.fetch_success_count, run.fetch_failure_count,
                           run.unchanged_count, run.extracted_count,
                           run.accepted_count, run.rejected_count, run.error_count
                    FROM ingestion.crawl_runs AS run
                    JOIN ingestion.sources AS source ON source.id=run.source_id
                    WHERE run.id=:run_id
                    """
                ),
                {"run_id": run_id},
            ).first()
        if row is None:
            raise CLIRejected("crawl run was not found")
        return {
            "accepted_count": int(row[13]),
            "discovered_count": int(row[7]),
            "error_count": int(row[15]),
            "extracted_count": int(row[12]),
            "fetch_failure_count": int(row[10]),
            "fetch_success_count": int(row[9]),
            "finished_at": _safe_datetime(row[6]),
            "mode": cast(str | None, row[4]),
            "rejected_count": int(row[14]),
            "requested_limit": cast(int | None, row[3]),
            "run_id": str(row[0]),
            "source": str(row[1]),
            "started_at": _safe_datetime(row[5]),
            "status": str(row[2]),
            "task_count": int(row[8]),
            "unchanged_count": int(row[11]),
        }

    def requeue_stale(self, older_than_seconds: int) -> int:
        return PostgreSQLRunnerStore(self._engine).recover_stale_tasks(
            older_than_seconds, self._aware_now()
        )

    def _runner_for_plan(self, plan: RunPlan) -> IngestionRunner:
        registration = TopDevRegistration()
        observer: FixtureTransport | ObservedTransport | None = None
        if plan.configuration.mode == "fixture":
            fixture_dir = plan.fixture_dir or Path("tests/fixtures/topdev")
            observer = _fixture_transport(fixture_dir, self._aware_now())
            adapter = registration.adapter(observer)
        else:
            live_transport = self._live_transport_factory(
                plan.configuration.minimum_request_interval_seconds
            )
            observer = ObservedTransport(live_transport, now=self._now)
            policy_transport = PolicyEnforcingTransport(
                observer,
                approved_paths=plan.configuration.approved_paths,
                blocked_paths=plan.configuration.blocked_paths,
                maximum_requests=plan.configuration.maximum_requests_per_run,
                maximum_concurrent_requests=plan.configuration.maximum_concurrent_requests,
                initial_request_count=plan.requests_already_attempted,
            )
            adapter = registration.adapter(policy_transport)
        return IngestionRunner(
            adapter=cast(IngestionAdapter, adapter),
            store=PostgreSQLRunnerStore(self._engine),
            configuration=plan.configuration,
            source_job_id_from_url=extract_job_id,
            transport_observer=observer,
            now=self._now,
        )

    def _aware_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("CLI clock must return a timezone-aware timestamp")
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m it_labor_market_intelligence.ingestion.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    bootstrap = commands.add_parser("bootstrap-topdev")
    bootstrap.add_argument("--enable", action="store_true")

    run = commands.add_parser("run")
    run.add_argument("--source", default="topdev")
    run.add_argument("--limit", type=int)
    run.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    run.add_argument(
        "--trigger", choices=("manual", "scheduled", "backfill", "test"), default="manual"
    )
    run.add_argument("--fixture-dir", type=Path)
    run.add_argument("--fail-fast", action="store_true")
    run.add_argument("--dry-run", action="store_true")

    retry = commands.add_parser("retry-run")
    retry.add_argument("--run-id", required=True)
    retry.add_argument("--fixture-dir", type=Path)

    inspect = commands.add_parser("inspect-run")
    inspect.add_argument("--run-id", required=True)

    stale = commands.add_parser("requeue-stale")
    stale.add_argument("--older-than-seconds", type=int, required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    service: CLIService | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute one command and return its specification-defined exit code."""

    import sys

    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    arguments = build_parser().parse_args(argv)
    try:
        active_service = service or PostgreSQLCLIService(_engine())
        if arguments.command == "bootstrap-topdev":
            bootstrap_result = active_service.bootstrap_topdev(bool(arguments.enable))
            _write_json(
                output,
                {
                    "command": "bootstrap-topdev",
                    "enabled": bootstrap_result.source_enabled,
                    "parser_version": bootstrap_result.parser_version,
                    "policy_created": bootstrap_result.policy_created,
                    "source": "topdev",
                },
            )
            return EXIT_SUCCEEDED
        if arguments.command == "run":
            request = RunRequest(
                source=str(arguments.source),
                limit=cast(int | None, arguments.limit),
                mode=cast(Literal["fixture", "live"], arguments.mode),
                trigger=cast(Literal["manual", "scheduled", "backfill", "test"], arguments.trigger),
                fixture_dir=cast(Path | None, arguments.fixture_dir),
                fail_fast=bool(arguments.fail_fast),
                dry_run=bool(arguments.dry_run),
            )
            if request.source != "topdev":
                raise CLIRejected("source must be topdev")
            plan = active_service.plan_run(request)
            _validate_plan(plan)
            if request.dry_run:
                _write_json(output, plan.safe_summary())
                return EXIT_SUCCEEDED
            run_result = active_service.execute_run(plan)
            _write_json(output, _run_result_summary(run_result))
            return _run_exit_code(run_result)
        if arguments.command == "retry-run":
            retry_result = active_service.retry_run(
                _run_id(arguments.run_id), cast(Path | None, arguments.fixture_dir)
            )
            _write_json(output, _run_result_summary(retry_result))
            return _run_exit_code(retry_result)
        if arguments.command == "inspect-run":
            _write_json(output, active_service.inspect_run(_run_id(arguments.run_id)))
            return EXIT_SUCCEEDED
        if arguments.command == "requeue-stale":
            age = int(arguments.older_than_seconds)
            if age < 1:
                raise CLIRejected("older-than-seconds must be at least 1")
            count = active_service.requeue_stale(age)
            _write_json(output, {"command": "requeue-stale", "requeued_or_failed": count})
            return EXIT_SUCCEEDED
        raise CLIRejected("unsupported ingestion command")
    except (CLIRejected, EnableRejected, ValueError) as error:
        _write_error(errors, error)
        return EXIT_CONFIGURATION_REJECTED
    except Exception as error:
        _write_error(errors, error)
        return EXIT_INTERNAL_FAILURE


def _engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise CLIRejected("DATABASE_URL is required")
    return sa.create_engine(url, pool_pre_ping=True)


def _validate_plan(plan: RunPlan) -> None:
    configuration = plan.configuration
    if configuration.source_slug != "topdev":
        raise CLIRejected("source must be topdev")
    if not 1 <= configuration.requested_limit <= plan.policy_maximum:
        raise CLIRejected(f"limit must be between 1 and {plan.policy_maximum}")
    if configuration.mode == "live":
        if not plan.source_enabled or not plan.policy_approved:
            raise CLIRejected("live mode requires an enabled source and approved current policy")
        if not url_allowed_by_policy(
            configuration.discovery_url,
            configuration.approved_paths,
            configuration.blocked_paths,
        ):
            raise CLIRejected("live discovery URL is blocked or not approved by source policy")
        return
    if configuration.trigger_type != "test" and (
        not plan.source_enabled or not plan.policy_approved
    ):
        raise CLIRejected("fixture mode with a disabled or unapproved source requires trigger=test")


def _path_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CLIRejected(f"{field_name} must be a JSON array of URL-path patterns")
    paths = tuple(cast(list[str], value))
    if any(not path.startswith("/") or "?" in path or "#" in path for path in paths):
        raise CLIRejected(f"{field_name} contains an invalid URL-path pattern")
    return paths


def _snapshot_value(snapshot: Mapping[str, object], key: str) -> object:
    if key not in snapshot:
        raise CLIRejected(f"crawl run policy snapshot is missing {key}")
    return snapshot[key]


def _snapshot_int(snapshot: Mapping[str, object], key: str) -> int:
    value = _snapshot_value(snapshot, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CLIRejected(f"crawl run policy snapshot has invalid {key}")
    return value


def _snapshot_optional_int(snapshot: Mapping[str, object], key: str) -> int | None:
    value = _snapshot_value(snapshot, key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CLIRejected(f"crawl run policy snapshot has invalid {key}")
    return value


def _snapshot_bool(snapshot: Mapping[str, object], key: str) -> bool:
    value = _snapshot_value(snapshot, key)
    if not isinstance(value, bool):
        raise CLIRejected(f"crawl run policy snapshot has invalid {key}")
    return value


def _configuration_from_snapshot(
    snapshot: Mapping[str, object],
    *,
    source_id: UUID,
    source_slug: str,
    source_policy_id: UUID,
    parser_version_id: UUID,
    requested_limit: int,
    run_type: Any,
    trigger_type: Any,
    git_commit_sha: str | None,
    parser_version: str,
    schema_version: str,
) -> RunConfiguration:
    mode_value = _snapshot_value(snapshot, "mode")
    if mode_value not in {"fixture", "live"}:
        raise CLIRejected("crawl run policy snapshot has invalid mode")
    interval = _snapshot_value(snapshot, "minimum_request_interval_seconds")
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        raise CLIRejected("crawl run policy snapshot has invalid minimum_request_interval_seconds")
    snapshot_limit = _snapshot_int(snapshot, "requested_limit")
    if snapshot_limit != requested_limit:
        raise CLIRejected("crawl run requested limit does not match its immutable snapshot")
    discovery_url = _snapshot_value(snapshot, "discovery_url")
    policy_version = _snapshot_value(snapshot, "policy_version")
    if not isinstance(discovery_url, str) or not isinstance(policy_version, str):
        raise CLIRejected("crawl run policy snapshot has invalid string values")
    return RunConfiguration(
        source_id=source_id,
        source_slug=source_slug,
        source_policy_id=source_policy_id,
        parser_version_id=parser_version_id,
        requested_limit=requested_limit,
        discovery_url=discovery_url,
        mode=cast(Literal["fixture", "live"], mode_value),
        run_type=cast(Any, run_type),
        trigger_type=cast(Any, trigger_type),
        policy_version=policy_version,
        minimum_request_interval_seconds=float(interval),
        maximum_requests_per_run=_snapshot_int(snapshot, "maximum_requests_per_run"),
        maximum_concurrent_requests=_snapshot_int(snapshot, "maximum_concurrent_requests"),
        approved_paths=_path_tuple(_snapshot_value(snapshot, "approved_paths"), "approved_paths"),
        blocked_paths=_path_tuple(_snapshot_value(snapshot, "blocked_paths"), "blocked_paths"),
        raw_retention_days=_snapshot_optional_int(snapshot, "raw_retention_days"),
        description_retention_days=_snapshot_optional_int(snapshot, "description_retention_days"),
        allow_raw_storage=_snapshot_bool(snapshot, "allow_raw_storage"),
        allow_description_storage=_snapshot_bool(snapshot, "allow_description_storage"),
        fail_fast=_snapshot_bool(snapshot, "fail_fast"),
        git_commit_sha=git_commit_sha,
        parser_version=parser_version,
        record_schema_version=schema_version,
    )


def _trigger_types(
    trigger: Literal["manual", "scheduled", "backfill", "test"],
) -> tuple[
    Literal["scheduled", "manual", "backfill", "test"],
    Literal["manual", "scheduler", "test"],
]:
    if trigger == "scheduled":
        return "scheduled", "scheduler"
    if trigger == "backfill":
        return "backfill", "manual"
    if trigger == "test":
        return "test", "test"
    return "manual", "manual"


def _run_exit_code(result: RunResult) -> int:
    if result.status == "succeeded":
        return EXIT_SUCCEEDED
    if result.status in {"partially_succeeded", "running"}:
        return EXIT_PARTIALLY_SUCCEEDED
    if result.status == "failed":
        return EXIT_ALL_TASKS_FAILED
    return EXIT_INTERNAL_FAILURE


def _run_result_summary(result: RunResult) -> dict[str, JsonValue]:
    return {
        "accepted_count": result.counters.accepted_count,
        "error_count": result.counters.error_count,
        "fetch_failure_count": result.counters.fetch_failure_count,
        "fetch_success_count": result.counters.fetch_success_count,
        "rejected_count": result.counters.rejected_count,
        "run_id": str(result.run_id),
        "status": result.status,
    }


def _run_id(value: object) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as error:
        raise CLIRejected("run-id must be a valid UUID") from error


def _write_json(stream: TextIO, value: Mapping[str, object]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    stream.write("\n")


def _write_error(stream: TextIO, error: Exception) -> None:
    message = sanitize_error(str(error)) or "ingestion command failed"
    _write_json(stream, {"error": message})


def _safe_datetime(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def _fixture_transport(fixture_dir: Path, now: datetime) -> FixtureTransport:
    """Build a network-incapable transport from repository-relative fixtures."""

    root = fixture_dir.resolve()
    if not root.is_dir():
        raise CLIRejected("fixture directory does not exist")
    try:
        repository_key = root.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError as error:
        raise CLIRejected("fixture directory must be inside the repository") from error

    discovery_files = sorted(root.glob("discovery_page_*.html"))
    if not discovery_files:
        raise CLIRejected("fixture directory has no discovery_page_*.html fixture")
    responses: dict[str, list[FixtureResponse | Exception]] = {}
    fixture_keys: dict[str, str] = {}
    discovered_urls: list[str] = []
    for index, path in enumerate(discovery_files, start=1):
        url = TOPDEV_IT_LISTING if index == 1 else f"{TOPDEV_IT_LISTING}?page={index}"
        response = _fixture_response(path, url, now)
        responses[url] = [response]
        fixture_keys[url] = f"{repository_key}/{path.name}"
        parser = _LinkParser()
        parser.feed(response.body.decode("utf-8", errors="replace"))
        for href in parser.links:
            parsed = urlparse(urljoin(response.url, href))
            if (
                parsed.scheme != "https"
                or parsed.netloc.casefold() not in {"topdev.vn", "www.topdev.vn"}
                or not any(part in parsed.path for part in ("/viec-lam/", "/detail-jobs/"))
            ):
                continue
            candidate = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            try:
                extract_job_id(candidate)
            except ValueError:
                continue
            if candidate not in discovered_urls:
                discovered_urls.append(candidate)

    detail_files = sorted(path for path in root.glob("job_*.html") if path.is_file())
    assigned: set[Path] = set()
    metadata_urls: dict[str, Path] = {}
    for path in detail_files:
        metadata = _fixture_metadata(path)
        source_url = metadata.get("source_url")
        if isinstance(source_url, str):
            metadata_urls[source_url] = path
    for url in discovered_urls:
        job_id = extract_job_id(url)
        detail_path = metadata_urls.get(url)
        if detail_path is None:
            detail_path = next((item for item in detail_files if job_id in item.stem), None)
        if detail_path is None:
            detail_path = next((item for item in detail_files if item not in assigned), None)
        if detail_path is None:
            raise CLIRejected(f"fixture detail response is missing for source job {job_id}")
        assigned.add(detail_path)
        responses[url] = [_fixture_response(detail_path, url, now)]
        fixture_keys[url] = f"{repository_key}/{detail_path.name}"
    return FixtureTransport(responses, fixture_keys=fixture_keys, now=lambda: now)


def _fixture_response(path: Path, default_url: str, now: datetime) -> FixtureResponse:
    metadata = _fixture_metadata(path)
    status_value = metadata.get("http_status", 200)
    content_type_value = metadata.get("content_type", "text/html")
    source_url_value = metadata.get("source_url", default_url)
    status = int(status_value) if isinstance(status_value, (int, str)) else 200
    content_type = str(content_type_value) if content_type_value is not None else None
    source_url = str(source_url_value)
    return FixtureResponse(
        url=source_url,
        status=status,
        body=path.read_bytes(),
        fetched_at=now,
        content_type=content_type,
        headers={"Content-Type": content_type or "application/octet-stream"},
    )


def _fixture_metadata(path: Path) -> dict[str, object]:
    metadata_path = path.with_suffix(".metadata.json")
    if not metadata_path.is_file():
        return {}
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CLIRejected(f"fixture metadata is invalid for {path.name}") from error
    if not isinstance(value, dict):
        raise CLIRejected(f"fixture metadata must be an object for {path.name}")
    return cast(dict[str, object], value)


if __name__ == "__main__":
    raise SystemExit(main())
