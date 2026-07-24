"""Bounded TopDev pilot runner with per-page discovery diagnostics."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from it_labor_market_intelligence.domain import NormalizedJobRecord

from .base import SourceRawJobRecord
from .topdev import (
    ADAPTER_VERSION,
    DISCOVERY_METHOD,
    PoliteCurlTransport,
    TopDevAdapter,
    _is_topdev_job_url,
    extract_job_id,
)

DEFAULT_OUTPUT = Path("datasets/processed/topdev_pilot.jsonl")
DEFAULT_REPORT = Path("reports/topdev_pilot_quality_report.json")
DEFAULT_DIAGNOSTIC = Path("reports/topdev_pilot_diagnostic.json")
PILOT_MAX_RECORDS = 30
_IT_SOURCE_CATEGORIES = {"information technology", "công nghệ thông tin"}
_TECHNICAL_SOURCE_TAG = re.compile(
    r"\b(?:python|java|javascript|golang|c#|c/c\+\+|sql|postgresql?|mysql|mongodb|"
    r"redis|linux|cloud|docker|kubernetes|fastapi|asp\.net|\.net|back-?end|devops|"
    r"database|server|network|data analytics|big data|data visualization|ui design|"
    r"ux/ui design|game developer|unity|ai|tensorflow|computer vision|infrastructure|"
    r"solution architect|it comtor)\b",
    re.IGNORECASE,
)
_NON_IT_SOURCE_TAG = re.compile(
    r"\b(?:autocad|revit|cad|marketing|content|tiktok|sales|talent acquisition|hr|"
    r"accounting|legal|law|social media|business development|business coordinator|"
    r"ngân hàng|tài chính|kiểm toán|kế toán)\b",
    re.IGNORECASE,
)
_CORROBORATED_IT_TITLE = re.compile(
    r"\b(?:data analyst|business analyst(?: it)?|product owner|technical project manager|"
    r"erp consultant|system administrator|it support|qa/qc|embedded engineer|dba|"
    r"it comtor|solution architect|cloud|data center|machine learning|ai\b|devops|"
    r"back[ -]?end|front[ -]?end|full[ -]?stack|software engineer|game developer)\b|"
    r"\b(?:giải pháp cntt|hạ tầng cntt|công nghệ thông tin|an toàn thông tin)\b",
    re.IGNORECASE,
)
_COVERAGE_FIELDS = (
    "source",
    "source_job_id",
    "source_url",
    "title_raw",
    "source_category_raw",
    "company_name_raw",
    "location_raw",
    "salary_raw",
    "skills_raw",
    "posted_at_raw",
    "expires_at_raw",
    "experience_raw",
    "employment_type_raw",
    "description_raw",
    "closed_state",
    "closed_state_provenance",
    "collected_at",
    "content_hash",
)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != () and value != []


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _is_explicit_it_category(category: str | None) -> bool:
    return category is not None and category.strip().casefold() in _IT_SOURCE_CATEGORIES


def scope_decision(
    raw: SourceRawJobRecord, normalized: NormalizedJobRecord
) -> tuple[bool, str | None]:
    """Use listing provenance plus source tags/role evidence to classify IT scope."""

    if not raw.discovery_method.startswith(DISCOVERY_METHOD):
        return False, "invalid_discovery_method"
    if raw.source_category_raw is not None and not _is_explicit_it_category(
        raw.source_category_raw
    ):
        return False, "source_category_non_it"
    source_tags = " | ".join(raw.skills_raw or ())
    has_technical_tag = bool(_TECHNICAL_SOURCE_TAG.search(source_tags))
    has_non_it_tag = bool(_NON_IT_SOURCE_TAG.search(source_tags))
    if has_non_it_tag and not has_technical_tag:
        return False, "source_tags_non_it"
    if has_technical_tag:
        return True, None
    if normalized.primary_category != "Unclassified" or normalized.skills:
        return True, None
    if _CORROBORATED_IT_TITLE.search(raw.title_raw):
        return True, None
    return False, "insufficient_it_evidence"


def is_it_scope(raw: SourceRawJobRecord, normalized: NormalizedJobRecord) -> bool:
    """Return the boolean component of the auditable scope decision."""

    return scope_decision(raw, normalized)[0]


def _initial_diagnostic(url: str, discovery_method: str) -> dict[str, Any]:
    try:
        job_id = extract_job_id(url)
    except ValueError:
        job_id = None
    return {
        "source_url": url,
        "extracted_source_job_id": job_id,
        "title_raw": None,
        "source_category_raw": None,
        "source_tags": [],
        "normalized_primary_category": None,
        "closed_state": None,
        "closed_state_provenance": None,
        "rejection_reason": None,
        "final_classification": None,
        "discovery_method": discovery_method,
    }


def _invalid_url_classification(url: str) -> str:
    path = urlparse(url).path.casefold()
    if "/companies/" in path:
        return "company page"
    if "/tim-kiem" in path or "/jobs/search" in path:
        return "category/listing page"
    return "duplicate or malformed URL"


def _quality_report(
    *,
    urls_discovered: int,
    pages_fetched: int,
    raw_records: Sequence[SourceRawJobRecord],
    normalized_records: Sequence[NormalizedJobRecord],
    diagnostics: Sequence[Mapping[str, Any]],
    failed_records: int,
    duplicate_records: int,
    runtime_seconds: float,
    run_started_at: datetime,
) -> dict[str, Any]:
    successful = len(raw_records)
    coverage_counts = {
        name: sum(_present(getattr(record, name)) for record in raw_records)
        for name in _COVERAGE_FIELDS
    }
    field_coverage = {
        name: {"count": count, "rate": _ratio(count, successful)}
        for name, count in coverage_counts.items()
    }
    null_rates = {
        name: _ratio(successful - count, successful) for name, count in coverage_counts.items()
    }
    salary_candidates = [
        normalized
        for raw, normalized in zip(raw_records, normalized_records, strict=True)
        if raw.salary_raw is not None
    ]
    salary_successes = sum(
        normalized.salary.confidence > 0
        and (normalized.salary.disclosed or normalized.salary.salary_type == "negotiable")
        for normalized in salary_candidates
    )
    experience_candidates = [
        normalized
        for raw, normalized in zip(raw_records, normalized_records, strict=True)
        if raw.experience_raw is not None
    ]
    experience_successes = sum(
        normalized.experience.confidence > 0 for normalized in experience_candidates
    )
    skill_successes = sum(bool(normalized.skills) for normalized in normalized_records)
    classifications = Counter(item["final_classification"] for item in diagnostics)
    rejection_reasons = Counter(
        str(item["rejection_reason"])
        for item in diagnostics
        if item["rejection_reason"] is not None
    )
    invalid_page_types = sum(
        classifications[classification]
        for classification in (
            "company page",
            "category/listing page",
            "duplicate or malformed URL",
        )
    )
    non_it = classifications["non-IT job"]
    incorrectly_rejected = classifications["IT job incorrectly rejected"]
    rejected = non_it + incorrectly_rejected + invalid_page_types
    return {
        "source": "topdev",
        "pilot_limit": PILOT_MAX_RECORDS,
        "urls_discovered": urls_discovered,
        "discovered_job_detail_urls": sum(
            _is_topdev_job_url(str(item["source_url"])) for item in diagnostics
        ),
        "pages_fetched": pages_fetched,
        "successful_records": successful,
        "it_records_accepted": successful,
        "real_non_it_records_rejected": non_it,
        "it_records_incorrectly_rejected": incorrectly_rejected,
        "invalid_page_types": invalid_page_types,
        "failed_records": failed_records,
        "duplicate_records": duplicate_records,
        "rejected_records": rejected,
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "field_coverage": field_coverage,
        "null_rates": null_rates,
        "salary_parsing_success": {
            "eligible_records": len(salary_candidates),
            "successful_records": salary_successes,
            "rate": _ratio(salary_successes, len(salary_candidates)),
        },
        "experience_parsing_success": {
            "eligible_records": len(experience_candidates),
            "successful_records": experience_successes,
            "rate": _ratio(experience_successes, len(experience_candidates)),
        },
        "skill_extraction_coverage": {
            "records_with_matches": skill_successes,
            "rate": _ratio(skill_successes, successful),
        },
        "closed_state_counts": {
            state: sum(record.closed_state == state for record in raw_records)
            for state in ("ACTIVE", "EXPIRED", "CLOSED", "UNKNOWN")
        },
        "active_job_count": sum(record.closed_state == "ACTIVE" for record in raw_records),
        "expired_job_count": sum(record.closed_state == "EXPIRED" for record in raw_records),
        "closed_job_count": sum(record.closed_state == "CLOSED" for record in raw_records),
        "unknown_state_job_count": sum(record.closed_state == "UNKNOWN" for record in raw_records),
        "adapter_version": ADAPTER_VERSION,
        "run_started_at": run_started_at.isoformat(),
        "runtime_seconds": round(runtime_seconds, 3),
    }


def run_pilot(
    adapter: TopDevAdapter,
    *,
    limit: int = PILOT_MAX_RECORDS,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    diagnostic_path: Path = DEFAULT_DIAGNOSTIC,
) -> dict[str, Any]:
    """Run a maximum-30 pilot and write normalized data plus technical diagnostics."""

    if not 1 <= limit <= PILOT_MAX_RECORDS:
        raise ValueError("Pilot limit must be between 1 and 30")
    started_at = datetime.now(UTC)
    started_clock = time.monotonic()
    urls = adapter.discover_job_urls(limit=limit)
    pages_fetched = 0
    failed = 0
    duplicates = 0
    seen_ids: set[str] = set()
    raw_records: list[SourceRawJobRecord] = []
    normalized_records: list[NormalizedJobRecord] = []
    diagnostics: list[dict[str, Any]] = []

    for url in urls[:limit]:
        diagnostic = _initial_diagnostic(url, adapter.discovery_method_for(url))
        diagnostics.append(diagnostic)
        if not _is_topdev_job_url(url):
            diagnostic["rejection_reason"] = "invalid_url_type"
            diagnostic["final_classification"] = _invalid_url_classification(url)
            continue
        pages_fetched += 1
        try:
            page = adapter.fetch_job_detail(url)
        except (OSError, TimeoutError):
            failed += 1
            diagnostic["rejection_reason"] = "fetch_error"
            diagnostic["final_classification"] = "duplicate or malformed URL"
            continue
        if page.status != 200:
            failed += 1
            diagnostic["rejection_reason"] = f"http_{page.status}"
            diagnostic["final_classification"] = "duplicate or malformed URL"
            continue
        if not _is_topdev_job_url(page.url):
            diagnostic["rejection_reason"] = "redirected_to_invalid_page_type"
            diagnostic["final_classification"] = _invalid_url_classification(page.url)
            continue
        try:
            raw = adapter.extract_raw_record(page)
            diagnostic["extracted_source_job_id"] = raw.source_job_id
            diagnostic["title_raw"] = raw.title_raw
            diagnostic["source_category_raw"] = raw.source_category_raw
            diagnostic["source_tags"] = list(raw.skills_raw or ())
            diagnostic["closed_state"] = raw.closed_state
            diagnostic["closed_state_provenance"] = _jsonable(raw.closed_state_provenance)
            if raw.source_job_id in seen_ids:
                duplicates += 1
                diagnostic["rejection_reason"] = "duplicate_source_job_id"
                diagnostic["final_classification"] = "duplicate or malformed URL"
                continue
            seen_ids.add(raw.source_job_id)
            normalized = adapter.normalize_record(raw)
            diagnostic["normalized_primary_category"] = normalized.primary_category
        except (TypeError, ValueError):
            diagnostic["rejection_reason"] = "invalid_or_unextractable_job_page"
            diagnostic["final_classification"] = "duplicate or malformed URL"
            continue

        accepted, rejection_reason = scope_decision(raw, normalized)
        if accepted:
            diagnostic["final_classification"] = "valid job-detail page"
            raw_records.append(raw)
            normalized_records.append(normalized)
        else:
            diagnostic["rejection_reason"] = rejection_reason
            diagnostic["final_classification"] = "non-IT job"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for raw, normalized in zip(raw_records, normalized_records, strict=True):
            payload = {"raw": _jsonable(raw), "normalized": _jsonable(normalized)}
            output_file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_path.write_text(
        json.dumps(
            {
                "source": "topdev",
                "description_fields_retained": False,
                "pages": diagnostics,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    report = _quality_report(
        urls_discovered=len(urls),
        pages_fetched=pages_fetched,
        raw_records=raw_records,
        normalized_records=normalized_records,
        diagnostics=diagnostics,
        failed_records=failed,
        duplicate_records=duplicates,
        runtime_seconds=time.monotonic() - started_clock,
        run_started_at=started_at,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded TopDev public-job pilot")
    parser.add_argument("--limit", type=int, default=PILOT_MAX_RECORDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--diagnostic", type=Path, default=DEFAULT_DIAGNOSTIC)
    parser.add_argument("--transport", choices=("urllib", "curl"), default="urllib")
    arguments = parser.parse_args()
    transport = PoliteCurlTransport() if arguments.transport == "curl" else None
    report = run_pilot(
        TopDevAdapter(transport),
        limit=arguments.limit,
        output_path=arguments.output,
        report_path=arguments.report,
        diagnostic_path=arguments.diagnostic,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
