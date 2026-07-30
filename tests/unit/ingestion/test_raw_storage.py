from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from it_labor_market_intelligence.ingestion.raw_storage import (
    INLINE_JSON_MAX_BYTES,
    RawStorageDecision,
    fixture_raw_decision,
    inline_json_raw_decision,
    suppressed_raw_decision,
)

FETCHED_AT = datetime(2026, 7, 29, 5, 0, tzinfo=UTC)


def test_fixture_decision_hashes_exact_bytes_and_uses_relative_key() -> None:
    body = b"<html>\r\nfixture</html>"

    decision = fixture_raw_decision(
        body,
        r"tests\fixtures\topdev\job_active.html",
        FETCHED_AT,
        30,
        mime_type="text/html",
    )

    assert decision.sha256 == hashlib.sha256(body).hexdigest()
    assert decision.byte_size == len(body)
    assert decision.storage_provider == "filesystem"
    assert decision.object_key == "tests/fixtures/topdev/job_active.html"
    assert decision.inline_payload_json is None
    assert decision.expires_at == FETCHED_AT + timedelta(days=30)
    assert decision.should_persist is True


@pytest.mark.parametrize(
    "fixture_key",
    [
        "",
        "/tests/fixtures/job.html",
        r"C:\Users\person\job.html",
        "tests/../secret.html",
        "tests/fixtures/",
    ],
)
def test_fixture_decision_rejects_unsafe_or_non_file_keys(fixture_key: str) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        fixture_raw_decision(b"fixture", fixture_key, FETCHED_AT, 30)


def test_inline_json_decision_hashes_original_bytes_not_canonical_json() -> None:
    body = b'{ "records": [2, 1], "ok": true }\n'

    decision = inline_json_raw_decision(
        body,
        FETCHED_AT,
        None,
        allow_raw_storage=True,
    )

    assert decision.sha256 == hashlib.sha256(body).hexdigest()
    assert decision.storage_provider == "inline"
    assert decision.inline_payload_json == {"records": [2, 1], "ok": True}
    assert decision.object_key is None
    assert decision.expires_at is None
    assert decision.reason == "inline_json"


@pytest.mark.parametrize(
    ("body", "allow", "reason"),
    [
        (b"{}", False, "policy_disallowed"),
        (b"not-json", True, "not_structured_json"),
        (b'"scalar"', True, "not_structured_json"),
        (b" " * (INLINE_JSON_MAX_BYTES + 1), True, "payload_too_large"),
    ],
    ids=["policy-disallowed", "invalid-json", "scalar-json", "too-large"],
)
def test_inline_json_decision_records_suppression_reason(
    body: bytes, allow: bool, reason: str
) -> None:
    decision = inline_json_raw_decision(
        body,
        FETCHED_AT,
        0,
        allow_raw_storage=allow,
    )

    assert decision.storage_provider is None
    assert decision.should_persist is False
    assert decision.reason == reason
    assert decision.expires_at == FETCHED_AT


def test_live_suppression_keeps_hash_and_safe_reason_only() -> None:
    decision = suppressed_raw_decision(
        b"<html>live response</html>",
        FETCHED_AT,
        30,
        policy_allows_storage=True,
        mime_type="text/html",
    )

    assert decision.storage_provider is None
    assert decision.object_key is None
    assert decision.inline_payload_json is None
    assert decision.reason == "object_storage_unavailable"


def test_raw_storage_decision_enforces_database_storage_consistency() -> None:
    with pytest.raises(ValueError, match="requires an object key"):
        RawStorageDecision(
            sha256="a" * 64,
            byte_size=1,
            storage_provider="filesystem",
            object_key=None,
            expires_at=None,
        )


def test_raw_storage_rejects_naive_timestamp_and_negative_retention() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        fixture_raw_decision(b"x", "tests/fixtures/x", datetime(2026, 7, 29), 1)
    with pytest.raises(ValueError, match="must not be negative"):
        fixture_raw_decision(b"x", "tests/fixtures/x", FETCHED_AT, -1)
