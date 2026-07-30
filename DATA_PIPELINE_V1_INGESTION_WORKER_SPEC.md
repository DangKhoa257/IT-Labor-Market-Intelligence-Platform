# Data Pipeline V1 — TopDev Ingestion Worker Specification

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`
**Runtime:** Python 3.12+, PostgreSQL 16, SQLAlchemy 2.x, psycopg 3, httpx
**Database prerequisite:** Database V1 Migrations 001–007 merged
**Status:** Implementation-ready
**Scope:** one bounded TopDev adapter from discovery through immutable ingestion evidence

---

## 1. Goal

Implement the first production-shaped ingestion worker using the existing
`TopDevAdapter` and Database V1 ingestion schema.

Required lineage:

```text
ingestion.sources
→ ingestion.source_policies
→ ingestion.parser_versions
→ ingestion.crawl_runs
→ ingestion.crawl_tasks
→ ingestion.fetch_events
→ ingestion.raw_objects
→ ingestion.extraction_runs
→ ingestion.extracted_records
→ ingestion.crawl_errors
```

The worker must:

- reuse the existing TopDev discovery/extraction behavior;
- persist successful and failed attempts with source-consistent lineage;
- enforce approved source policy limits;
- remain idempotent across retries and reruns;
- deduplicate raw evidence by exact-byte SHA-256;
- persist parser and record-schema versions;
- sanitize headers, logs, and errors;
- provide deterministic fixture-mode PostgreSQL tests;
- expose live mode only through explicit operator opt-in;
- stop at `ingestion.extracted_records`.

Do not write to `core`, `history`, `quality`, `analytics`, `serving`, or `api`.

---

## 2. Existing components to reuse

Read and preserve behavior from:

```text
src/it_labor_market_intelligence/adapters/topdev.py
src/it_labor_market_intelligence/adapters/topdev_pilot.py
docs/TOPDEV_ADAPTER.md
tests/unit/test_topdev_adapter.py
tests/unit/test_topdev_pilot.py
```

The adapter already owns:

```text
bounded discovery
TopDev URL validation
public GET fetch behavior
JSON-LD JobPosting extraction
contact redaction
source-scope classification
closed-state evidence
```

This PR adds orchestration and persistence. It must not rewrite the scraper.

---

## 3. Architecture boundary

```text
TopDevAdapter
→ generic ingestion runner
→ repositories/unit of work
→ Database V1 ingestion tables
```

TopDev-specific code owns only:

```text
discovery
URL validation
fetch rules
source extraction
closed-state detection
```

Generic ingestion code owns:

```text
source/policy/parser resolution
run and task lifecycle
claiming and recovery
retry classification
raw hashing and storage decisions
database writes
idempotency
metrics
sanitization
CLI
```

Do not put SQLAlchemy sessions inside `TopDevAdapter`. Do not put TopDev selectors,
host names, or JSON-LD mappings in the generic runner.

---

## 4. Required code inventory

Suggested layout:

```text
src/it_labor_market_intelligence/ingestion/
    __init__.py
    contracts.py
    errors.py
    sanitization.py
    hashing.py
    repositories.py
    raw_storage.py
    runner.py
    cli.py

src/it_labor_market_intelligence/ingestion/adapters/
    __init__.py
    topdev_registration.py
