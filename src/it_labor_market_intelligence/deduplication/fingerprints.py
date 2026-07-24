"""Stable fingerprints for offline duplicate comparison."""

from __future__ import annotations

import hashlib
from typing import Any

from it_labor_market_intelligence.processing.text import comparison_key, tokenize


def identity_key(record: dict[str, Any]) -> tuple[str | None, str | None]:
    raw = record.get("raw", {})
    return raw.get("source"), raw.get("source_job_id")


def canonical_url(record: dict[str, Any]) -> str | None:
    value = record.get("raw", {}).get("source_url")
    return comparison_key(value)


def content_hash(record: dict[str, Any]) -> str | None:
    value = record.get("raw", {}).get("content_hash")
    return str(value) if value else None


def probable_fingerprint(record: dict[str, Any]) -> dict[str, Any]:
    raw, normalized, enrichment = (
        record.get("raw", {}),
        record.get("normalized", {}),
        record.get("enrichment", {}),
    )
    return {
        "company": enrichment.get("company", {}).get("company_comparison_key")
        or comparison_key(raw.get("company_name_raw")),
        "title_tokens": tokenize(normalized.get("title_normalized") or raw.get("title_raw")),
        "city": enrichment.get("location", {}).get("city"),
        "employment_type": enrichment.get("employment", {}).get("employment_type"),
        "skills": tuple(
            sorted(
                match.get("canonical_name")
                for match in normalized.get("skills", [])
                if isinstance(match, dict) and match.get("canonical_name")
            )
        ),
        "salary": (
            normalized.get("salary", {}).get("minimum"),
            normalized.get("salary", {}).get("maximum"),
            normalized.get("salary", {}).get("currency"),
        ),
    }


def fingerprint_key(record: dict[str, Any]) -> str:
    fingerprint = probable_fingerprint(record)
    return hashlib.sha256(repr(sorted(fingerprint.items())).encode()).hexdigest()
