"""Composition root for source adapters to invoke canonical offline processing."""

from __future__ import annotations

from collections.abc import Sequence

from it_labor_market_intelligence.domain import (
    FieldProvenance,
    NormalizedJobRecord,
    RawJobRecord,
    ValidationIssue,
)

from .experience import parse_experience
from .job_titles import normalize_job_title
from .salary import parse_salary
from .skills import SkillDefinition, match_skills
from .skills.taxonomy import TAXONOMY_VERSION


def _skill_input(record: RawJobRecord) -> tuple[str, str, str]:
    if record.skills_raw is not None:
        return "\n".join(record.skills_raw), "skills_raw", "skills_raw:joined"
    return record.description_raw, "description_raw", "description_raw"


def normalize_job_record(
    record: RawJobRecord,
    taxonomy: Sequence[SkillDefinition] | None = None,
) -> NormalizedJobRecord:
    """Apply all deterministic normalizers to a source-independent raw contract."""

    title = normalize_job_title(record.title_raw)
    salary = parse_salary(record.salary_raw)
    experience = parse_experience(record.experience_raw)
    skill_text, skill_source, skill_evidence_key = _skill_input(record)
    skills = match_skills(skill_text, taxonomy, source_field=skill_source)
    skills_confidence = min((match.confidence for match in skills), default=1.0)
    skills_provenance = FieldProvenance(
        source_field=skill_source,
        method="boundary_alias_match",
        rule_version=TAXONOMY_VERSION,
        confidence=skills_confidence,
        evidence_key=skill_evidence_key,
    )

    provenance = {
        "title_normalized": title.provenance,
        "primary_category": title.provenance,
        "secondary_categories": title.provenance,
        "salary.minimum": salary.provenance,
        "salary.maximum": salary.provenance,
        "salary.currency": salary.provenance,
        "salary.period": salary.provenance,
        "salary.salary_type": salary.provenance,
        "salary.disclosed": salary.provenance,
        "experience.minimum_years": experience.provenance,
        "experience.maximum_years": experience.provenance,
        "experience.minimum_inclusive": experience.provenance,
        "experience.maximum_inclusive": experience.provenance,
        "skills": skills_provenance,
    }

    issues: list[ValidationIssue] = []
    if record.salary_raw and salary.confidence == 0.0:
        issues.append(
            ValidationIssue(
                "salary", "salary_unparsed", "Salary text had no numeric value", "warning"
            )
        )
    if salary.disclosed and salary.currency is None:
        issues.append(
            ValidationIssue(
                "salary.currency",
                "currency_missing_or_ambiguous",
                "Numeric salary has no unambiguous explicit currency",
                "warning",
            )
        )
    if record.experience_raw and experience.confidence == 0.0:
        issues.append(
            ValidationIssue(
                "experience", "experience_unparsed", "Experience text was not recognized", "warning"
            )
        )
    if title.primary_category == "Unclassified":
        issues.append(
            ValidationIssue(
                "primary_category",
                "title_unclassified",
                "No deterministic title rule matched",
                "INFO",
            )
        )

    return NormalizedJobRecord(
        source=record.source,
        source_job_id=record.source_job_id,
        source_url=record.source_url,
        title_raw=record.title_raw,
        title_normalized=title.title_normalized,
        primary_category=title.primary_category,
        secondary_categories=title.secondary_categories,
        salary=salary,
        experience=experience,
        skills=skills,
        collected_at=record.collected_at,
        field_provenance=provenance,
        validation_issues=tuple(issues),
    )
