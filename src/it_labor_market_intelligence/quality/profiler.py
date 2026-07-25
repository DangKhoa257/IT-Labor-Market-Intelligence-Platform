"""Deterministic standard-library dataset profiling."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any, cast


def _raw(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("raw", {})
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _normalized(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("normalized", {})
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _top(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def profile_dataset(
    records: Iterable[dict[str, Any]], accepted_count: int | None = None, rejected_count: int = 0
) -> dict[str, Any]:
    values = list(records)
    total = len(values)
    raw_fields = (
        "source",
        "source_job_id",
        "source_url",
        "title_raw",
        "company_name_raw",
        "location_raw",
        "salary_raw",
        "skills_raw",
        "experience_raw",
    )
    fields: dict[str, dict[str, Any]] = {}
    for field in raw_fields:
        observed = [_raw(record).get(field) for record in values]
        present = sum(value is not None and value != "" and value != [] for value in observed)
        empty = sum(value == "" for value in observed)
        distinct = {str(value) for value in observed if value is not None and value != ""}
        fields[field] = {
            "presence_count": present,
            "coverage": _rate(present, total),
            "null_rate": _rate(sum(value is None for value in observed), total),
            "empty_string_rate": _rate(empty, total),
            "distinct_count": len(distinct),
        }
    issue_codes: Counter[str] = Counter()
    issue_levels: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    states: Counter[str] = Counter()
    skills: Counter[str] = Counter()
    cities: Counter[str] = Counter()
    employment: Counter[str] = Counter()
    work_modes: Counter[str] = Counter()
    salary_disclosed = salary_parsed = experience_parsed = skill_records = 0
    info_notice_records = warning_error_records = title_classified_records = 0
    identities: Counter[tuple[str | None, str | None]] = Counter()
    for record in values:
        raw, normalized = _raw(record), _normalized(record)
        identities[(raw.get("source"), raw.get("source_job_id"))] += 1
        states[str(raw.get("closed_state"))] += 1
        categories[str(normalized.get("primary_category"))] += 1
        title_classified_records += normalized.get("primary_category") not in {
            None,
            "Unclassified",
        }
        salary = normalized.get("salary", {})
        experience = normalized.get("experience", {})
        salary_disclosed += bool(salary.get("disclosed"))
        salary_parsed += salary.get("confidence", 0) > 0
        experience_parsed += (
            experience.get("confidence", 0) > 0 and raw.get("experience_raw") is not None
        )
        matched = normalized.get("skills", [])
        skill_records += bool(matched)
        for match in matched:
            if isinstance(match, dict) and isinstance(match.get("canonical_name"), str):
                skills[match["canonical_name"]] += 1
        enrichment = record.get("enrichment", {})
        location = enrichment.get("location", {})
        if location.get("city"):
            cities[str(location["city"])] += 1
        employment_value = enrichment.get("employment", {}).get("employment_type")
        if employment_value:
            employment[str(employment_value)] += 1
        work_mode = enrichment.get("work_mode", {}).get("work_mode")
        if work_mode:
            work_modes[str(work_mode)] += 1
        findings = [
            *record.get("quality_issues", []),
            *normalized.get("validation_issues", []),
        ]
        severities = {
            str(finding.get("severity", "INFO")).upper()
            for finding in findings
            if isinstance(finding, dict)
        }
        info_notice_records += "INFO" in severities
        warning_error_records += bool(severities & {"WARNING", "ERROR"})
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            issue_codes[str(finding.get("code"))] += 1
            issue_levels[str(finding.get("severity", "INFO")).upper()] += 1
    return {
        "total_records": total,
        "accepted_records": total if accepted_count is None else accepted_count,
        "rejected_records": rejected_count,
        "unique_source_job_ids": len(identities),
        "duplicate_identity_count": sum(count - 1 for count in identities.values() if count > 1),
        "fields": dict(sorted(fields.items())),
        "validation_issues_by_code": _top(issue_codes),
        "validation_issues_by_severity": _top(issue_levels),
        "salary_disclosed_rate": _rate(salary_disclosed, total),
        "salary_parsing_success_rate": _rate(salary_parsed, total),
        "experience_parsing_success_rate": _rate(experience_parsed, total),
        "skill_extraction_coverage": _rate(skill_records, total),
        "records_with_info_notices": info_notice_records,
        "records_with_warning_or_error_issues": warning_error_records,
        "title_classified_records": title_classified_records,
        "title_classification_coverage": _rate(title_classified_records, total),
        "closed_state_distribution": _top(states),
        "title_category_distribution": _top(categories),
        "city_distribution": _top(cities),
        "employment_type_distribution": _top(employment),
        "work_mode_distribution": _top(work_modes),
        "top_skills": _top(skills),
    }
