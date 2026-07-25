"""Dependency-free probabilistic duplicate similarity."""

from __future__ import annotations

from typing import Any

from .fingerprints import probable_fingerprint


def _jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set, right_set = set(left), set(right)
    if not left_set and not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def compare_records(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    first, second = probable_fingerprint(left), probable_fingerprint(right)
    title_score = _jaccard(first["title_tokens"], second["title_tokens"])
    skill_score = _jaccard(first["skills"], second["skills"])
    company = bool(first["company"] and first["company"] == second["company"])
    city = bool(first["city"] and first["city"] == second["city"])
    employment = bool(
        first["employment_type"] and first["employment_type"] == second["employment_type"]
    )
    salary = bool(first["salary"][0] is not None and first["salary"] == second["salary"])
    score = (
        (0.40 * title_score)
        + (0.25 * float(company))
        + (0.15 * skill_score)
        + (0.10 * float(city))
        + (0.05 * float(employment))
        + (0.05 * float(salary))
    )
    explicit_company_conflict = bool(
        first["company"] and second["company"] and first["company"] != second["company"]
    )
    if explicit_company_conflict:
        classification = "DISTINCT"
    elif score >= 0.8:
        classification = "PROBABLE_DUPLICATE"
    elif score >= 0.6:
        classification = "POSSIBLE_DUPLICATE"
    else:
        classification = "DISTINCT"
    return {
        "classification": classification,
        "score": round(score, 4),
        "matched_features": [
            name
            for name, matched in (
                ("company", company),
                ("city", city),
                ("employment_type", employment),
                ("salary", salary),
            )
            if matched
        ]
        + (["title_tokens"] if title_score else [])
        + (["skills"] if skill_score else []),
        "conflicting_features": [
            name
            for name in ("company", "city")
            if first[name] and second[name] and first[name] != second[name]
        ],
        "method_version": "dedup.v1",
        "confidence": round(score, 4),
    }
