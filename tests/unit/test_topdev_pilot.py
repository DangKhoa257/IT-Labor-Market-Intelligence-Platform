"""Bounded pilot runner tests with synthetic in-memory HTTP responses."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from it_labor_market_intelligence.adapters import FetchResult, TopDevAdapter
from it_labor_market_intelligence.adapters.topdev import TOPDEV_IT_LISTING
from it_labor_market_intelligence.adapters.topdev_pilot import (
    _invalid_url_classification,
    is_it_scope,
    run_pilot,
)

FETCHED_AT = datetime(2026, 7, 24, tzinfo=UTC)


def _posting(job_id: int) -> bytes:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": f"Backend Engineer {job_id}",
        "description": (
            "SYNTHETIC_TEST_DATA / EXAMPLE_NOT_REAL_DATA. Required skills: Python and PostgreSQL."
        ),
        "datePosted": "2026-07-20",
        "validThrough": "2026-08-20",
        "skills": "Python, PostgreSQL",
        "employmentType": "OTHER",
        "industry": "Information Technology",
        "experienceRequirements": {"monthsOfExperience": 24},
        "hiringOrganization": {"name": "SYNTHETIC_TEST_DATA"},
        "identifier": {"value": f"company-{job_id}"},
        "baseSalary": {"currency": "USD", "unitText": "MONTH", "value": "1000-2000 USD"},
    }
    return ('<script type="application/ld+json">' + json.dumps(payload) + "</script>").encode()


class SyntheticTransport:
    def __init__(self, job_count: int) -> None:
        self.job_urls = [
            f"https://topdev.vn/viec-lam/synthetic-backend-{1000 + index}"
            for index in range(job_count)
        ]

    def __call__(self, url: str) -> FetchResult:
        if url.startswith(TOPDEV_IT_LISTING):
            page_number = 2 if "page=2" in url else 1
            start = (page_number - 1) * 15
            page_jobs = self.job_urls[start : start + 15]
            duplicated = [page_jobs[0], *page_jobs] if page_jobs else []
            body = (
                "<main>"
                + "".join(f'<a href="{job_url}">Job</a>' for job_url in duplicated)
                + "</main>"
            ).encode()
        else:
            job_id = int(url.rsplit("-", maxsplit=1)[1])
            body = _posting(job_id)
        return FetchResult(url, 200, body, FETCHED_AT, "text/html")


def test_pilot_limit_is_enforced_and_outputs_quality_report(tmp_path: Path) -> None:
    output = tmp_path / "topdev_pilot.jsonl"
    report_path = tmp_path / "quality.json"
    report = run_pilot(
        TopDevAdapter(SyntheticTransport(35)),
        limit=30,
        output_path=output,
        report_path=report_path,
        diagnostic_path=tmp_path / "diagnostic.json",
    )
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 30
    assert report["urls_discovered"] == 30
    assert report["pages_fetched"] == 30
    assert report["successful_records"] == 30
    assert report["it_records_accepted"] == 30
    assert report["real_non_it_records_rejected"] == 0
    assert report["it_records_incorrectly_rejected"] == 0
    assert report["invalid_page_types"] == 0
    assert report["duplicate_records"] == 0
    assert report["salary_parsing_success"]["rate"] == 1.0
    assert report["experience_parsing_success"]["rate"] == 1.0
    assert report["skill_extraction_coverage"]["rate"] == 1.0
    assert report["active_job_count"] == 30
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_non_it_record_is_out_of_pilot_scope() -> None:
    transport = SyntheticTransport(1)
    adapter = TopDevAdapter(transport)
    raw = adapter.extract_raw_record(adapter.fetch_job_detail(transport.job_urls[0]))
    non_it_raw = replace(
        raw,
        title_raw="Sales Executive",
        source_category_raw="Sales",
        skills_raw=("Sales",),
    )
    assert is_it_scope(non_it_raw, adapter.normalize_record(non_it_raw)) is False
    ai_raw = replace(
        raw,
        title_raw="AI Solution Analyst",
        source_category_raw="Information Technology",
        skills_raw=None,
    )
    assert is_it_scope(ai_raw, adapter.normalize_record(ai_raw)) is True
    misleading_global_raw = replace(ai_raw, discovery_method="global_job_sitemap_pages_1_2")
    assert (
        is_it_scope(misleading_global_raw, adapter.normalize_record(misleading_global_raw)) is False
    )


@pytest.mark.parametrize(
    "title",
    [
        "Data Analyst",
        "Business Analyst IT",
        "Product Owner",
        "Technical Project Manager",
        "ERP Consultant",
        "System Administrator",
        "IT Support",
        "QA/QC",
        "Embedded Engineer",
    ],
)
def test_ambiguous_it_titles_use_source_category_not_title_only(title: str) -> None:
    transport = SyntheticTransport(1)
    adapter = TopDevAdapter(transport)
    raw = adapter.extract_raw_record(adapter.fetch_job_detail(transport.job_urls[0]))
    candidate = replace(
        raw,
        title_raw=title,
        source_category_raw="Information Technology",
        skills_raw=(),
    )
    assert is_it_scope(candidate, adapter.normalize_record(candidate)) is True


def test_business_model_validation_analyst_has_corroborated_it_evidence() -> None:
    transport = SyntheticTransport(1)
    adapter = TopDevAdapter(transport)
    raw = adapter.extract_raw_record(adapter.fetch_job_detail(transport.job_urls[0]))
    candidate = replace(
        raw,
        title_raw=("Senior Business Model Validation Analyst (BI) - Khối Dữ liệu"),
        source_category_raw="Information Technology",
        skills_raw=("Data Analytics", "Big Data", "Data Visualization"),
    )
    normalized = adapter.normalize_record(candidate)
    assert normalized.primary_category == "Business Intelligence"
    assert is_it_scope(candidate, normalized) is True


@pytest.mark.parametrize(
    ("title", "source_category", "source_tags"),
    [
        ("Giám đốc HDBank - Tỉnh Phú Yên", "Banking", ("Ngân Hàng",)),
        (
            "Chuyên viên Cao Cấp Tiếp thị số (Digital Marketing)",
            "Information Technology",
            ("Marketing", "Content"),
        ),
        (
            "Trưởng Ca Bán Hàng TokyoLife Ninh Bình",
            "Information Technology",
            ("Sales", "Business/Sales"),
        ),
        (
            "Kỹ Sư Xây Dựng / Triển Khai Bản Vẽ Cốp Pha Nhôm",
            "Information Technology",
            ("AutoCAD", "Revit"),
        ),
        (
            "Talent Acquisition Staff",
            "Information Technology",
            ("Talent Acquisition",),
        ),
        (
            "(Korean Candidates) Accounting",
            "Information Technology",
            ("Kế toán",),
        ),
    ],
)
def test_rejected_pilot_non_it_titles_remain_rejected(
    title: str, source_category: str, source_tags: tuple[str, ...]
) -> None:
    transport = SyntheticTransport(1)
    adapter = TopDevAdapter(transport)
    raw = adapter.extract_raw_record(adapter.fetch_job_detail(transport.job_urls[0]))
    candidate = replace(
        raw,
        title_raw=title,
        source_category_raw=source_category,
        skills_raw=source_tags,
    )
    assert is_it_scope(candidate, adapter.normalize_record(candidate)) is False


@pytest.mark.parametrize(
    ("url", "classification"),
    [
        ("https://topdev.vn/companies/example-123", "company page"),
        ("https://topdev.vn/viec-lam/tim-kiem", "category/listing page"),
        ("https://topdev.vn/not-a-job", "duplicate or malformed URL"),
    ],
)
def test_invalid_page_type_classification(url: str, classification: str) -> None:
    assert _invalid_url_classification(url) == classification


@pytest.mark.parametrize("limit", [0, 31])
def test_pilot_rejects_limits_outside_one_to_thirty(tmp_path: Path, limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 30"):
        run_pilot(
            TopDevAdapter(SyntheticTransport(35)),
            limit=limit,
            output_path=tmp_path / "output.jsonl",
            report_path=tmp_path / "report.json",
            diagnostic_path=tmp_path / "diagnostic.json",
        )
