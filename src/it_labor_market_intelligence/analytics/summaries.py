"""Source-agnostic descriptive statistics without pandas."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from statistics import mean, median, quantiles
from typing import Any


def _counter(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"value": key, "count": value}
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _salary_summary(records: list[dict]) -> dict[str, Any]:
    groups: dict[str, list[Decimal]] = {}
    for record in records:
        salary = record.get("normalized", {}).get("salary", {})
        if (
            salary.get("minimum") is None
            or salary.get("maximum") is None
            or not salary.get("currency")
        ):
            continue
        midpoint = (Decimal(str(salary["minimum"])) + Decimal(str(salary["maximum"]))) / 2
        groups.setdefault(str(salary["currency"]), []).append(midpoint)
    results: dict[str, Any] = {}
    for currency, values in sorted(groups.items()):
        ordered = sorted(values)
        results[currency] = {
            "numeric_sample_count": len(ordered),
            "mean": str(round(Decimal(str(mean(ordered))), 2)),
            "median": str(median(ordered)),
            "min": str(ordered[0]),
            "max": str(ordered[-1]),
            "quartiles": (
                [str(item) for item in quantiles(ordered, n=4, method="inclusive")]
                if len(ordered) >= 2
                else []
            ),
        }
    return results


def analyze_records(records: list[dict], generated_at: str) -> dict[str, Any]:
    companies: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    cities: Counter[str] = Counter()
    work_modes: Counter[str] = Counter()
    skills: Counter[str] = Counter()
    pairs: Counter[str] = Counter()
    states: Counter[str] = Counter()
    disclosed = 0
    for record in records:
        raw, normalized, enrichment = (
            record.get("raw", {}),
            record.get("normalized", {}),
            record.get("enrichment", {}),
        )
        company = enrichment.get("company", {}).get("company_name_normalized") or raw.get(
            "company_name_raw"
        )
        if company:
            companies[str(company)] += 1
        categories[str(normalized.get("primary_category", "Unclassified"))] += 1
        state = raw.get("closed_state")
        if state:
            states[str(state)] += 1
        city = enrichment.get("location", {}).get("city")
        if city:
            cities[str(city)] += 1
        mode = enrichment.get("work_mode", {}).get("work_mode")
        if mode:
            work_modes[str(mode)] += 1
        salary = normalized.get("salary", {})
        disclosed += bool(salary.get("disclosed"))
        names = sorted(
            match.get("canonical_name")
            for match in normalized.get("skills", [])
            if isinstance(match, dict) and match.get("canonical_name")
        )
        skills.update(names)
        for left, right in zip(names, names[1:], strict=False):
            pairs[f"{left} | {right}"] += 1
    total = len(records)
    return {
        "sample_size": total,
        "generated_at": generated_at,
        "source_coverage": _counter(
            Counter(str(record.get("raw", {}).get("source")) for record in records)
        ),
        "limitations": [
            "Descriptive output is limited to this offline input sample.",
            "Salary statistics are separated by currency; no exchange rate is applied.",
        ],
        "market_overview": {
            "total_accepted_jobs": total,
            "unique_companies": len(companies),
            "disclosed_salary_rate": round(disclosed / total, 4) if total else 0.0,
            "active_job_count": states["ACTIVE"],
        },
        "category": _counter(categories),
        "skills": {"top_skills": _counter(skills), "co_occurrence_pairs": _counter(pairs)},
        "salary": _salary_summary(records),
        "companies": _counter(companies),
        "locations": {"cities": _counter(cities), "work_modes": _counter(work_modes)},
        "closed_states": _counter(states),
    }
