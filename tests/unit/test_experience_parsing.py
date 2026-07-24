"""Experience parser tests for Vietnamese, English, ambiguity, and nulls."""

from decimal import Decimal

import pytest

from it_labor_market_intelligence.processing.experience import parse_experience


@pytest.mark.parametrize(
    ("raw", "minimum", "maximum", "minimum_inclusive", "maximum_inclusive"),
    [
        ("No experience required", Decimal(0), Decimal(0), True, True),
        ("Không yêu cầu kinh nghiệm", Decimal(0), Decimal(0), True, True),
        ("under 1 year", None, Decimal(1), False, False),
        ("Dưới 1 năm", None, Decimal(1), False, False),
        ("minimum 3 years", Decimal(3), None, True, False),
        ("Tối thiểu 2 năm", Decimal(2), None, True, False),
        ("3-5 years", Decimal(3), Decimal(5), True, True),
        ("Từ 2 đến 4 năm", Decimal(2), Decimal(4), True, True),
        ("more than 5 years", Decimal(5), None, False, False),
        ("Trên 3 năm", Decimal(3), None, False, False),
        ("minimum 24 months", Decimal(2), None, True, False),
    ],
)
def test_supported_experience_forms(
    raw: str,
    minimum: Decimal | None,
    maximum: Decimal | None,
    minimum_inclusive: bool,
    maximum_inclusive: bool,
) -> None:
    result = parse_experience(raw)
    assert (result.minimum_years, result.maximum_years) == (minimum, maximum)
    assert (result.minimum_inclusive, result.maximum_inclusive) == (
        minimum_inclusive,
        maximum_inclusive,
    )
    assert result.evidence


@pytest.mark.parametrize("raw", [None, "", "Experience preferred", "Có kinh nghiệm là lợi thế"])
def test_missing_or_ambiguous_experience_never_becomes_zero(
    raw: str | None,
) -> None:
    result = parse_experience(raw)
    assert result.minimum_years is None
    assert result.maximum_years is None


def test_reversed_range_is_rejected_conservatively() -> None:
    result = parse_experience("5-2 years")
    assert result.minimum_years is None and result.maximum_years is None
    assert result.confidence == 0.0