```

Tests:

```text
tests/unit/ingestion/test_sanitization.py
tests/unit/ingestion/test_hashing.py
tests/unit/ingestion/test_retry_policy.py
tests/unit/ingestion/test_runner.py
tests/integration/ingestion/test_topdev_ingestion_postgresql.py
tests/integration/ingestion/test_topdev_ingestion_concurrency.py
```

Fixtures:

```text
tests/fixtures/topdev/discovery_page_1.html
tests/fixtures/topdev/job_active.html
tests/fixtures/topdev/job_expired.html
tests/fixtures/topdev/job_invalid.html
tests/fixtures/topdev/job_negotiable_salary.html
```

Docs:

```text
docs/DATA_PIPELINE_V1_INGESTION.md
docs/TOPDEV_INGESTION_RUNBOOK.md
```

Update `README.md`, `docs/ARCHITECTURE.md`, `docs/TOPDEV_ADAPTER.md`, and
`docs/DATA_IMPORT_RUNBOOK.md`.

---

## 5. No database migration by default

Use the existing Database V1 schema. Do not add Migration 008 for convenience.

A new migration is allowed only when an existing constraint makes a correct,
race-safe worker impossible. Any such migration must be narrow, explained,
backward-compatible, and PostgreSQL-tested.

---

## 6. TopDev bootstrap

Provide an idempotent command:

```text
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev
```

### `ingestion.sources`

Required identity:

```text
slug = topdev
display_name = TopDev
base_url = https://topdev.vn
source_type = job_board
country_code = VN
```

The source is disabled when first registered. Later idempotent bootstrap runs
without `--enable` preserve existing enablement; bootstrap is registration, not
an implicit disable operation. `--enable` still requires a currently valid
approved policy.

### `ingestion.source_policies`

Bootstrap only when no reviewed policy exists. Suggested test/pilot values:

```text
policy_version = topdev-policy-v1
minimum_request_interval_seconds = 2.000
maximum_requests_per_run = 30
maximum_concurrent_requests = 1
raw_retention_days = 30
description_retention_days = 90
allow_raw_storage = true
allow_description_storage = true
```

Do not silently mark robots or terms review approved. Tests must explicitly seed
approved policy fixtures.

### `ingestion.parser_versions`

Register:

```text
parser_name = TopDevAdapter
version = topdev.v1
schema_version = source-raw-job-record.v1
```

Include git commit SHA when available and a deterministic configuration hash.
Only one parser version per source may be active by application behavior.

Parser identity is immutable. Reusing a version is allowed only when its schema
version and configuration hash are identical, and must not rewrite the original
Git commit. A semantic or configuration change requires incrementing
`ADAPTER_VERSION`. Insert a new version before retiring the previous active row.

---

## 7. CLI contract

Provide:

```text
python -m it_labor_market_intelligence.ingestion.cli bootstrap-topdev
python -m it_labor_market_intelligence.ingestion.cli run --source topdev
python -m it_labor_market_intelligence.ingestion.cli retry-run --run-id <uuid>
python -m it_labor_market_intelligence.ingestion.cli inspect-run --run-id <uuid>
python -m it_labor_market_intelligence.ingestion.cli requeue-stale --older-than-seconds <n>
```

`run` options:

```text
--source topdev
--limit <1..30>
--mode fixture|live
--trigger manual|scheduled|backfill|test
--fixture-dir <path>
--fail-fast
--dry-run
```

Defaults:

```text
mode = fixture
trigger = manual
limit = min(10, active policy maximum)
fail_fast = false
dry_run = false
```

Live mode requires an enabled source and approved current policy. Fixture mode
may use a disabled source only with `trigger=test`.

Dry-run may resolve configuration and print a deterministic plan, but must not
insert run/task/evidence rows.

Exit codes:

```text
0 = succeeded
2 = partially succeeded
3 = policy/configuration rejected
4 = all tasks failed
5 = unexpected internal failure
```

Never print credentials, cookies, authorization headers, raw bodies, or the
`DATABASE_URL`.

---

## 8. Adapter and transport contracts

Reuse an existing `SourceAdapter` protocol if present. Otherwise define a
source-independent protocol equivalent to:

```python
class SourceAdapter(Protocol):
    source_slug: str
    parser_name: str
    parser_version: str
    record_schema_version: str

    def discover_job_urls(self, limit: int) -> Sequence[str]: ...
    def fetch_job_detail(self, url: str) -> FetchResponse: ...
    def extract_raw_record(self, page: FetchResponse) -> SourceRawJobRecord: ...
    def detect_closed_state(self, page: FetchResponse) -> str: ...
