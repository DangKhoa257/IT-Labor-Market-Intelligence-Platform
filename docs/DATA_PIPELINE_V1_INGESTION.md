# Data Pipeline V1 Ingestion

## Scope

Data Pipeline V1 implements a production-shaped ingestion evidence worker for one approved source,
TopDev. It begins with source and policy resolution and stops after
`ingestion.extracted_records`. It does not import canonical records or write to `core`, `history`,
`quality`, `analytics`, `serving`, or `api`.

The implementation is source-independent below the adapter boundary:

```text
TopDevAdapter
    -> IngestionRunner
    -> PostgreSQLRunnerStore (short units of work)
    -> Database V1 ingestion schema
```

`TopDevAdapter` owns TopDev URL validation, curated IT-listing discovery, public GET behavior,
JSON-LD extraction, contact redaction, source-scope evidence, and closed-state detection. The generic
runner owns run/task lifecycle, retries, raw hashing, persistence, idempotency, counters, and safe
errors. The adapter does not receive a SQLAlchemy session, and the runner contains no TopDev selector
or JSON-LD mapping.

## Database lineage

Every persisted result is traceable through Database V1:

```text
ingestion.sources
  -> ingestion.source_policies
  -> ingestion.parser_versions
  -> ingestion.crawl_runs
       -> ingestion.crawl_tasks
            -> ingestion.fetch_events
                 -> ingestion.raw_objects (when storage is allowed and available)
                 -> ingestion.extraction_runs
                      -> ingestion.extracted_records
       -> ingestion.crawl_errors
```

Source-consistency checks prevent the runner from combining a run, task, fetch, parser, extracted
record, or error from different sources. The database IDs, source URL, source job ID, collection
time, parser/schema version, response hash, and direct-payload hash preserve evidence lineage.

## Bootstrap, policy, and parser identity

`bootstrap-topdev` idempotently registers:

- source slug `topdev`, disabled on first registration and thereafter preserving existing
  enablement unless `--enable` is explicitly requested;
- an unreviewed `topdev-policy-v1` only when no reviewed policy exists;
- parser `TopDevAdapter`, version `topdev.v1`, schema
  `source-raw-job-record.v1`;
- a deterministic SHA-256 of behavior-affecting parser configuration;
- the current Git commit SHA when it can be read safely.

Reviewed policies are never rewritten by bootstrap. Enabling performs a separate check for a
currently valid policy whose robots and terms statuses are both `approved`. Rerunning bootstrap
without `--enable` does not disable an already-enabled source.

Parser version, schema version, configuration hash, and original Git commit form immutable parser
provenance. An identical semantic identity is reused without metadata updates. Reusing a version
with a changed schema or configuration is rejected and requires an `ADAPTER_VERSION` increment. A
new row is inserted successfully before the previous active row is retired. The crawl run retains
its own build commit separately in `crawl_runs.git_commit_sha`.

## Fixture and live modes

Fixture mode is the default. It maps production-valid TopDev URLs to repository-relative HTML
fixtures using `FixtureTransport`; a missing mapping fails instead of falling back to the network.
A disabled or unapproved source can be exercised only with `--trigger test`.

Live mode is opt-in with `--mode live`. It requires both an enabled source and a currently approved
policy. Blocked paths override approved paths, and discovery plus every detail request is checked
before transport work. A policy wrapper enforces the total request count and maximum concurrency,
while the resolved policy interval is passed to the TopDev transport even when greater than two
seconds. The transport remains bounded to public GET requests, limited redirects, and no login,
CAPTCHA bypass, proxy rotation, or 403 retry. Nothing schedules live mode automatically.

## Run and task lifecycle

A new run is persisted before discovery. One discovery task is created, followed by at most the
requested number of deterministic detail tasks. Duplicate URLs and duplicate source job IDs are
discarded before insert, and database uniqueness makes repeated planning idempotent.

Detail claims use one PostgreSQL statement with `FOR UPDATE SKIP LOCKED`. The claim increments the
attempt number and commits before adapter fetch work begins. Two workers therefore cannot claim the
same attempt.

The transaction boundaries are intentionally short:

```text
create/start run and discovery task -> commit
discovery or HTTP work              -> no database transaction
plan tasks                           -> commit
claim one task                       -> commit
fetch or retry timing                -> no database transaction
persist fetch/raw evidence           -> commit
parse direct evidence                -> no database transaction
persist extraction/record/error      -> commit
lock and finalize run from SQL data  -> commit
```

No network call, rate-limit delay, or parser execution occurs while a row lock is held.

## Fetch attempts and retries

Every actual transport attempt creates one `ingestion.fetch_events` row, including discovery,
timeouts, and HTTP failures. Request/response headers pass through a fixed allowlist; authorization,
cookies, tokens, unknown headers, and raw bodies are not persisted or printed.

Live and fixture responses carry the same safe response metadata contract. `Content-Type`,
`Content-Length`, `ETag`, `Last-Modified`, `Cache-Control`, `Retry-After`, and `Date` may be
persisted. Cookie, Set-Cookie, authorization, CSRF, session, and unknown headers are discarded.

Default detail retry behavior is:

- attempt 1 retry: scheduled after 5 seconds;
- attempt 2 retry: scheduled after 30 seconds;
- attempt 3 failure: exhausted;
- a positive `Retry-After` or HTTP-date is accepted only when it resolves to at most 300 seconds.

