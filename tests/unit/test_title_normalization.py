"""Tests for the deterministic title taxonomy baseline."""

import pytest

from it_labor_market_intelligence.processing.job_titles import normalize_job_title


def test_title_alias_is_normalized_and_classified() -> None:
    result = normalize_job_title("Senior Back-end Engineer")
    assert result.title_raw == "Senior Back-end Engineer"
    assert result.title_normalized == "Senior Backend Engineer"
    assert result.primary_category == "Backend"
    assert result.secondary_categories == ()
    assert result.confidence == 0.95
    assert result.matched_rules == ("backend",)


def test_vietnamese_diacritics_are_preserved() -> None:
    result = normalize_job_title("Kỹ sư Data Engineer")
    assert result.title_normalized.startswith("Kỹ Sư")
    assert result.primary_category == "Data Engineer"


def test_multi_role_title_has_deterministic_secondary_category() -> None:
    result = normalize_job_title("DevOps Engineer / Backend Engineer")
    assert result.primary_category == "DevOps/Cloud/SRE"
    assert result.secondary_categories == ("Backend",)
    assert result.confidence < 0.95


def test_unknown_title_falls_back_without_accuracy_claim() -> None:
    result = normalize_job_title("Technology Wizard")
    assert result.primary_category == "Unclassified"
    assert result.confidence == 0.0
    assert result.matched_rules == ("fallback_unclassified",)


@pytest.mark.parametrize(
    ("title", "category"),
    [
        ("AI Software Engineer (Python/Go/C/C++ Backend & AI Agents)", "AI/Machine Learning"),
        ("Agentic Engineer (Python/Go/C/C++ Backend & AI Agents)", "AI/Machine Learning"),
        ("AI Solution Architect", "AI/Machine Learning"),
        ("Deputy Head of Machine Learning Engineering", "AI/Machine Learning"),
        (
            "Chuyên viên Giải pháp Cloud, Data Center và An toàn thông tin",
            "DevOps/Cloud/SRE",
        ),
        ("Chuyên viên Triển khai và Vận hành Hạ tầng CNTT", "IT Support/System Administration"),
        ("DBA", "IT Support/System Administration"),
        ("Technical Analyst", "Business Analyst"),
        ("[Game Live-Ops]_Mobile Game Developer Senior", "Mobile"),
        (
            "Senior Business Model Validation Analyst (BI) - Khối Dữ liệu",
            "Business Intelligence",
        ),
    ],
)
def test_retained_topdev_technical_titles_are_classified(title: str, category: str) -> None:
    assert normalize_job_title(title).primary_category == category


@pytest.mark.parametrize("title", ["Marketing Analyst", "Sales Executive"])
def test_clear_non_it_commercial_titles_are_not_classified_as_it(title: str) -> None:
    assert normalize_job_title(title).primary_category == "Unclassified"