```

Inject:

```text
transport
clock
retry scheduler
raw-storage implementation
logger
```

Fixture transport never uses the network. Live transport follows existing
TopDev timeout, redirect, user-agent, rate, and no-bypass behavior.

---

## 9. Crawl-run lifecycle

Create a `crawl_runs` row before discovery with source, policy, parser, pipeline
version when available, requested limit, configuration JSON, and git SHA.

`configuration_json` is an immutable execution snapshot containing policy
version, request interval, request and concurrency limits, approved and blocked
paths, raw and description retention, storage permissions, mode, discovery URL,
parser/schema versions, and fail-fast behavior. `retry-run` reconstructs from
this snapshot, never from mutable current policy values. It may reject live
continuation when the source is disabled, authorization is revoked, or a new
blocked path applies.

Expected lifecycle:

```text
pending → running → succeeded
pending → running → partially_succeeded
pending → running → failed
pending → running → cancelled
```

After start, do not change run identity fields.

Before terminal update, lock the run and derive all counters from persisted
children. Do not trust only in-memory counters.

Required counter meanings:

```text
discovered_count = unique validated detail URLs
task_count = persisted discovery/detail tasks
fetch_success_count = successful fetch attempts
fetch_failure_count = failed fetch attempts
unchanged_count = later successful fetch with same body for same source identity
extracted_count = persisted extracted records
accepted_count = accepted extracted records
rejected_count = rejected extracted records
error_count = persisted crawl errors
```

Use the exact status vocabulary allowed by Migration 002.

Terminal semantics:

```text
succeeded: at least one success and no exhausted/rejected task
partially_succeeded: at least one success and at least one exhausted/rejected task
failed: discovery fails before task creation or every detail task fails/rejects
cancelled: explicit operator cancellation only
```

A fetch error never marks a posting inactive.

---

## 10. Discovery and task planning

Create one discovery task and one detail task per unique validated URL.

Detail task fields include:

```text
task_type = detail
source_job_id = numeric URL suffix
requested_url = canonicalized URL
discovery_method = curated_it_listing
max_attempts = deterministic retry-policy result
safe task_payload_json provenance
```

Enforce:

```text
requested limit <= policy maximum
detail count <= requested limit
concurrency <= policy maximum
approved/blocked path policy
```

Duplicate discovery output must not create duplicate tasks. Use a transaction
that locks the crawl run, reads existing planned tasks, and inserts only missing
ones.

---

## 11. Claiming and stale-task recovery

Claim eligible tasks with PostgreSQL:

```sql
FOR UPDATE SKIP LOCKED
```

Claim transaction:

- selects one pending/retry task whose `scheduled_for` is due;
- increments `attempt_count`;
- sets `status=running` and `started_at`;
- commits before network work.

Do not hold a database transaction during HTTP requests or rate-limit sleep.
Two workers must never claim the same attempt.

`requeue-stale` must lock stale running tasks, avoid terminal runs, respect
`max_attempts`, requeue retryable tasks, and fail exhausted tasks with a
sanitized error.

No scheduler is added in this PR.

---

## 12. Retry policy

Retryable examples:

```text
timeout
connection reset
temporary DNS failure
HTTP 408, 425, 429, 500, 502, 503, 504
```

Not retryable:

```text
invalid URL
robots denied
HTTP 400, 401, 403, 404, 410
CAPTCHA/anti-bot/login/paywall
missing or invalid JobPosting JSON-LD
required-field rejection
scope rejection
schema validation rejection
```

Default detail attempts:

```text
max_attempts = 3
attempt 1 failure → scheduled +5 seconds
attempt 2 failure → scheduled +30 seconds
attempt 3 failure → exhausted
```

Respect a safely parsed `Retry-After` only when bounded to 300 seconds. Tests use
an injected scheduler and must not sleep.

---

## 13. Fetch events

Persist one `ingestion.fetch_events` row for every actual fetch attempt.

Persist the existing schema fields, including run/task/source/raw lineage,
requested/resolved URL, status, content type, byte count, duration, attempt,
robots decision, outcome, cache headers, sanitized header JSON, and timestamps.

Use one central mapping to exact database `fetch_outcome` values and test each
value against PostgreSQL constraints.

Header allowlist:

```text
request: User-Agent, Accept, Accept-Language, If-None-Match, If-Modified-Since
response: Content-Type, Content-Length, ETag, Last-Modified, Cache-Control,
          Retry-After, Date
