"""Source-agnostic offline enrichment, quality, deduplication, and analytics pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from it_labor_market_intelligence.analytics import analyze_records
from it_labor_market_intelligence.data_io import JsonlParseError, iter_jsonl, write_jsonl
from it_labor_market_intelligence.deduplication import deduplicate_records
from it_labor_market_intelligence.processing.companies import normalize_company
from it_labor_market_intelligence.processing.employment import normalize_employment_type
from it_labor_market_intelligence.processing.locations import normalize_location
from it_labor_market_intelligence.processing.work_modes import normalize_work_mode
from it_labor_market_intelligence.quality import profile_dataset, validate_dataset
from it_labor_market_intelligence.quality.report import write_report


def enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    """Attach Phase 2 normalizers without changing source or canonical parser payloads."""

    result = dict(record)
    raw = result.get("raw", {})
    result["enrichment"] = {
        "company": normalize_company(raw.get("company_name_raw")),
        "location": normalize_location(raw.get("location_raw")),
        "employment": normalize_employment_type(
            raw.get("employment_type_raw"), raw.get("title_raw")
        ),
        "work_mode": normalize_work_mode(None, raw.get("description_raw")),
    }
    return result


def run_pipeline(
    input_path: Path,
    output_path: Path,
    rejected_path: Path,
    quality_path: Path,
    analytics_path: Path,
    duplicates_path: Path,
    *,
    source: str | None = None,
    strict: bool = False,
    max_records: int | None = None,
    dry_run: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for record in iter_jsonl(input_path):
        if source and record.get("raw", {}).get("source") != source:
            continue
        records.append(enrich_record(record))
        if max_records is not None and len(records) >= max_records:
            break
    accepted, rejected = validate_dataset(records, reject_threshold="ERROR" if strict else "REJECT")
    duplicates = deduplicate_records(accepted)
    timestamp = generated_at or datetime.now(UTC).isoformat()
    quality = profile_dataset(
        accepted + rejected, accepted_count=len(accepted), rejected_count=len(rejected)
    )
    quality["generated_at"] = timestamp
    quality["input_record_count"] = len(records)
    analytics = analyze_records(accepted, timestamp)
    if not dry_run:
        write_jsonl(output_path, accepted)
        write_jsonl(rejected_path, rejected)
        write_report(quality_path, quality)
        write_report(analytics_path, analytics)
        write_report(duplicates_path, duplicates)
    return {
        "input": len(records),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "duplicate_clusters": duplicates["cluster_count"],
        "quality": quality,
        "analytics": analytics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the source-agnostic offline data pipeline")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rejected-output", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--analytics-report", type=Path, required=True)
    parser.add_argument("--duplicates-report", type=Path, required=True)
    parser.add_argument("--source")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    if not arguments.input.is_file():
        print(f"Input file does not exist: {arguments.input}", file=sys.stderr)
        return 2
    try:
        summary = run_pipeline(
            arguments.input,
            arguments.output,
            arguments.rejected_output,
            arguments.quality_report,
            arguments.analytics_report,
            arguments.duplicates_report,
            source=arguments.source,
            strict=arguments.strict,
            max_records=arguments.max_records,
            dry_run=arguments.dry_run,
        )
    except JsonlParseError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                key: value
                for key, value in summary.items()
                if key in {"input", "accepted", "rejected", "duplicate_clusters"}
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
