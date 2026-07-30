from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest

from it_labor_market_intelligence.ingestion.adapters.topdev_registration import BootstrapResult
from it_labor_market_intelligence.ingestion.cli import (
    EXIT_ALL_TASKS_FAILED,
    EXIT_CONFIGURATION_REJECTED,
    EXIT_INTERNAL_FAILURE,
    EXIT_PARTIALLY_SUCCEEDED,
    EXIT_SUCCEEDED,
    RunPlan,
    RunRequest,
    main,
)
from it_labor_market_intelligence.ingestion.contracts import JsonValue
from it_labor_market_intelligence.ingestion.runner import (
    RunConfiguration,
    RunCounters,
    RunResult,
)

RUN_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("20000000-0000-0000-0000-000000000002")
POLICY_ID = UUID("20000000-0000-0000-0000-000000000003")
PARSER_ID = UUID("20000000-0000-0000-0000-000000000004")


@dataclass
class FakeCLIService:
    source_enabled: bool = True
    policy_approved: bool = True
    policy_maximum: int = 30
    run_status: str = "succeeded"
    failure: Exception | None = None
    plans: list[RunRequest] = field(default_factory=list)
    executed: list[RunPlan] = field(default_factory=list)
    retried: list[tuple[UUID, Path | None]] = field(default_factory=list)
    inspected: list[UUID] = field(default_factory=list)
    stale_ages: list[int] = field(default_factory=list)
    bootstraps: list[bool] = field(default_factory=list)

    def bootstrap_topdev(self, enable: bool) -> BootstrapResult:
        self.bootstraps.append(enable)
        return BootstrapResult(
            source_id=SOURCE_ID,
            source_enabled=enable,
            policy_created=True,
            parser_version="topdev.v1",
            configuration_hash="a" * 64,
            git_commit_sha="1234567",
        )

    def plan_run(self, request: RunRequest) -> RunPlan:
        self.plans.append(request)
        limit = request.limit if request.limit is not None else min(10, self.policy_maximum)
        run_type: Literal["test", "manual"] = "test" if request.trigger == "test" else "manual"
        trigger_type: Literal["test", "manual"] = "test" if request.trigger == "test" else "manual"
        return RunPlan(
            configuration=RunConfiguration(
                source_id=SOURCE_ID,
                source_slug=request.source,
                source_policy_id=POLICY_ID,
                parser_version_id=PARSER_ID,
                requested_limit=limit,
                discovery_url="https://topdev.vn/viec-lam/tim-kiem",
                mode=request.mode,
                run_type=run_type,
                trigger_type=trigger_type,
                fail_fast=request.fail_fast,
                parser_version="topdev.v1",
            ),
            source_enabled=self.source_enabled,
            policy_approved=self.policy_approved,
            policy_maximum=self.policy_maximum,
            fixture_dir=request.fixture_dir,
        )

    def execute_run(self, plan: RunPlan) -> RunResult:
        self.executed.append(plan)
        if self.failure is not None:
            raise self.failure
        return _result(self.run_status)

    def retry_run(self, run_id: UUID, fixture_dir: Path | None) -> RunResult:
        self.retried.append((run_id, fixture_dir))
        return _result(self.run_status)

    def inspect_run(self, run_id: UUID) -> dict[str, JsonValue]:
        self.inspected.append(run_id)
        return {
            "error_count": 1,
            "run_id": str(run_id),
            "source": "topdev",
            "status": "partially_succeeded",
        }

    def requeue_stale(self, older_than_seconds: int) -> int:
        self.stale_ages.append(older_than_seconds)
        return 2


def _result(status: str) -> RunResult:
    return RunResult(
        run_id=RUN_ID,
        status=status,  # type: ignore[arg-type]
        counters=RunCounters(fetch_success_count=1, accepted_count=1),
    )


