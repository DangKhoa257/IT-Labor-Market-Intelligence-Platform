"""Source-independent domain contracts for offline job processing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

Currency = Literal["VND", "USD"]
SalaryPeriod = Literal["hour", "month", "year"]
SalaryType = Literal["gross", "net", "negotiable"]
IssueSeverity = Literal["INFO", "WARNING", "ERROR", "REJECT", "error", "warning"]


def _validate_confidence(confidence: float) -> None:
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    """Evidence and versioned deterministic method for one derived field."""

    source_field: str
    method: str
    rule_version: str
    confidence: float
    evidence_text: str | None = None
    evidence_key: str | None = None

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        if (
            not self.source_field.strip()
            or not self.method.strip()
            or not self.rule_version.strip()
        ):
            raise ValueError("source_field, method, and rule_version are required")
        if self.evidence_text is None and self.evidence_key is None:
            raise ValueError("provenance requires evidence_text or evidence_key")


@dataclass(frozen=True, slots=True)
class Salary:
    """Parsed salary with no implicit currency, period, or gross/net defaults."""

    salary_raw: str | None
    minimum: Decimal | None
    maximum: Decimal | None
    currency: Currency | None
    period: SalaryPeriod | None
    salary_type: SalaryType | None
    disclosed: bool
    confidence: float
    evidence: tuple[str, ...]
    provenance: FieldProvenance

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        if not self.disclosed and (self.minimum is not None or self.maximum is not None):
            raise ValueError("undisclosed salary cannot contain numeric values")
        if self.disclosed and self.minimum is None and self.maximum is None:
            raise ValueError("disclosed salary requires at least one numeric value")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("salary minimum cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class ExperienceRange:
    """Parsed years-of-experience range; null differs from explicit zero."""

    experience_raw: str | None
    minimum_years: Decimal | None
    maximum_years: Decimal | None
    minimum_inclusive: bool
    maximum_inclusive: bool
    confidence: float
    evidence: tuple[str, ...]
    provenance: FieldProvenance

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        if (
            self.minimum_years is not None
            and self.maximum_years is not None
            and self.minimum_years > self.maximum_years
        ):
            raise ValueError("experience minimum cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class SkillMatch:
    """One canonical skill match and its exact source evidence span."""

    canonical_name: str
    matched_alias: str
    category: str
    start: int
    end: int
    evidence_text: str
    confidence: float
    provenance: FieldProvenance

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        if (
            self.start < 0
            or self.end <= self.start
            or self.end - self.start != len(self.evidence_text)
        ):
            raise ValueError("skill evidence span is invalid")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A non-destructive validation finding attached to a canonical field."""

    field_name: str
    code: str
    message: str
    severity: IssueSeverity
    observed_value: object | None = None
    expected_rule: str | None = None
    record_identifier: str | None = None
    source: str | None = None
    provenance_reference: str | None = None


@dataclass(frozen=True, slots=True)
class RawJobRecord:
    """Source-adapter output before canonical normalization."""

    source: str
    source_job_id: str
    source_url: str
    title_raw: str
    description_raw: str
    collected_at: datetime
    salary_raw: str | None = None
    experience_raw: str | None = None
    skills_raw: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        required = {
            "source": self.source,
            "source_job_id": self.source_job_id,
            "source_url": self.source_url,
            "title_raw": self.title_raw,
            "description_raw": self.description_raw,
        }
        if missing := [name for name, value in required.items() if not value.strip()]:
            raise ValueError(f"required raw fields cannot be blank: {', '.join(missing)}")
        if self.collected_at.tzinfo is None or self.collected_at.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class NormalizedJobRecord:
    """Source-independent record produced by the offline processing pipeline."""

    source: str
    source_job_id: str
    source_url: str
    title_raw: str
    title_normalized: str
    primary_category: str
    secondary_categories: tuple[str, ...]
    salary: Salary
    experience: ExperienceRange
    skills: tuple[SkillMatch, ...]
    collected_at: datetime
    field_provenance: Mapping[str, FieldProvenance] = field(default_factory=dict)
    validation_issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_provenance", MappingProxyType(dict(self.field_provenance)))
