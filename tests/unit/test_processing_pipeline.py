"""End-to-end source-independent processing and provenance tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from it_labor_market_intelligence.domain import FieldProvenance, RawJobRecord
from it_labor_market_intelligence.processing import normalize_job_record

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "processing" / "synthetic_jobs.json"


def test_synthetic_fixture_is_prominently_marked() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["data_classification"] == "SYNTHETIC_TEST_DATA"
    assert "EXAMPLE_NOT_REAL_DATA" in payload["warning"]
    assert all(record["source"] == "SYNTHETIC_TEST_DATA" for record in payload["records"])
    assert all("SYNTHETIC_TEST_DATA" in record["description_raw"] for record in payload["records"])


def test_every_derived_pipeline_field_has_complete_provenance() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"][0]
    raw = RawJobRecord(**payload, collected_at=datetime(2026, 1, 1, tzinfo=UTC))
    normalized = normalize_job_record(raw)
    expected_fields = {
        "title_normalized",
        "primary_category",
        "secondary_categories",
        "salary.minimum",
        "salary.maximum",
        "salary.currency",
        "salary.period",
        "salary.salary_type",
        "salary.disclosed",
        "experience.minimum_years",
        "experience.maximum_years",
        "experience.minimum_inclusive",
        "experience.maximum_inclusive",
        "skills",
    }
    assert set(normalized.field_provenance) == expected_fields
    for provenance in normalized.field_provenance.values():
        assert provenance.source_field
        assert provenance.method
        assert provenance.rule_version
        assert 0.0 <= provenance.confidence <= 1.0
        assert provenance.evidence_text is not None or provenance.evidence_key is not None
    assert normalized.source_url == payload["source_url"]


def test_nulls_and_negotiable_values_survive_pipeline() -> None:
    raw = RawJobRecord(
        source="SYNTHETIC_TEST_DATA",
        source_job_id="null-case",
        source_url="https://invalid.example/jobs/null-case",
        title_raw="Unknown Role",
        description_raw="SYNTHETIC_TEST_DATA / EXAMPLE_NOT_REAL_DATA",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        salary_raw="Thỏa thuận",
        experience_raw=None,
        skills_raw=None,
    )
    result = normalize_job_record(raw)
    assert result.salary.disclosed is False
    assert result.salary.minimum is None and result.salary.maximum is None
    assert result.experience.minimum_years is None
    assert result.primary_category == "Unclassified"


def test_provenance_rejects_missing_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        FieldProvenance("salary_raw", "regex", "v1", 0.5)


def test_raw_record_requires_timezone_aware_collection_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RawJobRecord(
            source="SYNTHETIC_TEST_DATA",
            source_job_id="bad-time",
            source_url="https://invalid.example/jobs/bad-time",
            title_raw="Backend Engineer",
            description_raw="SYNTHETIC_TEST_DATA / EXAMPLE_NOT_REAL_DATA",
            collected_at=datetime(2026, 1, 1),
        )
