"""Foundation tests for documentation and canonical schema contracts."""

from __future__ import annotations

import csv
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "AGENT_RULES.md",
    REPOSITORY_ROOT / "docs" / "PRODUCT_SPEC.md",
    REPOSITORY_ROOT / "docs" / "DATA_SCHEMA.md",
    REPOSITORY_ROOT / "docs" / "JOB_TAXONOMY.md",
    REPOSITORY_ROOT / "docs" / "SKILL_TAXONOMY.md",
    REPOSITORY_ROOT / "docs" / "ARCHITECTURE.md",
    REPOSITORY_ROOT / "docs" / "BENCHMARK_PLAN.md",
    REPOSITORY_ROOT / "docs" / "DATABASE_V1_HISTORY_QUALITY.md",
    REPOSITORY_ROOT / "docs" / "DATABASE_V1_ANALYTICS.md",
    REPOSITORY_ROOT / "datasets" / "gold" / "ANNOTATION_GUIDELINES.md",
)
GOLD_TEMPLATE = REPOSITORY_ROOT / "datasets" / "gold" / "job_postings_gold_template.csv"
EXPECTED_FIELDS = (
    "source",
    "source_job_id",
    "source_url",
    "title_raw",
    "title_normalized",
    "job_category",
    "company_name",
    "company_industry",
    "company_size",
    "location_raw",
    "city",
    "work_mode",
    "employment_type",
    "seniority",
    "experience_min_years",
    "experience_max_years",
    "salary_raw",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_type",
    "salary_disclosed",
    "skills_raw",
    "skills_normalized",
    "education_level",
    "language_requirements",
    "description_raw",
    "posted_at",
    "expires_at",
    "first_seen_at",
    "last_seen_at",
    "collected_at",
    "is_active",
    "content_hash",
    "extractor_version",
    "confidence_score",
)


def test_pytest_environment_is_working() -> None:
    """Provide the requested minimal smoke test."""
    assert True


def test_required_documents_are_not_empty() -> None:
    empty_documents = [path for path in DOCUMENTS if not path.read_text(encoding="utf-8").strip()]
    assert not empty_documents, f"Empty documents: {empty_documents}"


def test_gold_template_header_matches_documented_canonical_schema() -> None:
    schema_text = (REPOSITORY_ROOT / "docs" / "DATA_SCHEMA.md").read_text(encoding="utf-8")
    documented_fields = tuple(re.findall(r"^\| `([a-z][a-z0-9_]*)` \|", schema_text, re.MULTILINE))

    with GOLD_TEMPLATE.open(encoding="utf-8", newline="") as csv_file:
        csv_fields = tuple(next(csv.reader(csv_file)))

    assert documented_fields == EXPECTED_FIELDS
    assert csv_fields == EXPECTED_FIELDS


def test_gold_template_contains_only_marked_examples() -> None:
    with GOLD_TEMPLATE.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    assert len(rows) <= 3
    assert all(None not in row for row in rows), "A row has more values than the canonical header"
    assert all(row["source"] == "EXAMPLE_NOT_REAL_DATA" for row in rows)
    assert all("EXAMPLE_NOT_REAL_DATA" in row["description_raw"] for row in rows)


def test_migration_003_canonical_contract_is_synchronized() -> None:
    schema_text = (REPOSITORY_ROOT / "docs" / "DATA_SCHEMA.md").read_text(encoding="utf-8")
    core_text = (REPOSITORY_ROOT / "docs" / "DATABASE_V1_CORE.md").read_text(encoding="utf-8")
    assert "Database V1 Migration 005 compatibility" in schema_text
    for table in (
        "core.job_postings",
        "core.job_posting_locations",
        "core.salary_offers",
        "core.job_posting_skills",
        "core.job_posting_occupations",
    ):
        assert table in schema_text or table in core_text


def test_migration_004_history_quality_contract_is_synchronized() -> None:
    schema_text = (REPOSITORY_ROOT / "docs" / "DATA_SCHEMA.md").read_text(encoding="utf-8")
    history_text = (REPOSITORY_ROOT / "docs" / "DATABASE_V1_HISTORY_QUALITY.md").read_text(
        encoding="utf-8"
    )
    assert "Migration 005 compatibility" in schema_text
    for table in (
        "history.job_observations",
        "history.job_change_events",
        "quality.data_quality_issues",
        "quality.field_evidence",
        "quality.duplicate_clusters",
    ):
        assert table in schema_text or table in history_text


def test_migration_005_analytics_contract_is_synchronized() -> None:
    schema_text = (REPOSITORY_ROOT / "docs" / "DATA_SCHEMA.md").read_text(encoding="utf-8")
    analytics_text = (REPOSITORY_ROOT / "docs" / "DATABASE_V1_ANALYTICS.md").read_text(
        encoding="utf-8"
    )
    assert "Migration 005 compatibility" in schema_text
    for table in (
        "refresh_runs",
        "dim_dates",
        "fact_job_observations",
        "bridge_job_observation_skills",
        "daily_market_metrics",
        "daily_salary_metrics",
    ):
        assert table in analytics_text
