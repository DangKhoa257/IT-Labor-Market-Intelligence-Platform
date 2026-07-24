"""Offline Phase 2 regression coverage; all input values are SYNTHETIC_TEST_DATA."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from it_labor_market_intelligence.analytics import analyze_records
from it_labor_market_intelligence.cli.offline_pipeline import enrich_record, run_pipeline
from it_labor_market_intelligence.data_io import (
    JsonlParseError,
    iter_jsonl,
    read_jsonl,
    write_jsonl,
)
from it_labor_market_intelligence.deduplication import deduplicate_records
from it_labor_market_intelligence.processing.companies import normalize_company
from it_labor_market_intelligence.processing.employment import normalize_employment_type
from it_labor_market_intelligence.processing.locations import normalize_location
from it_labor_market_intelligence.processing.text import comparison_key, normalize_whitespace
from it_labor_market_intelligence.processing.work_modes import normalize_work_mode
from it_labor_market_intelligence.quality import validate_record


def _record(identifier: str, **raw_changes: object) -> dict:
    raw = {
        "source": "synthetic",
        "source_job_id": identifier,
        "source_url": f"https://example.test/jobs/{identifier}",
        "title_raw": "Backend Engineer",
        "company_name_raw": "Example Technology JSC",
        "location_raw": "H\u00e0 N\u1ed9i",
        "closed_state": "ACTIVE",
        "collected_at": "2026-01-01T00:00:00+00:00",
        "content_hash": f"hash-{identifier}",
    }
    raw.update(raw_changes)
    return {
        "raw": raw,
        "normalized": {
            "title_normalized": "Backend Engineer",
            "primary_category": "Software Engineering",
            "salary": {
                "minimum": 100,
                "maximum": 200,
                "currency": "USD",
                "period": "MONTH",
                "disclosed": True,
                "confidence": 1.0,
            },
            "experience": {"minimum_years": None, "maximum_years": None, "confidence": 0.0},
            "skills": [{"canonical_name": "Python"}],
        },
    }


def test_jsonl_streaming_unicode_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('\n{"title":"K\u1ef9 s\u01b0"}\n\n', encoding="utf-8")
    assert read_jsonl(path) == [{"title": "K\u1ef9 s\u01b0"}]


def test_jsonl_rejects_non_object_with_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(JsonlParseError, match=r":1:"):
        list(iter_jsonl(path))


def test_jsonl_deterministic_roundtrip_and_append(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    write_jsonl(path, [{"z": 1, "a": 2}])
    assert path.read_text(encoding="utf-8") == '{"a":2,"z":1}\n'


def test_text_normalization_is_accent_insensitive_without_losing_display() -> None:
    assert normalize_whitespace("  C\u00d4NG\tTY  ") == "C\u00d4NG TY"
    assert comparison_key("C\u00f4ng ty \u0110\u1ea1i Ph\u00e1t") == "cong ty dai phat"


def test_company_location_and_employment_normalization() -> None:
    assert normalize_company("Example Tech JSC")["company_name_normalized"] == "Example Technology"
    location = normalize_location("Remote - H\u00e0 N\u1ed9i, Q.1")
    assert location["normalized_locations"] == ("Hanoi",)
    assert location["district"] == "District 1"
    assert not location["is_remote_only"]
    assert normalize_employment_type("OTHER")["employment_type"] == "UNSPECIFIED"
    assert (
        normalize_employment_type(None, "Th\u1ef1c t\u1eadp sinh")["employment_type"]
        == "INTERNSHIP"
    )


def test_work_mode_false_positives_are_not_remote_work() -> None:
    assert normalize_work_mode(None, "Support remote users")["work_mode"] == "UNSPECIFIED"
    assert normalize_work_mode(None, "Work from home two days")["work_mode"] == "REMOTE"
    assert normalize_work_mode(None, "L\u00e0m vi\u1ec7c t\u1eeb xa")["work_mode"] == "REMOTE"


def test_validator_handles_naive_and_aware_dates() -> None:
    record = _record("1", posted_at_raw="2026-01-01", collected_at="2026-01-01T00:00:00+00:00")
    assert not any(item["code"] == "posted_after_collected" for item in validate_record(record))


def test_validator_rejects_missing_identity_and_bad_salary() -> None:
    record = _record("", source_url="bad", title_raw="", source_job_id="")
    record["normalized"]["salary"] = {
        "minimum": 200,
        "maximum": 100,
        "currency": "USD",
        "period": "MONTH",
        "disclosed": True,
    }
    codes = {item["code"] for item in validate_record(record)}
    assert {"required_missing", "url_malformed", "salary_range_invalid"} <= codes


def test_exact_duplicate_clusters_merge_overlapping_signals() -> None:
    first = _record("1", content_hash="shared")
    second = _record("1", source_url="https://example.test/jobs/changed", content_hash="other")
    third = _record("3", content_hash="shared")
    result = deduplicate_records([first, second, third])
    exact = [
        cluster for cluster in result["clusters"] if cluster["classification"] == "EXACT_DUPLICATE"
    ]
    assert exact[0]["member_indices"] == [0, 1, 2]
    assert {member["source_job_id"] for member in exact[0]["members"]} == {"1", "3"}


def test_same_title_different_companies_is_distinct() -> None:
    left, right = (
        enrich_record(_record("1")),
        enrich_record(_record("2", company_name_raw="Another Company LLC")),
    )
    assert deduplicate_records([left, right])["cluster_count"] == 0


def test_analytics_pairs_are_counted_per_record() -> None:
    record = enrich_record(_record("1"))
    record["normalized"]["skills"] = [{"canonical_name": "Python"}, {"canonical_name": "SQL"}]
    report = analyze_records([record], "2026-01-01T00:00:00+00:00")
    assert report["skills"]["co_occurrence_pairs"] == [{"value": "Python | SQL", "count": 1}]


def test_pipeline_preserves_all_input_records_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "input.jsonl"
    write_jsonl(source, [_record("1"), _record("2", title_raw="")])
    paths = [
        tmp_path / name
        for name in ("ok.jsonl", "bad.jsonl", "quality.json", "analytics.json", "duplicates.json")
    ]
    summary = run_pipeline(source, *paths, generated_at="2026-01-01T00:00:00+00:00")
    assert summary["accepted"] + summary["rejected"] == 2
    assert len(read_jsonl(paths[0])) + len(read_jsonl(paths[1])) == 2
    assert json.loads(paths[2].read_text(encoding="utf-8"))["input_record_count"] == 2
