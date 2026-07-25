"""Import analysis-ready JSONL into the relational database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from it_labor_market_intelligence.data_io import JsonlParseError
from it_labor_market_intelligence.database.models import Base
from it_labor_market_intelligence.database.services import DatasetImporter, DuplicateReportImporter
from it_labor_market_intelligence.database.session import create_database_engine, session_factory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--source")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--duplicates-report", type=Path)
    args = parser.parse_args()
    if not args.input.is_file() or args.batch_size < 1:
        print("Invalid input path or batch size", file=sys.stderr)
        return 2
    engine = create_database_engine(args.database_url)
    Base.metadata.create_all(engine)
    try:
        with session_factory(engine)() as session:
            counts = DatasetImporter(session).import_path(
                args.input,
                source_name=args.source,
                replace_existing=args.replace_existing,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
            if args.duplicates_report is not None:
                if not args.duplicates_report.is_file():
                    raise ValueError(f"Duplicate report does not exist: {args.duplicates_report}")
                duplicate_counts = DuplicateReportImporter(session).import_path(
                    args.duplicates_report, dry_run=args.dry_run
                )
                counts.update(
                    {f"duplicate_clusters_{key}": value for key, value in duplicate_counts.items()}
                )
    except (JsonlParseError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
