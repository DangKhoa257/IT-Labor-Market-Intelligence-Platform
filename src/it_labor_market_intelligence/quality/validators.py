"""Field- and record-level validation over canonical JSON payloads."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from .issues import issue


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def validate_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return serializable issues; malformed input never raises."""

    raw = record.get("raw", {})
    normalized = record.get("normalized", {})
    findings = []
    for field in ("source", "source_job_id", "source_url", "title_raw"):
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            findings.append(
                issue(
                    record,
                    "required_missing",
                    "REJECT",
                    field,
                    "Required identity field is missing",
                    raw.get(field),
                    "non-empty string",
                )
            )
    url = raw.get("source_url")
    if isinstance(url, str):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            findings.append(
                issue(
                    record,
                    "url_malformed",
                    "REJECT",
                    "source_url",
                    "Source URL is malformed",
                    url,
                    "absolute HTTP/HTTPS URL",
                )
            )
    salary = normalized.get("salary", {})
    minimum, maximum = _decimal(salary.get("minimum")), _decimal(salary.get("maximum"))
    if any(value is not None and value < 0 for value in (minimum, maximum)):
        findings.append(
            issue(
                record,
                "salary_negative",
                "ERROR",
                "salary",
                "Salary cannot be negative",
                salary,
                "minimum and maximum >= 0",
            )
        )
    if minimum is not None and maximum is not None and minimum > maximum:
        findings.append(
            issue(
                record,
                "salary_range_invalid",
                "ERROR",
                "salary",
                "Salary minimum exceeds maximum",
                salary,
                "minimum <= maximum",
            )
        )
    if salary.get("salary_type") == "negotiable" and (minimum is not None or maximum is not None):
        findings.append(
            issue(
                record,
                "negotiable_numeric",
                "ERROR",
                "salary",
                "Negotiable salary has numeric bounds",
                salary,
                "negotiable has null bounds",
            )
        )
    if salary.get("disclosed") is False and (minimum is not None or maximum is not None):
        findings.append(
            issue(
                record,
                "undisclosed_numeric",
                "ERROR",
                "salary",
                "Undisclosed salary has numeric bounds",
                salary,
                "undisclosed has null bounds",
            )
        )
    if (minimum is not None or maximum is not None) and (
        not salary.get("currency") or not salary.get("period")
    ):
        findings.append(
            issue(
                record,
                "numeric_salary_semantics_missing",
                "WARNING",
                "salary",
                "Numeric salary lacks currency or period",
                salary,
                "numeric salary has currency and period",
            )
        )
    experience = normalized.get("experience", {})
    exp_min, exp_max = (
        _decimal(experience.get("minimum_years")),
        _decimal(experience.get("maximum_years")),
    )
    if any(value is not None and value < 0 for value in (exp_min, exp_max)):
        findings.append(
            issue(
                record,
                "experience_negative",
                "ERROR",
                "experience",
                "Experience cannot be negative",
                experience,
                "years >= 0",
            )
        )
    if exp_min is not None and exp_max is not None and exp_min > exp_max:
        findings.append(
            issue(
                record,
                "experience_range_invalid",
                "ERROR",
                "experience",
                "Experience minimum exceeds maximum",
                experience,
                "minimum <= maximum",
            )
        )
    posted, collected, expires = (
        _parse_datetime(raw.get(name))
        for name in ("posted_at_raw", "collected_at", "expires_at_raw")
    )
    if raw.get("posted_at_raw") is not None and posted is None:
        findings.append(
            issue(
                record,
                "posted_at_malformed",
                "WARNING",
                "posted_at_raw",
                "Posted date is malformed",
                raw.get("posted_at_raw"),
                "ISO-8601",
            )
        )
    if posted and collected and posted > collected:
        findings.append(
            issue(
                record,
                "posted_after_collected",
                "WARNING",
                "posted_at_raw",
                "Posted date is after collection",
                raw.get("posted_at_raw"),
                "posted <= collected",
            )
        )
    if expires and collected and expires < collected and raw.get("closed_state") == "ACTIVE":
        findings.append(
            issue(
                record,
                "active_past_expiry",
                "ERROR",
                "expires_at_raw",
                "Active record has past expiry",
                raw.get("expires_at_raw"),
                "expired/closed state",
            )
        )
    if raw.get("closed_state") not in {"ACTIVE", "EXPIRED", "CLOSED", "UNKNOWN"}:
        findings.append(
            issue(
                record,
                "closed_state_invalid",
                "ERROR",
                "closed_state",
                "Unsupported closed state",
                raw.get("closed_state"),
                "ACTIVE|EXPIRED|CLOSED|UNKNOWN",
            )
        )
    skills = normalized.get("skills", [])
    names = [item.get("canonical_name") for item in skills if isinstance(item, dict)]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        findings.append(
            issue(
                record,
                "skill_empty",
                "WARNING",
                "skills",
                "Skill list contains empty canonical name",
                names,
                "non-empty canonical names",
            )
        )
    if len(names) != len(set(names)):
        findings.append(
            issue(
                record,
                "skill_duplicate",
                "WARNING",
                "skills",
                "Canonical skill names are duplicated",
                names,
                "unique canonical names",
            )
        )
    return [
        finding.__dict__
        if hasattr(finding, "__dict__")
        else {
            "field_name": finding.field_name,
            "code": finding.code,
            "message": finding.message,
            "severity": finding.severity,
            "observed_value": finding.observed_value,
            "expected_rule": finding.expected_rule,
            "record_identifier": finding.record_identifier,
            "source": finding.source,
            "provenance_reference": finding.provenance_reference,
        }
        for finding in findings
    ]


def validate_dataset(
    records: Iterable[dict[str, Any]], reject_threshold: str = "REJECT"
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach quality issues and split accepted/rejected records deterministically."""

    levels = {"INFO": 0, "WARNING": 1, "ERROR": 2, "REJECT": 3}
    threshold = levels[reject_threshold]
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for record in records:
        result = dict(record)
        findings = validate_record(result)
        result["quality_issues"] = findings
        if any(levels.get(str(item["severity"]), 3) >= threshold for item in findings):
            rejected.append(result)
        else:
            accepted.append(result)
    return accepted, rejected