```

Remove authorization, cookies, CSRF/session values, API keys, and unknown
secret-bearing headers.

---

## 14. Raw objects

Hash exact response body bytes:

```text
lowercase SHA-256
```

Do not hash decoded or reformatted text.

Use atomic upsert on globally unique `ingestion.raw_objects.sha256`. Concurrent
identical bodies must produce one raw-object row referenced by multiple fetch
events.

### Storage decisions

Structured JSON up to 256 KiB may use `inline_payload_json` only when policy
allows raw storage.

Do not put full HTML in JSONB.

Fixture mode may store:

```text
storage_provider = fixture
object_key = repository-relative fixture identifier
bucket_name = NULL
inline_payload_json = NULL
```

Never store an absolute local path.

Live mode without configured object storage may process bytes in memory and
persist a fetch event without raw-object lineage; it must record that safe
storage decision in metrics. Do not write live raw HTML to Git or datasets.

When raw retention days are known:

```text
expires_at = fetched_at + retention days
```

Unknown retention remains null. No deletion is executed.

When identical bytes already exist, the raw-object ID and valid storage
location are reused. Retention is never shortened: later expiry wins, and NULL
means indefinite retention. The atomic conflict update rejects a matching
SHA-256 with a different byte size and is safe under concurrent upserts.

---

## 15. Extraction runs and records

Create one `extraction_runs` row for each fetch event reaching the parser.
Persist parser version and raw/fetch/run lineage.

A TopDev detail page emits at most one `extracted_records` row.

Persist direct evidence only through the existing `SourceRawJobRecord` contract:

```text
source identity and URL
title/company/location direct values
salary and experience direct evidence
skills raw evidence
contact-redacted description
posted/expiry dates
raw employment evidence
closed-state evidence
collection time
discovery provenance
response/content hash
```

Do not present canonical classifications as direct evidence.

### Direct hash

Hash canonical JSON bytes using:

```text
UTF-8
sorted object keys
no insignificant whitespace
stable timezone-aware datetime representation
preserved list order
direct-payload-json.v1 contract
```

Do not hash Python `repr()`.

Accepted records require source job ID, title, description, valid JobPosting
JSON-LD, valid source scope, and consistent URL identity.

Rejected records retain source/fetch/extraction lineage and a sanitized stable
reason.

The same fetch event and parser version must not create duplicate extraction
output. A later unchanged fetch event may create new evidence but increments the
run's unchanged counter.

---

## 16. Crawl errors

Persist sanitized errors with available run/task/fetch/extraction/source
lineage.

Stages:

```text
bootstrap
discovery
task_claim
fetch
raw_storage
extraction
persistence
finalization
```

Bounded categories:

```text
configuration
policy_rejected
network
timeout
http_client
http_server
robots_denied
blocked
invalid_url
invalid_content
parser
scope_rejected
schema_validation
database
internal
```

Messages are capped at 2,000 characters and must not contain raw bodies,
credentials, cookies, tokens, database URLs, local user paths, environment
variables, or stack traces.

`details_json` may contain safe structured values such as attempt number,
timeout, retry delay, content type, byte count, and parser version.

---

## 17. Policy enforcement

Before live execution require an enabled source, a currently valid policy, and
approved robots/terms status according to exact existing vocabularies.

Enforce:

```text
minimum request interval
maximum requests per run
maximum concurrency
approved/blocked paths
raw-storage permission
description-storage permission
```

Blocked paths take precedence over approved paths. Validate the discovery URL
and every detail URL before live transport work. Count every actual request
across initial and retry invocations, keep execution at or below approved
concurrency, and pass the resolved policy interval to the live transport even
when it is greater than the adapter default.

When description storage is disabled, the adapter may inspect description in
memory but the persisted direct payload must omit/null it and record a safe
suppression flag. Do not replace it with a summary.

---

## 18. Transaction boundaries

Use short transactions:

```text
claim task → commit
HTTP outside transaction
persist fetch/raw evidence → commit
extract outside transaction when possible
persist extraction/record/error/task result → commit
finalize run from locked persisted evidence → commit
```

Do not hold locks while performing HTTP or sleeping.

On partial failure, preserve already committed evidence. Explicit recovery
handles stale tasks.

---

## 19. Fixture and live modes

Fixture mode is the default and is mandatory for CI. Required scenarios:

```text
active valid job
expired valid job
negotiable salary
missing/invalid JSON-LD
duplicate discovery URL
429 then success
403 blocked
404/410
timeout then success
unchanged later body
changed later body
```

Fixture URLs must still pass production URL validation; use a mapped test
transport rather than weakening validation.

Live mode is explicit and bounded:

```text
maximum 30 requests
minimum two-second interval
concurrency one unless approved otherwise
descriptive user agent
no login
no CAPTCHA solving
no proxy rotation
no 403/anti-bot retry
no cookie persistence
no scheduled execution in this PR
```

CI must not depend on TopDev availability.

---

## 20. Tests

### Unit

Cover sanitization, exact-byte and direct-payload hashing, retry classification,
backoff, `Retry-After`, duplicate planning, run outcomes, fail-fast, dry-run, and
counter calculation.

### PostgreSQL integration

Cover:

- idempotent bootstrap and parser rotation;
- complete fixture lineage;
- one fetch event per actual attempt;
- accepted and rejected extraction output;
- raw allowed/suppressed and description allowed/suppressed;
- retention expiry behavior;
- source-consistency rejection/prevention;
- unchanged and changed later fetches;
- retry and no-retry paths;
- stale-task recovery;
- database-derived run counters;
- secret-free persisted errors.

### Concurrency

Use separate PostgreSQL connections and bounded lock/statement timeouts:

1. two workers upsert identical raw bytes and produce one raw object;
2. two workers attempt to claim the same task and only one succeeds.

Existing TopDev adapter and all Database V1 tests must remain green.

---

## 21. Metrics and logging

Use structured logs with IDs and bounded metadata:

```text
event
source_slug
crawl_run_id
crawl_task_id
source_job_id
attempt_number
stage
outcome
duration_ms
```

Never log raw bodies, descriptions, unapproved headers, database URLs,
credentials, cookies, or tokens.

No monitoring-vendor integration in this PR.

---

## 22. CI

CI must:

1. upgrade PostgreSQL to Alembic head;
2. run existing Database V1 tests;
3. run existing TopDev tests;
4. run fixture-mode ingestion PostgreSQL tests;
5. run raw-upsert and task-claim concurrency tests;
6. run full pytest;
7. run Ruff;
8. run Black;
9. run MyPy.

CI must not use live network access or object-storage credentials.

---

## 23. Documentation

`docs/DATA_PIPELINE_V1_INGESTION.md` must explain architecture, lineage,
transactions, idempotency, retries, fixture/live modes, raw policy, parser
versioning, counters, and limitations.

`docs/TOPDEV_INGESTION_RUNBOOK.md` must cover bootstrap, policy review, enable,
fixture run, inspect, optional live run, recovery, disable, failure triage, and
safe SQL queries.

State clearly:

```text
fetch failure never closes a posting
this PR stops before canonical import
retention metadata does not delete data
object storage is not provisioned automatically
```

---

## 24. Out of scope

Do not implement:

```text
canonical/core importer
history observation writer
quality evidence writer
cross-posting deduplication
company/location/taxonomy resolution
analytics or serving refresh
public API/dashboard changes
scheduler/cron/distributed queue
second source adapter
object-storage provisioning
retention deletion/archive export
proxy rotation/login/CAPTCHA bypass
LLM extraction/embeddings
```

---

## 25. Acceptance criteria

- [ ] Generic runner has no TopDev selector/mapping logic.
- [ ] TopDev adapter has no database-session logic.
- [ ] Source is disabled by default.
- [ ] Live mode requires approved policy and explicit enable.
- [ ] Complete Source → Run → Task → Fetch → Raw → Extraction → Record lineage.
- [ ] Every actual attempt creates a fetch event.
- [ ] Raw bytes use exact lowercase SHA-256.
- [ ] Concurrent identical bytes deduplicate safely.
- [ ] Parser/schema versions are persisted.
- [ ] Rejected records and failures retain sanitized lineage.
- [ ] Duplicate discovery does not duplicate tasks.
- [ ] Two workers cannot claim the same task.
- [ ] Retries and stale recovery are bounded.
- [ ] Run counters come from persisted evidence.
- [ ] No writes outside `ingestion`/required `system` version lookup.
- [ ] CI uses fixtures only.
- [ ] Full pytest, Ruff, Black, and MyPy pass.

---

## 26. Codex workflow

1. Read `AGENT_RULES.md` and this specification.
2. Read TopDev adapter docs/code/tests and Database V1 ingestion migration/models.
3. Confirm `main` includes merged Migration 007 and pull latest `origin/main`.
4. Create `feat/data-pipeline-v1-topdev-ingestion`.
5. Implement generic ingestion orchestration and TopDev registration.
6. Add deterministic fixtures, unit tests, PostgreSQL tests, and two concurrency tests.
7. Do not use the live network during implementation or CI.
8. Run all checks.
9. Push and create one draft PR into `main`.
10. Do not merge.

---

## 27. Codex prompt

```text
Read AGENT_RULES.md and DATA_PIPELINE_V1_INGESTION_WORKER_SPEC.md.

