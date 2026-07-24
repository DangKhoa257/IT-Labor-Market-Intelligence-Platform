"""Tests for the deterministic title taxonomy baseline."""

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
