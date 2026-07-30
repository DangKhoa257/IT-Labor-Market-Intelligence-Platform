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

from it_labor_market_intelligence.adapters.topdev import TOPDEV_IT_LISTING, extract_job_id

from .adapters.topdev_registration import (
    BootstrapResult,
    EnableRejected,
    PolicyState,
    SourceState,
    TopDevRegistration,
    discover_git_commit_sha,
    enable_topdev,
    register_topdev,
)
from .contracts import FixtureResponse, IngestionAdapter, JsonValue
from .runner import (
    FixtureTransport,
    IngestionRunner,
    PostgreSQLRunnerStore,
    RunConfiguration,
    RunResult,
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

    def disable_source(self, source_id: UUID, at: datetime) -> None:
        self._connection.execute(
            sa.text(
                """
                UPDATE ingestion.sources
                SET is_enabled=false, updated_at=:at
                WHERE id=:source_id
                """
            ),
            {"source_id": source_id, "at": at},
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
                    '[]'::jsonb, '[]'::jsonb, 2.000, 30, 1, 30, 90,
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
                SELECT id, maximum_requests_per_run, raw_retention_days,
                       allow_raw_storage, allow_description_storage
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
            maximum_requests_per_run=int(row[1]),
            raw_retention_days=cast(int | None, row[2]),
            allow_raw_storage=bool(row[3]),
            allow_description_storage=bool(row[4]),
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
        self._connection.execute(
            sa.text(
                """
                UPDATE ingestion.parser_versions
                SET is_active=false,
                    retired_at=COALESCE(retired_at, GREATEST(:at, created_at))
                WHERE source_id=:source_id AND parser_name=:parser_name
                  AND is_active AND version!=:version
                """
            ),
            {
                "source_id": source_id,
                "parser_name": registration.parser_name,
                "version": registration.parser_version,
                "at": at,
            },
        )
        self._connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.parser_versions (
                    source_id, parser_name, version, schema_version,
                    git_commit_sha, configuration_hash, is_active
                ) VALUES (
                    :source_id, :parser_name, :version, :schema_version,
                    :git_sha, :configuration_hash, true
                )
                ON CONFLICT (source_id, parser_name, version) DO UPDATE SET
                    schema_version=EXCLUDED.schema_version,
                    git_commit_sha=EXCLUDED.git_commit_sha,
                    configuration_hash=EXCLUDED.configuration_hash,
                    is_active=true,
                    retired_at=NULL
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
    ) -> None:
        self._engine = engine
        self._now = now or (lambda: datetime.now(UTC))
        self._git_commit_sha = git_commit_sha

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
            row = connection.execute(
                sa.text(
                    """
                    SELECT source.id, source.is_enabled,
                           policy.id, policy.robots_review_status,
                           policy.terms_review_status,
                           policy.maximum_requests_per_run,
                           policy.raw_retention_days,
                           policy.allow_raw_storage,
                           policy.allow_description_storage,
                           parser.id, parser.version, parser.schema_version
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
            ).first()
        if row is None:
            raise CLIRejected("TopDev source, current policy, or active parser is not configured")

        policy_maximum = min(30, int(row[5]))
        limit = min(10, policy_maximum) if request.limit is None else request.limit
        if not 1 <= limit <= policy_maximum:
            raise CLIRejected(f"limit must be between 1 and {policy_maximum}")
        policy_approved = row[3] == "approved" and row[4] == "approved"
        run_type, trigger_type = _trigger_types(request.trigger)
        configuration = RunConfiguration(
            source_id=cast(UUID, row[0]),
            source_slug="topdev",
            source_policy_id=cast(UUID, row[2]),
            parser_version_id=cast(UUID, row[9]),
            requested_limit=limit,
            discovery_url=TOPDEV_IT_LISTING,
            mode=request.mode,
            run_type=run_type,
            trigger_type=trigger_type,
            raw_retention_days=cast(int | None, row[6]),
            allow_raw_storage=bool(row[7]),
            allow_description_storage=bool(row[8]),
            fail_fast=request.fail_fast,
            git_commit_sha=self._git_commit_sha or discover_git_commit_sha(),
            parser_version=str(row[10]),
            record_schema_version=str(row[11]),
        )
        return RunPlan(
            configuration=configuration,
            source_enabled=bool(row[1]),
            policy_approved=policy_approved,
            policy_maximum=policy_maximum,
            fixture_dir=request.fixture_dir,
        )

    def execute_run(self, plan: RunPlan) -> RunResult:
        runner = self._runner_for_plan(plan)
        return runner.run()

    def retry_run(self, run_id: UUID, fixture_dir: Path | None) -> RunResult:
        with self._engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    """
                    SELECT run.source_id, source.slug, run.source_policy_id,
                           run.parser_version_id, run.requested_limit,
                           run.configuration_json, run.run_type, run.trigger_type,
                           run.git_commit_sha, run.status,
                           policy.raw_retention_days, policy.allow_raw_storage,
                           policy.allow_description_storage,
                           parser.version, parser.schema_version,
                           source.is_enabled,
                           policy.robots_review_status, policy.terms_review_status,
                           policy.maximum_requests_per_run
                    FROM ingestion.crawl_runs AS run
                    JOIN ingestion.sources AS source ON source.id=run.source_id
                    JOIN ingestion.source_policies AS policy ON policy.id=run.source_policy_id
                    JOIN ingestion.parser_versions AS parser ON parser.id=run.parser_version_id
                    WHERE run.id=:run_id
                    """
                ),
                {"run_id": run_id},
            ).first()
        if row is None:
            raise CLIRejected("crawl run was not found")
        if row[9] != "running":
            raise CLIRejected("only a running crawl run can be retried")
        configuration_json = cast(Mapping[str, object], row[5])
        mode: Literal["fixture", "live"] = (
            "live" if configuration_json.get("mode") == "live" else "fixture"
        )
        configuration = RunConfiguration(
            source_id=cast(UUID, row[0]),
            source_slug=str(row[1]),
            source_policy_id=cast(UUID, row[2]),
            parser_version_id=cast(UUID, row[3]),
            requested_limit=int(row[4]),
            discovery_url=TOPDEV_IT_LISTING,
            mode=mode,
            run_type=cast(Any, row[6]),
            trigger_type=cast(Any, row[7]),
            raw_retention_days=cast(int | None, row[10]),
            allow_raw_storage=bool(row[11]),
            allow_description_storage=bool(row[12]),
            fail_fast=bool(configuration_json.get("fail_fast", False)),
            git_commit_sha=cast(str | None, row[8]),
            parser_version=str(row[13]),
            record_schema_version=str(row[14]),
        )
        plan = RunPlan(
            configuration=configuration,
            source_enabled=bool(row[15]),
            policy_approved=row[16] == "approved" and row[17] == "approved",
            policy_maximum=int(row[18]),
            fixture_dir=fixture_dir,
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
        observer: FixtureTransport | None = None
        if plan.configuration.mode == "fixture":
            fixture_dir = plan.fixture_dir or Path("tests/fixtures/topdev")
            observer = _fixture_transport(fixture_dir, self._aware_now())
            adapter = registration.adapter(observer)
        else:
            adapter = registration.adapter()
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
        return
    if configuration.trigger_type != "test" and (
        not plan.source_enabled or not plan.policy_approved
    ):
        raise CLIRejected("fixture mode with a disabled or unapproved source requires trigger=test")


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