def _invoke(arguments: list[str], service: FakeCLIService) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(arguments, service=service, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_bootstrap_invocation_is_disabled_unless_enable_is_explicit() -> None:
    service = FakeCLIService()

    disabled_code, disabled_output, _ = _invoke(["bootstrap-topdev"], service)
    enabled_code, enabled_output, _ = _invoke(["bootstrap-topdev", "--enable"], service)

    assert disabled_code == enabled_code == EXIT_SUCCEEDED
    assert service.bootstraps == [False, True]
    assert json.loads(disabled_output)["enabled"] is False
    assert json.loads(enabled_output)["enabled"] is True


def test_fixture_run_is_default_and_invokes_runner_service() -> None:
    service = FakeCLIService(source_enabled=False, policy_approved=False)

    code, output, errors = _invoke(["run", "--trigger", "test"], service)

    assert code == EXIT_SUCCEEDED
    assert errors == ""
    assert service.plans[0].mode == "fixture"
    assert service.executed[0].configuration.mode == "fixture"
    assert json.loads(output)["status"] == "succeeded"


def test_live_mode_rejected_without_enabled_source_and_approved_policy() -> None:
    service = FakeCLIService(source_enabled=False, policy_approved=False)

    code, output, errors = _invoke(["run", "--mode", "live"], service)

    assert code == EXIT_CONFIGURATION_REJECTED
    assert output == ""
    assert service.executed == []
    assert "enabled source and approved current policy" in errors


@pytest.mark.parametrize("limit", [0, 6])
def test_limit_validation_rejects_out_of_policy_values(limit: int) -> None:
    service = FakeCLIService(policy_maximum=5)

    code, _, _ = _invoke(["run", "--limit", str(limit)], service)

    assert code == EXIT_CONFIGURATION_REJECTED
    assert service.executed == []


def test_non_topdev_source_is_rejected_before_service_resolution() -> None:
    service = FakeCLIService()

    code, _, errors = _invoke(["run", "--source", "other"], service)

    assert code == EXIT_CONFIGURATION_REJECTED
    assert service.plans == []
    assert "source must be topdev" in errors


def test_dry_run_resolves_plan_but_performs_no_ingestion_write() -> None:
    service = FakeCLIService(source_enabled=False, policy_approved=False)

    code, output, _ = _invoke(["run", "--trigger", "test", "--dry-run"], service)

    assert code == EXIT_SUCCEEDED
    assert len(service.plans) == 1
    assert service.executed == []
    summary = json.loads(output)
    assert summary["dry_run"] is True
    assert summary["mode"] == "fixture"


def test_retry_run_invokes_existing_run_with_fixture_directory() -> None:
    service = FakeCLIService(run_status="partially_succeeded")

    code, output, _ = _invoke(
        ["retry-run", "--run-id", str(RUN_ID), "--fixture-dir", "tests/fixtures/topdev"],
        service,
    )

    assert code == EXIT_PARTIALLY_SUCCEEDED
    assert service.retried == [(RUN_ID, Path("tests/fixtures/topdev"))]
    assert json.loads(output)["run_id"] == str(RUN_ID)


def test_inspect_run_output_is_deterministic_and_safe() -> None:
    service = FakeCLIService()

    code, output, errors = _invoke(["inspect-run", "--run-id", str(RUN_ID)], service)

    assert code == EXIT_SUCCEEDED
    assert errors == ""
    assert output == (
        '{"error_count":1,"run_id":"20000000-0000-0000-0000-000000000001",'
        '"source":"topdev","status":"partially_succeeded"}\n'
    )


def test_requeue_stale_validates_age_and_invokes_recovery() -> None:
    service = FakeCLIService()

    code, output, _ = _invoke(["requeue-stale", "--older-than-seconds", "60"], service)
    rejected, _, _ = _invoke(["requeue-stale", "--older-than-seconds", "0"], service)

    assert code == EXIT_SUCCEEDED
    assert rejected == EXIT_CONFIGURATION_REJECTED
    assert service.stale_ages == [60]
    assert json.loads(output)["requeued_or_failed"] == 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("succeeded", EXIT_SUCCEEDED),
        ("partially_succeeded", EXIT_PARTIALLY_SUCCEEDED),
        ("running", EXIT_PARTIALLY_SUCCEEDED),
        ("failed", EXIT_ALL_TASKS_FAILED),
        ("cancelled", EXIT_INTERNAL_FAILURE),
    ],
)
def test_run_exit_codes_follow_specification(status: str, expected: int) -> None:
    service = FakeCLIService(run_status=status)

    code, _, _ = _invoke(["run"], service)

    assert code == expected


def test_unexpected_errors_are_secret_safe_and_never_print_raw_body() -> None:
    service = FakeCLIService(
        failure=RuntimeError(
            "postgresql://user:password@localhost/private "
            "authorization=Bearer-secret raw_body=<html>PRIVATE_BODY</html>"
        )
    )

    code, output, errors = _invoke(["run"], service)

    assert code == EXIT_INTERNAL_FAILURE
    assert output == ""
    assert "password" not in errors
    assert "Bearer-secret" not in errors
    assert "PRIVATE_BODY" not in errors
    assert "[redacted]" in errors