Confirm main contains the merged Database V1 Migration 007 and pull the latest
origin/main.

Create:
feat/data-pipeline-v1-topdev-ingestion

Implement Data Pipeline V1 TopDev Ingestion Worker exactly as specified.

Reuse the existing TopDevAdapter and preserve its verified extraction behavior.
Build a source-independent ingestion runner that persists complete Database V1
lineage:

Source -> CrawlRun -> CrawlTask -> FetchEvent -> RawObject
                                      -> ExtractionRun -> ExtractedRecord

Persist sanitized CrawlError evidence for failures.

Implement:
- explicit TopDev source/policy/parser bootstrap;
- disabled-by-default live source;
- fixture and opt-in live modes;
- bounded source-policy enforcement;
- deterministic task planning;
- FOR UPDATE SKIP LOCKED task claiming;
- bounded retries and stale-task recovery;
- exact raw-byte SHA-256 deduplication;
- parser-version and schema-version lineage;
- deterministic direct-payload hashing;
- database-derived final run counters;
- safe structured logging.

Do not add Migration 008 unless an existing database constraint makes correct
implementation impossible. Explain and test any migration before adding it.

Do not write to core, history, quality, analytics, serving, or api. Do not add a
scheduler, queue, second source, object-storage provisioning, retention
deletion, proxy rotation, login, CAPTCHA solving, LLM extraction, or frontend
changes.

CI and all tests must use repository fixtures and must not access TopDev live.

Add unit and PostgreSQL integration tests, including real two-connection tests
for:
- concurrent identical raw-object upsert;
- two workers claiming tasks.

Run:
- Alembic upgrade head
- existing Database V1 tests
- existing TopDev adapter tests
- new ingestion PostgreSQL tests
- full pytest
- Ruff
- Black
- MyPy

Push the branch and create one draft PR into main. Do not merge.

Report the PR link, final commit, CLI commands, test counts, concurrency
scenarios, full pytest result, and GitHub Actions status.
```
