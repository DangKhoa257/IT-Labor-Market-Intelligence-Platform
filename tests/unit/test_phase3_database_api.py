"""Phase 3 integration tests using only SYNTHETIC_TEST_DATA and SQLite."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.main import create_app
from it_labor_market_intelligence.data_io import JsonlParseError, write_jsonl
from it_labor_market_intelligence.database.models import Base, Company, JobPosting, Skill, Source
from it_labor_market_intelligence.database.repositories import JobRepository
from it_labor_market_intelligence.database.services import DatasetImporter


def _payload(identifier: str, *, company: str = "Example Tech", currency: str = "USD") -> dict:
    return {
        "raw": {
            "source": "synthetic",
            "source_job_id": identifier,
            "source_url": f"https://example.test/jobs/{identifier}",
            "title_raw": "Backend Engineer",
            "company_name_raw": company,
            "location_raw": "Hanoi",
            "salary_raw": "1000-2000 USD/month",
            "posted_at_raw": "2026-01-01",
            "expires_at_raw": "2026-12-31",
            "collected_at": "2026-02-01T00:00:00Z",
            "closed_state": "ACTIVE",
            "content_hash": f"hash-{identifier}",
            "description_raw": "<b>Build APIs</b>",
        },
        "normalized": {
            "title_normalized": "Backend Engineer",
            "primary_category": "Software Engineering",
            "secondary_categories": [],
            "salary": {
                "minimum": "1000",
                "maximum": "2000",
                "currency": currency,
                "period": "MONTH",
                "salary_type": "gross",
                "disclosed": True,
            },
            "experience": {"minimum_years": "1", "maximum_years": "3"},
            "skills": [{"canonical_name": "Python", "category": "Language", "confidence": 1.0}],
            "field_provenance": {"salary.minimum": {"method": "synthetic"}},
            "validation_issues": [],
        },
        "enrichment": {
            "company": {
                "company_name_normalized": company,
                "company_comparison_key": company.casefold().replace(" ", "-"),
            },
            "location": {"city": "Hanoi", "province": "Hanoi", "country": "Vietnam"},
            "work_mode": {"work_mode": "HYBRID"},
            "employment": {"employment_type": "FULL_TIME"},
        },
        "quality_issues": [],
    }


@pytest.fixture
def database(tmp_path: Path) -> tuple[str, Session]:
    url = f"sqlite:///{tmp_path / 'phase3.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield url, session
    session.close()


def test_model_source_identity_constraint(database: tuple[str, Session]) -> None:
    _, session = database
    source = Source(name="synthetic")
    session.add(source)
    session.flush()
    values = {
        "source_id": source.id,
        "source_job_id": "1",
        "source_url": "https://example.test/1",
        "title_raw": "Engineer",
        "collected_at": datetime(2026, 1, 1, tzinfo=UTC),
        "status": "ACTIVE",
    }
    session.add_all([JobPosting(**values), JobPosting(**values)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_import_is_idempotent_and_deduplicates_dimensions(
    database: tuple[str, Session], tmp_path: Path
) -> None:
    _, session = database
    path = tmp_path / "jobs.jsonl"
    write_jsonl(path, [_payload("1"), _payload("2")])
    importer = DatasetImporter(session)
    assert importer.import_path(path)["inserted"] == 2
    assert importer.import_path(path)["skipped"] == 2
    assert session.scalar(select(func.count(Company.id))) == 1
    assert session.scalar(select(func.count(Skill.id))) == 1


def test_import_update_replaces_existing_values(
    database: tuple[str, Session], tmp_path: Path
) -> None:
    _, session = database
    path = tmp_path / "jobs.jsonl"
    write_jsonl(path, [_payload("1")])
    importer = DatasetImporter(session)
    importer.import_path(path)
    changed = _payload("1")
    changed["raw"]["title_raw"] = "Senior Backend Engineer"
    write_jsonl(path, [changed])
    result = importer.import_path(path, replace_existing=True)
    assert result["updated"] == 1
    assert session.scalar(select(JobPosting.title_raw)) == "Senior Backend Engineer"


def test_import_malformed_json_rolls_back(database: tuple[str, Session], tmp_path: Path) -> None:
    _, session = database
    path = tmp_path / "bad.jsonl"
    path.write_text('{"raw":{"source":"synthetic"}}\nnot-json\n', encoding="utf-8")
    with pytest.raises(JsonlParseError):
        DatasetImporter(session).import_path(path)
    assert session.scalar(select(func.count(JobPosting.id))) == 0


def test_repository_filters_and_pagination(database: tuple[str, Session], tmp_path: Path) -> None:
    _, session = database
    path = tmp_path / "jobs.jsonl"
    write_jsonl(path, [_payload("1"), _payload("2", company="Other Tech")])
    DatasetImporter(session).import_path(path)
    items, total = JobRepository(session).list(page=1, page_size=1, city="Hanoi", skill="Python")
    assert total == 2
    assert len(items) == 1


@pytest.fixture
def client(database: tuple[str, Session], tmp_path: Path) -> TestClient:
    url, session = database
    path = tmp_path / "jobs.jsonl"
    write_jsonl(path, [_payload("1", currency="USD"), _payload("2", currency="VND")])
    DatasetImporter(session).import_path(path)
    return TestClient(create_app(url))


def test_health_jobs_detail_and_404(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    listing = client.get("/api/v1/jobs?page_size=1").json()
    assert listing["total"] == 2 and len(listing["items"]) == 1
    detail = client.get(f"/api/v1/jobs/{listing['items'][0]['id']}").json()
    assert detail["description_preview"] == "Build APIs"
    assert detail["skills"] == ["Python"]
    assert client.get("/api/v1/jobs/9999").status_code == 404
    companies = client.get("/api/v1/companies").json()
    company = client.get(f"/api/v1/companies/{companies[0]['id']}")
    assert company.status_code == 200
    assert company.json()["top_skills"][0]["value"] == "Python"
    assert client.get("/api/v1/companies/9999").status_code == 404


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/companies",
        "/api/v1/skills",
        "/api/v1/analytics/overview",
        "/api/v1/analytics/categories",
        "/api/v1/analytics/skills",
        "/api/v1/analytics/locations",
        "/api/v1/quality/summary",
        "/api/v1/duplicates",
    ],
)
def test_read_only_endpoints(client: TestClient, endpoint: str) -> None:
    assert client.get(endpoint).status_code == 200


def test_salary_analytics_separates_currencies(client: TestClient) -> None:
    data = client.get("/api/v1/analytics/salaries").json()["data"]["by_currency"]
    assert [row["currency"] for row in data] == ["USD", "VND"]
    assert all("median" in row for row in data)


def test_query_validation(client: TestClient) -> None:
    assert client.get("/api/v1/jobs?page=0").status_code == 422
    assert client.get("/api/v1/jobs?sort=unknown").status_code == 422
