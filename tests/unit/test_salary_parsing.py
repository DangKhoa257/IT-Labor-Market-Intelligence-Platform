"""Salary parsing tests use synthetic strings, not labor-market observations."""

from decimal import Decimal

import pytest

from it_labor_market_intelligence.processing.salary import parse_salary


@pytest.mark.parametrize(
    ("raw", "minimum", "maximum", "currency", "period", "salary_type"),
    [
        (
            "20-30 triệu VND/tháng gross",
            Decimal("20000000"),
            Decimal("30000000"),
            "VND",
            "month",
            "gross",
        ),
        (
            "USD 1,500 - 2,000 per month net",
            Decimal("1500"),
            Decimal("2000"),
            "USD",
            "month",
            "net",
        ),
        ("$25/hour", Decimal("25"), Decimal("25"), "USD", "hour", None),
        ("120k USD yearly", Decimal("120000"), Decimal("120000"), "USD", "year", None),
        ("1.5 million VND", Decimal("1500000"), Decimal("1500000"), "VND", None, None),
        ("from 2,000 USD", Decimal("2000"), None, "USD", None, None),
        ("up to 50 triệu VND", None, Decimal("50000000"), "VND", None, None),
    ],
)
def test_supported_salary_forms(
    raw: str,
    minimum: Decimal | None,
    maximum: Decimal | None,
    currency: str | None,
    period: str | None,
    salary_type: str | None,
) -> None:
    result = parse_salary(raw)
    assert (result.minimum, result.maximum) == (minimum, maximum)
    assert (result.currency, result.period, result.salary_type) == (
        currency,
        period,
        salary_type,
    )
    assert result.salary_raw == raw
    assert result.disclosed is True
    assert result.confidence > 0
    assert result.evidence


@pytest.mark.parametrize("raw", ["Negotiable", "Thỏa thuận", "thoa thuan", "Thương lượng"])
def test_negotiable_is_undisclosed_and_has_no_numbers(raw: str) -> None:
    result = parse_salary(f"{raw} 20 triệu VND")
    assert result.disclosed is False
    assert result.minimum is None and result.maximum is None
    assert result.salary_type == "negotiable"
    assert result.salary_raw == f"{raw} 20 triệu VND"


def test_missing_semantics_are_not_defaulted() -> None:
    result = parse_salary("1000")
    assert result.currency is None
    assert result.period is None
    assert result.salary_type is None
    assert result.minimum == result.maximum == Decimal("1000")


def test_ambiguous_currency_is_null() -> None:
    result = parse_salary("1000 USD / 25,000,000 VND per month")
    assert result.currency is None
    assert "ambiguous_currency" in result.evidence


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_salary_is_undisclosed(raw: str | None) -> None:
    result = parse_salary(raw)
    assert result.disclosed is False
    assert result.minimum is None and result.maximum is None
    assert result.confidence == 1.0
