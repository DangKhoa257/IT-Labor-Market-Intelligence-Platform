"""Conservative deterministic salary parsing for offline processing."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from it_labor_market_intelligence.domain import (
    Currency,
    FieldProvenance,
    Salary,
    SalaryPeriod,
    SalaryType,
)

RULE_VERSION = "salary.v1"
_NUMBER = re.compile(
    r"(?<![\w.])\d+(?:[.,]\d+)*(?:(?=\s*(?:k|triệu|trieu|million|mn|mio)\b)|(?!\w))"
)
_NEGOTIABLE = re.compile(
    r"\bnegotiable\b|\bthỏa\s+thuận\b|\bthoa\s+thuan\b|\bthương\s+lượng\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    translation: dict[str | int, str | int | None] = {
        "–": "-",
        "—": "-",
        "−": "-",
        "₫": " vnd ",
    }
    return unicodedata.normalize("NFKC", text).casefold().translate(str.maketrans(translation))


def _decimal(token: str) -> Decimal | None:
    separators = {character for character in token if character in ".,"}
    candidate = token
    if len(separators) == 2:
        decimal_mark = "." if token.rfind(".") > token.rfind(",") else ","
        thousands_mark = "," if decimal_mark == "." else "."
        candidate = token.replace(thousands_mark, "").replace(decimal_mark, ".")
    elif separators:
        mark = separators.pop()
        pieces = token.split(mark)
        if len(pieces) > 2 or (len(pieces) == 2 and len(pieces[1]) == 3):
            candidate = "".join(pieces)
        else:
            candidate = token.replace(mark, ".")
    try:
        return Decimal(candidate)
    except InvalidOperation:
        return None


def _scale_for(text: str, match: re.Match[str]) -> Decimal:
    suffix = text[match.end() : match.end() + 15]
    if re.match(r"\s*(?:triệu|trieu|million|mn|mio)\b", suffix):
        return Decimal("1000000")
    if re.match(r"\s*(?:k\b|thousand\b)", suffix):
        return Decimal("1000")
    # In a compact range such as "20-30 triệu", the shared suffix applies to both ends.
    if re.search(r"^\s*(?:-|to|đến)\s*\d+(?:[.,]\d+)*\s*(?:triệu|trieu|million)\b", suffix):
        return Decimal("1000000")
    if re.search(r"^\s*(?:-|to)\s*\d+(?:[.,]\d+)*\s*k\b", suffix):
        return Decimal("1000")
    return Decimal(1)


def _currency(text: str) -> tuple[Currency | None, list[str]]:
    usd = bool(re.search(r"(?<!\w)(?:usd|us\s*dollars?|dollars?)(?!\w)|\$", text))
    vnd = bool(re.search(r"(?<!\w)(?:vnd|vnđ|đồng)(?!\w)", text))
    if usd == vnd:
        return None, (["ambiguous_currency"] if usd else ["currency_not_stated"])
    return ("USD" if usd else "VND"), ["explicit_currency"]


def _period(text: str) -> tuple[SalaryPeriod | None, list[str]]:
    patterns: dict[SalaryPeriod, str] = {
        "hour": r"/\s*(?:h|hr|hour)\b|\b(?:per\s+)?hour(?:ly)?\b|\b(?:mỗi\s+)?giờ\b",
        "month": r"/\s*(?:mo|month)\b|\b(?:per\s+)?month(?:ly)?\b|\b(?:mỗi\s+)?tháng\b",
        "year": (
            r"/\s*(?:yr|year)\b|\b(?:per\s+)?year(?:ly)?\b|" r"\bannual(?:ly)?\b|\b(?:mỗi\s+)?năm\b"
        ),
    }
    found = [period for period, pattern in patterns.items() if re.search(pattern, text)]
    if len(found) == 1:
        return found[0], ["explicit_period"]
    return None, ["ambiguous_period" if found else "period_not_stated"]


def _salary_type(text: str) -> tuple[SalaryType | None, list[str]]:
    gross = bool(re.search(r"(?<!\w)gross(?!\w)|\btrước\s+thuế\b", text))
    net = bool(re.search(r"(?<!\w)net(?!\w)|\bsau\s+thuế\b", text))
    if gross == net:
        return None, (["ambiguous_salary_type"] if gross else ["salary_type_not_stated"])
    return ("gross" if gross else "net"), ["explicit_salary_type"]


def _provenance(raw: str | None, confidence: float, method: str) -> FieldProvenance:
    return FieldProvenance(
        source_field="salary_raw",
        method=method,
        rule_version=RULE_VERSION,
        confidence=confidence,
        evidence_text=raw,
        evidence_key=None if raw is not None else "salary_raw:null",
    )


def parse_salary(raw_text: str | None) -> Salary:
    """Parse a salary string without supplying unstated semantics."""

    if raw_text is None or not raw_text.strip():
        confidence = 1.0
        return Salary(
            raw_text,
            None,
            None,
            None,
            None,
            None,
            False,
            confidence,
            ("missing_salary",),
            _provenance(raw_text, confidence, "null_semantics"),
        )

    text = _normalize(raw_text)
    currency, currency_evidence = _currency(text)
    period, period_evidence = _period(text)
    salary_type, type_evidence = _salary_type(text)

    if _NEGOTIABLE.search(text):
        confidence = 1.0
        return Salary(
            raw_text,
            None,
            None,
            currency,
            period,
            "negotiable",
            False,
            confidence,
            tuple(["negotiable_phrase", *currency_evidence, *period_evidence]),
            _provenance(raw_text, confidence, "negotiable_phrase"),
        )

    matches = list(_NUMBER.finditer(text))
    values = [
        value * _scale_for(text, match)
        for match in matches
        if (value := _decimal(match.group())) is not None
    ]
    if not values:
        confidence = 0.0
        return Salary(
            raw_text,
            None,
            None,
            currency,
            period,
            salary_type,
            False,
            confidence,
            tuple(["no_numeric_salary", *currency_evidence, *period_evidence, *type_evidence]),
            _provenance(raw_text, confidence, "unparsed"),
        )

    if len(values) >= 2:
        minimum, maximum = values[0], values[1]
        shape = "range"
    elif re.search(r"\b(?:up\s+to|maximum|max|tối\s+đa|đến)\b", text):
        minimum, maximum = None, values[0]
        shape = "upper_bound"
    elif re.search(r"\b(?:from|minimum|min|at\s+least|từ|ít\s+nhất)\b", text):
        minimum, maximum = values[0], None
        shape = "lower_bound"
    else:
        minimum = maximum = values[0]
        shape = "single_value"

    if minimum is not None and maximum is not None and minimum > maximum:
        minimum, maximum = maximum, minimum
        shape = "range_reordered"

    explicit_count = sum(item is not None for item in (currency, period, salary_type))
    confidence = min(0.99, 0.72 + (0.08 * explicit_count))
    evidence = tuple([shape, *currency_evidence, *period_evidence, *type_evidence])
    return Salary(
        raw_text,
        minimum,
        maximum,
        currency,
        period,
        salary_type,
        True,
        confidence,
        evidence,
        _provenance(raw_text, confidence, "regex_numeric_parse"),
    )