Timeouts, connection failures, HTTP 408, 425, 429, 500, 502, 503, and 504 are retryable. Invalid
URLs, HTTP 400, 401, 403, 404, and 410, blocked access, invalid JobPosting JSON-LD, missing required
evidence, scope rejection, and schema rejection are not retried. Tests inject immediate scheduling;
production code never sleeps inside a test or transaction.

`retry-run` resumes due tasks only for an existing `running` crawl run. It does not reopen a
terminal run. It reconstructs behavior from the immutable policy snapshot in
`crawl_runs.configuration_json`, not current mutable limits or retention values. Live continuation
also rechecks current enablement, approval, and newly blocked paths and rejects unauthorized
continuation. `requeue-stale` changes stale `running` tasks to `pending` when attempts remain and to
`failed` when exhausted. Terminal runs are excluded from recovery.

A fetch failure never marks a posting inactive.

## Raw evidence decisions

The SHA-256 is calculated over exact response bytes and stored as 64 lowercase hexadecimal
characters. `raw_objects.sha256` is globally unique; an atomic PostgreSQL upsert makes concurrent
identical bodies share one row. A changed byte sequence creates new evidence.

For identical bytes and byte size, the first valid storage location is preserved and retention can
only become safer: a later expiry extends it, a shorter expiry cannot reduce it, and null expiry
means indefinite retention. A same SHA-256 with a different byte size is rejected. These rules are
applied atomically under concurrent upserts.

Storage decisions are explicit:

- **fixture:** Database V1 uses `storage_provider=filesystem` with a repository-relative fixture
  identifier; absolute local paths are rejected;
- **inline:** structured JSON no larger than 256 KiB may use `inline_payload_json` when policy
  permits;
- **suppressed:** no raw-object row is created when policy disallows storage or safe live object
  storage is unavailable; the fetch event remains;
- **external:** repository contracts support Database V1 external providers and metadata, but this
  phase does not provision or configure an object store.

Full HTML is never placed in JSONB. `expires_at` is `fetched_at + raw_retention_days`; unknown
retention remains null. Retention metadata does not delete or archive anything.

When description storage is disabled, extraction may inspect the description in memory, but the
persisted direct payload contains `description_raw=null` and
`description_storage_suppressed=true`. It is not replaced with a summary.

## Extraction and hashing

Each successful detail fetch reaching the parser receives one idempotent `extraction_runs` row for
the fetch/parser pair. A TopDev page emits at most one accepted or rejected extracted record.
Rejected records retain run, fetch, raw, parser, source, URL, source-job, and sanitized reason
lineage.

The `direct-payload-json.v1` hash contract is:

- UTF-8 JSON;
- sorted object keys;
- separators without insignificant whitespace;
- timezone-aware datetimes rendered with stable ISO 8601 values;
- list order preserved;
- SHA-256 over those canonical bytes, never Python `repr()`.

Later successful evidence with the same source identity and raw-object hash increments
`unchanged_count`. A changed response does not.

## Errors, output, and counters

Persisted crawl errors use bounded Database V1 stages/categories and a 2,000-character sanitized
message. Details contain only safe values such as attempt, delay, status, byte count, or parser
version. Credentials, database URLs, cookies, tokens, raw bodies, stack traces, and local absolute
paths are excluded. CLI output is deterministic compact JSON and never prints `DATABASE_URL`.

Terminal finalization locks the run and derives counters from persisted children:

- unique persisted detail tasks -> `discovered_count`;
- all discovery/detail tasks -> `task_count`;
- fetch outcomes -> success/failure counts;
- prior identical source evidence -> `unchanged_count`;
- persisted records and statuses -> extracted/accepted/rejected counts;
- persisted crawl errors -> `error_count`.

Terminal status is `succeeded` when at least one detail task succeeds and none fail,
`partially_succeeded` when successes and failures coexist, and `failed` when no detail task
succeeds. The worker never infers cancellation, and this phase includes no cancellation command.

## CLI summary

```powershell
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev --enable
python -m it_labor_market_intelligence.ingestion.cli run --source topdev --mode fixture --trigger test --limit 4 --fixture-dir tests/fixtures/topdev
python -m it_labor_market_intelligence.ingestion.cli run --source topdev --mode fixture --trigger test --limit 4 --fixture-dir tests/fixtures/topdev --dry-run
python -m it_labor_market_intelligence.ingestion.cli run --source topdev --mode live --trigger manual --limit 10
python -m it_labor_market_intelligence.ingestion.cli retry-run --run-id <uuid> --fixture-dir tests/fixtures/topdev
python -m it_labor_market_intelligence.ingestion.cli inspect-run --run-id <uuid>
python -m it_labor_market_intelligence.ingestion.cli requeue-stale --older-than-seconds 300
```

Exit codes are 0 succeeded, 2 partially succeeded or waiting for a scheduled retry, 3 policy or
configuration rejection, 4 all detail tasks failed, and 5 unexpected internal failure.

## Known limitations

- Only TopDev is registered; there is no second source adapter.
- There is no scheduler, queue, distributed coordinator, or automatic live crawling.
- Object storage and retention deletion/archive execution are not provisioned.
- `retry-run` resumes running runs; it does not reopen terminal runs.
- No LLM extraction, embeddings, proxy rotation, login, or CAPTCHA handling exists.
- This phase stops at `ingestion.extracted_records`; canonical/core import, history observation,
  quality evidence, analytics refresh, serving refresh, and API/dashboard population remain separate
  future work.
