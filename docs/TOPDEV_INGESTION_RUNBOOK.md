# TopDev Ingestion Runbook

This runbook operates the bounded Data Pipeline V1 ingestion worker. Fixture mode is the default and
is the required mode for development, tests, and CI. Live TopDev access is a manual, opt-in action;
there is no scheduler or automatic live crawler.

## Safety rules

- Use repository fixtures unless a reviewed policy explicitly authorizes a live run.
- Never bypass login, CAPTCHA, robots, terms, HTTP 403, or other access controls.
- Never print `DATABASE_URL`, credentials, cookies, authorization headers, or response bodies.
- A failed fetch does not close a posting.
- The worker stops at `ingestion.extracted_records`; it does not populate downstream schemas.

## Prepare the database

Start PostgreSQL, apply Database V1, and verify its security baseline:

```powershell
docker compose up -d db
alembic upgrade head
alembic current
psql $env:DATABASE_URL -c "SELECT operations.assert_security_baseline_v1();"
```

The expected head is Migration 007 (`20260728_0007`). This ingestion worker adds no Migration 008.

## Bootstrap TopDev

Register the source, policy template, and parser version without enabling live access:

```powershell
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev
```

Bootstrap is idempotent. It leaves the source disabled unless `--enable` is supplied, does not
overwrite a reviewed policy, and safely rotates the active parser only when registering a distinct
version. Parser identity includes its version, schema version, deterministic configuration hash,
and Git commit SHA when available.

Review policy state directly before enabling:

```sql
SELECT s.slug, s.is_enabled, p.policy_version, p.is_current,
       p.robots_status, p.terms_status, p.reviewed_at,
       p.max_requests_per_run, p.raw_retention_days
FROM ingestion.sources AS s
LEFT JOIN ingestion.source_policies AS p ON p.source_id = s.id
WHERE s.slug = 'topdev'
ORDER BY p.created_at DESC;
```

After an authorized reviewer marks the current policy approved, enable explicitly:

```powershell
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev --enable
```

Enablement is rejected unless the current policy is valid and both robots and terms statuses are
`approved`. Running bootstrap later without `--enable` disables the source again by design.

## Validate and run fixtures

Preview validation and fixture discovery without ingestion writes:

```powershell
python -m it_labor_market_intelligence.ingestion.cli run --source topdev --mode fixture --trigger test --limit 4 --fixture-dir tests/fixtures/topdev --dry-run
```

Run deterministic fixture ingestion:

```powershell
python -m it_labor_market_intelligence.ingestion.cli run --source topdev --mode fixture --trigger test --limit 4 --fixture-dir tests/fixtures/topdev
```

Fixture URLs must have an explicit repository-relative mapping. A missing fixture fails closed and
never falls back to network access.

## Optional manual live run

Only after source enablement and policy approval:

```powershell
python -m it_labor_market_intelligence.ingestion.cli run --source topdev --mode live --trigger manual --limit 10
```

The limit must be from 1 through the active policy maximum. Live mode uses public GET requests and
the adapter rate limit. It has no object-storage backend, proxy rotation, login, or CAPTCHA bypass,
and HTTP 403 is not retried.

## Inspect a run

```powershell
python -m it_labor_market_intelligence.ingestion.cli inspect-run --run-id <uuid>
```

The command emits a deterministic JSON summary containing identifiers, state, safe counters, and
timestamps. It omits raw bodies, sensitive headers, error internals, and database credentials.

For database triage, inspect lineage without selecting raw payloads:

```sql
SELECT id, source_id, status, discovered_count, task_count,
       fetch_success_count, fetch_failure_count, extracted_count,
       accepted_count, rejected_count, unchanged_count, error_count
FROM ingestion.crawl_runs
WHERE id = '<run-uuid>';

SELECT id, task_type, status, attempt_count, next_attempt_at
FROM ingestion.crawl_tasks
WHERE crawl_run_id = '<run-uuid>'
ORDER BY task_type, canonical_url;

SELECT task_id, attempt_number, outcome, http_status, raw_object_id, fetched_at
FROM ingestion.fetch_events
WHERE crawl_run_id = '<run-uuid>'
ORDER BY fetched_at, attempt_number;
```

## Retry and recovery

Resume due retry tasks in an existing running run:

```powershell
python -m it_labor_market_intelligence.ingestion.cli retry-run --run-id <uuid> --fixture-dir tests/fixtures/topdev
```

Default retry delays are 5 seconds and 30 seconds, with at most three actual attempts. Timeouts,
connection errors, HTTP 408, 425, 429, 500, 502, 503, and 504 are retryable. Invalid URLs, HTTP 400,
401, 403, 404, 410, access blocking, parsing failures, and evidence/schema rejection are not.
`Retry-After` is honored only up to 300 seconds.

Recover tasks whose worker lease became stale:

```powershell
python -m it_labor_market_intelligence.ingestion.cli requeue-stale --older-than-seconds 300
```

Stale running tasks are returned to pending only while attempts remain; exhausted tasks become
failed. Terminal crawl runs are never changed by recovery.

## Disable live access

Bootstrap without the enable flag to return the source to its safe default:

```powershell
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev
```

Confirm `ingestion.sources.is_enabled` is false before closing the change record. This does not
rewrite reviewed policies or delete prior evidence.

## Failure triage

- Exit `2`: inspect the run; it is either partially successful or has a future `next_attempt_at`.
- Exit `3`: check source slug, limit, fixture directory, source enablement, and current policy review.
- Exit `4`: inspect task outcomes and sanitized `crawl_errors`; all detail tasks failed.
- Exit `5`: capture the safe error and run ID, then inspect PostgreSQL health without copying raw
  payloads or credentials into a ticket.
- HTTP 429 or a timeout can be resumed with `retry-run` after its scheduled time. HTTP 403 must be
  treated as a terminal access decision, not retried or bypassed.
- A rejected record indicates parser/evidence validation, while a missing raw-object link can be an
  intentional policy or storage-safety suppression. Neither condition authorizes downstream import.

## Exit codes

- `0`: succeeded, inspected, bootstrapped, or recovery completed;
- `2`: partially succeeded or waiting for a scheduled retry;
- `3`: invalid configuration, policy rejection, disabled live source, or invalid limit;
- `4`: all detail tasks failed;
- `5`: unexpected internal failure reported with a sanitized message.

## Known limitations

There is no scheduler, distributed queue, automatic live crawling, provisioned object storage, or
retention deletion worker. The ingestion result remains source evidence only. Canonical/core import,
history, quality, analytics, serving, and API population are outside this phase.
