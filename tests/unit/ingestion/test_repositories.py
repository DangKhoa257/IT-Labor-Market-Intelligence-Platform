from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import sqlalchemy as sa

from it_labor_market_intelligence.ingestion.raw_storage import (
    fixture_raw_decision,
    suppressed_raw_decision,
)
from it_labor_market_intelligence.ingestion.repositories import (
    claim_due_task,
    upsert_raw_object,
    upsert_raw_storage_decision,
)


def _connection_with_result(result: MagicMock) -> tuple[sa.Connection, MagicMock]:
    connection_mock = MagicMock(spec=sa.Connection)
    connection_mock.execute.return_value = result
    return cast(sa.Connection, connection_mock), connection_mock


def test_claim_due_task_uses_one_atomic_skip_locked_statement() -> None:
    claimed_row = cast(sa.Row[Any], object())
    result = MagicMock()
    result.first.return_value = claimed_row
    connection, connection_mock = _connection_with_result(result)
    run_id = UUID("00000000-0000-0000-0000-000000000123")

    assert claim_due_task(connection, run_id) is claimed_row

    statement, parameters = connection_mock.execute.call_args.args
    sql = str(statement)
    assert "FOR UPDATE OF task SKIP LOCKED" in sql
    assert "task.attempt_count < task.max_attempts" in sql
    assert "run.status = 'running'" in sql
    assert "attempt_count = task.attempt_count + 1" in sql
    assert parameters == {"run_id": run_id}
    connection_mock.commit.assert_not_called()


def test_upsert_raw_object_is_atomic_and_does_not_overwrite_first_location() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = 42
    connection, connection_mock = _connection_with_result(result)
    expires_at = datetime(2026, 8, 28, tzinfo=UTC)

    raw_object_id = upsert_raw_object(
        connection,
        "a" * 64,
        123,
        "tests/fixtures/topdev/job.html",
        expires_at,
        mime_type="text/html",
    )

    assert raw_object_id == 42
    statement, parameters = connection_mock.execute.call_args.args
    sql = str(statement)
    assert "ON CONFLICT (sha256) DO UPDATE" in sql
    assert "WHERE ingestion.raw_objects.byte_size = EXCLUDED.byte_size" in sql
    assert parameters["storage_provider"] == "filesystem"
    assert parameters["object_key"] == "tests/fixtures/topdev/job.html"
    assert parameters["expires_at"] is expires_at
    connection_mock.commit.assert_not_called()


def test_upsert_raw_object_rejects_hash_size_mismatch_reported_by_database() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    connection, _ = _connection_with_result(result)

    with pytest.raises(ValueError, match="different byte size"):
        upsert_raw_object(connection, "b" * 64, 10, "fixture.html", None)


@pytest.mark.parametrize("sha256", ["A" * 64, "a" * 63, "not-a-hash"])
def test_upsert_raw_object_rejects_noncanonical_hash(sha256: str) -> None:
    connection = cast(sa.Connection, MagicMock(spec=sa.Connection))

    with pytest.raises(ValueError, match="lowercase hexadecimal"):
        upsert_raw_object(connection, sha256, 1, "fixture.html", None)


def test_upsert_raw_storage_decision_maps_all_metadata() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = 7
    connection, connection_mock = _connection_with_result(result)
    fetched_at = datetime(2026, 7, 29, tzinfo=UTC)
    decision = fixture_raw_decision(
        b"fixture",
        "tests/fixtures/topdev/job.html",
        fetched_at,
        30,
        mime_type="text/html",
    )

    assert upsert_raw_storage_decision(connection, decision) == 7

    parameters = connection_mock.execute.call_args.args[1]
    assert parameters["sha256"] == decision.sha256
    assert parameters["byte_size"] == decision.byte_size
    assert parameters["mime_type"] == "text/html"


def test_upsert_raw_storage_decision_skips_suppressed_evidence() -> None:
    connection = cast(sa.Connection, MagicMock(spec=sa.Connection))
    decision = suppressed_raw_decision(
        b"live",
        datetime(2026, 7, 29, tzinfo=UTC),
        30,
        policy_allows_storage=False,
    )

    assert upsert_raw_storage_decision(connection, decision) is None
    cast(MagicMock, connection).execute.assert_not_called()
