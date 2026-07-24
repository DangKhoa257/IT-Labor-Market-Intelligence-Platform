# TopDev Pilot Runbook

## Prerequisites

- Python 3.12 or 3.13 with the project installed, or `PYTHONPATH=src`.
- Network access to public TopDev sitemap/detail URLs.
- No database, browser session, credentials, proxy, CAPTCHA tooling, or scheduler is required.

Run tests before a live pilot:

```powershell
python -m pytest
```

## Pilot command

From the repository root, the explicit command for the maximum-30 pilot is:

```powershell
$env:PYTHONPATH="src"; python -m it_labor_market_intelligence.adapters.topdev_pilot --limit 30 --transport curl
```

The runner refuses limits below 1 or above 30. `--transport urllib` is also available when the local
Python runtime has a working HTTPS backend; both transports use identical request identity, timing,
redirect, and stop constraints.

## Expected artifacts

- `datasets/processed/topdev_pilot.jsonl`
- `reports/topdev_pilot_quality_report.json`

The quality report records discovered URLs, attempted page fetches, successful/failed/duplicate/
rejected records, per-field coverage and null rates, salary and experience parse success, skill
coverage, active/expired/unknown counts, adapter version, start time, and runtime.

## Validation checklist

1. Confirm `successful_records <= 30` and equals the JSONL line count.
2. Confirm `pages_fetched <= urls_discovered <= 30`.
3. Review failures/rejections before interpreting coverage. The curated IT listing may contain
   adjacent roles; inspect grouped `source_tags_non_it` and `insufficient_it_evidence` reasons.
4. Confirm every `raw.source_job_id` equals the numeric suffix in `raw.source_url`.
5. Confirm negotiable salaries have null numeric bounds and no inferred currency/type.
6. Confirm missing experience is null, while explicit month requirements normalize correctly.
7. Confirm `employment_type_raw=OTHER` is not presented as a meaningful canonical type.
8. Inspect field null rates and parsing/skill coverage in the quality report.
9. Treat the pilot as a bounded technical dataset, not production analytics.

## Stop conditions

Stop the run and investigate normally if the sitemap or pages return HTTP 403, CAPTCHA/challenge
content, repeated non-200 responses, or a changed payload without JSON-LD `JobPosting`. Do not alter
headers to impersonate a browser, retry around access control, use another IP, or add bypass logic.
The runner performs no such actions automatically.
