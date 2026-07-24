# Offline Data Quality Pipeline

The offline pipeline accepts canonical JSONL records in the existing `{raw, normalized}` shape. It adds an `enrichment` object for company, location, employment type, and work mode; it does not alter the source adapter payload.

It then validates records, keeps accepted and rejected JSONL outputs separate, detects duplicates without deleting records, profiles the input, and produces descriptive analytics. JSONL is UTF-8, object-per-line, streaming on read, and atomically written.

Run:

```powershell
$env:PYTHONPATH='src;.venv\Lib\site-packages'
.\.uv-python\cpython-3.12.13-windows-x86_64-none\python.exe -m it_labor_market_intelligence.cli.offline_pipeline --input datasets/processed/topdev_pilot.jsonl --output datasets/processed/topdev_analysis_ready.jsonl --rejected-output datasets/processed/topdev_rejected.jsonl --quality-report reports/topdev_data_quality_v2.json --analytics-report reports/topdev_pilot_analytics.json --duplicates-report reports/topdev_duplicates.json
```

The CLI has no network code. `--dry-run` evaluates the same flow without writing. Invalid JSONL or missing input returns exit code 2.

Validation issues use `INFO`, `WARNING`, `ERROR`, and `REJECT`. Identity and malformed URL failures are reject-level. Salary, experience, date, status, and skill consistency are independently reported. Null remains distinct from an empty string and from an explicit zero.

Future adapters only need to emit the canonical raw and normalized payload; no adapter-specific logic is required in this pipeline.
