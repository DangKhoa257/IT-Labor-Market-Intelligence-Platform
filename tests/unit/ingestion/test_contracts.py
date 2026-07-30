from __future__ import annotations

from datetime import UTC, datetime

import pytest

from it_labor_market_intelligence.ingestion.contracts import FixtureResponse


def test_fixture_response_converts_without_changing_exact_body() -> None:
    fetched_at = datetime(2026, 7, 29, 4, 30, tzinfo=UTC)
    body = b"\x00fixture\xff"
    response = FixtureResponse(
        url="https://topdev.vn/viec-lam/example-123",
        status=200,
        body=body,
        fetched_at=fetched_at,
        content_type="text/html; charset=utf-8",
        headers={"ETag": '"fixture"'},
    )

    result = response.as_fetch_result()

    assert result.url == response.url
    assert result.status == 200
    assert result.body is body
    assert result.fetched_at is fetched_at
    assert result.content_type == "text/html; charset=utf-8"


@pytest.mark.parametrize("status", [0, 99, 600])
def test_fixture_response_rejects_invalid_http_status(status: int) -> None:
    with pytest.raises(ValueError, match="status"):
        FixtureResponse(
            url="https://topdev.vn/viec-lam/example-123",
            status=status,
            body=b"",
            fetched_at=datetime.now(UTC),
        )


def test_fixture_response_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixtureResponse(
            url="https://topdev.vn/viec-lam/example-123",
            status=200,
            body=b"",
            fetched_at=datetime(2026, 7, 29),
        )
