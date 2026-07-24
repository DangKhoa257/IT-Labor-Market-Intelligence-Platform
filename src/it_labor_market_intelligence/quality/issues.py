"""Quality issue construction helpers."""

from __future__ import annotations

from typing import Any

from it_labor_market_intelligence.domain import ValidationIssue


def issue(
    record: dict[str, Any],
    code: str,
    level: str,
    field: str,
    message: str,
    observed: Any,
    rule: str,
) -> ValidationIssue:
    raw = record.get("raw", {})
    return ValidationIssue(
        field_name=field,
        code=code,
        message=message,
        severity=level,  # type: ignore[arg-type]
        observed_value=observed,
        expected_rule=rule,
        record_identifier=str(raw.get("source_job_id")) if raw.get("source_job_id") else None,
        source=str(raw.get("source")) if raw.get("source") else None,
        provenance_reference=f"normalized.field_provenance.{field}",
    )
