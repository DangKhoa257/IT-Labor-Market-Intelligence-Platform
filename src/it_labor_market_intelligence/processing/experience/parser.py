"""Vietnamese and English deterministic experience parsing."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from it_labor_market_intelligence.domain import ExperienceRange, FieldProvenance

RULE_VERSION = "experience.v1"
_NO_EXPERIENCE = re.compile(
    r"\bno\s+(?:work\s+)?experience\s+(?:is\s+)?required\b"
    r"|\bexperience\s+not\s+required\b"
    r"|\bkhông\s+(?:yêu\s+cầu|cần)\s+kinh\s+nghiệm\b"
    r"|\bchưa\s+có\s+kinh\s+nghiệm\b",
)
_UNDER = re.compile(
    r"\b(?:under|less\s+than|below)\s*(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?)\b"
    r"|\b(?:dưới|ít\s+hơn)\s*(\d+(?:[.,]\d+)?)\s*năm\b"
)
_RANGE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?)\b"
    r"|\b(?:từ\s+)?(\d+(?:[.,]\d+)?)\s*(?:-|–|—|đến|tới)\s*"
    r"(\d+(?:[.,]\d+)?)\s*năm\b"
)
_MORE_THAN = re.compile(
    r"\b(?:more\s+than|over|greater\s+than)\s*(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?)\b"
    r"|\b(?:hơn|trên)\s*(\d+(?:[.,]\d+)?)\s*năm\b"
)
_MINIMUM = re.compile(
    r"\b(?:minimum|min(?:imum)?\.?|at\s+least)\s*(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?)\b"
    r"|\b(\d+(?:[.,]\d+)?)\+\s*(?:years?|yrs?)\b"
    r"|\b(?:tối\s+thiểu|ít\s+nhất)\s*(\d+(?:[.,]\d+)?)\s*năm\b"
    r"|\b(?:từ)\s*(\d+(?:[.,]\d+)?)\s*năm\b"
)
_MINIMUM_MONTHS = re.compile(
    r"\b(?:minimum|min(?:imum)?\.?|at\s+least)\s*(\d+(?:[.,]\d+)?)\s*(?:months?|mos?)\b"
    r"|\b(?:tối\s+thiểu|ít\s+nhất)\s*(\d+(?:[.,]\d+)?)\s*tháng\b"
)


def _number(*groups: str | None) -> Decimal:
    value = next(group for group in groups if group is not None)
    return Decimal(value.replace(",", "."))


def _provenance(raw: str | None, confidence: float, method: str) -> FieldProvenance:
    return FieldProvenance(
        source_field="experience_raw",
        method=method,
        rule_version=RULE_VERSION,
        confidence=confidence,
        evidence_text=raw,
        evidence_key=None if raw is not None else "experience_raw:null",
    )


def _result(
    raw: str | None,
    minimum: Decimal | None,
    maximum: Decimal | None,
    minimum_inclusive: bool,
    maximum_inclusive: bool,
    confidence: float,
    rule: str,
    evidence: str,
) -> ExperienceRange:
    return ExperienceRange(
        experience_raw=raw,
        minimum_years=minimum,
        maximum_years=maximum,
        minimum_inclusive=minimum_inclusive,
        maximum_inclusive=maximum_inclusive,
        confidence=confidence,
        evidence=(evidence,),
        provenance=_provenance(raw, confidence, rule),
    )


def parse_experience(raw_text: str | None) -> ExperienceRange:
    """Parse explicit experience constraints; absence never becomes zero."""

    if raw_text is None or not raw_text.strip():
        return _result(raw_text, None, None, False, False, 1.0, "null_semantics", "missing")

    text = unicodedata.normalize("NFKC", raw_text).casefold()
    if match := _NO_EXPERIENCE.search(text):
        return _result(
            raw_text,
            Decimal(0),
            Decimal(0),
            True,
            True,
            1.0,
            "no_experience_phrase",
            match.group(),
        )
    if match := _UNDER.search(text):
        return _result(
            raw_text,
            None,
            _number(*match.groups()),
            False,
            False,
            0.98,
            "exclusive_upper_bound",
            match.group(),
        )
    if match := _RANGE.search(text):
        groups = match.groups()
        minimum = _number(groups[0], groups[2])
        maximum = _number(groups[1], groups[3])
        if minimum > maximum:
            return _result(
                raw_text,
                None,
                None,
                False,
                False,
                0.0,
                "invalid_range",
                match.group(),
            )
        return _result(
            raw_text, minimum, maximum, True, True, 0.99, "inclusive_range", match.group()
        )
    if match := _MORE_THAN.search(text):
        return _result(
            raw_text,
            _number(*match.groups()),
            None,
            False,
            False,
            0.98,
            "exclusive_lower_bound",
            match.group(),
        )
    if match := _MINIMUM_MONTHS.search(text):
        months = _number(*match.groups())
        return _result(
            raw_text,
            months / Decimal(12),
            None,
            True,
            False,
            0.98,
            "inclusive_lower_bound_months",
            match.group(),
        )
    if match := _MINIMUM.search(text):
        return _result(
            raw_text,
            _number(*match.groups()),
            None,
            True,
            False,
            0.98,
            "inclusive_lower_bound",
            match.group(),
        )
    return _result(raw_text, None, None, False, False, 0.0, "unparsed", raw_text)
