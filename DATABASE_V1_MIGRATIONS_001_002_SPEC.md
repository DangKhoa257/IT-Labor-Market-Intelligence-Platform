# Database V1 — Migration 001 & 002 Implementation Specification

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`  
**Target database:** PostgreSQL 16 / Supabase PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration tool:** Alembic  
**Audience:** Codex implementation agent  
**Status:** Implementation-ready specification  
**Scope:** Database V1 foundation and ingestion layers only

---

## 1. Objective

Implement the first two Database V1 migrations for the IT Labor Market Intelligence Platform.

These migrations establish:

- PostgreSQL schemas and required extensions;
- system-level metadata and operational audit tables;
- source registry and source-specific collection policies;
- parser version registry;
- crawl execution tracking;
- crawl task and fetch-event lineage;
- immutable raw-object metadata;
- extraction run and extracted-record tracking;
- structured crawl errors;
- PostgreSQL integration tests;
- CI validation against PostgreSQL 16.

The implementation must support a market-intelligence data pipeline:

```text
Source
→ CrawlRun
→ CrawlTask
→ FetchEvent
→ RawObject
→ ExtractionRun
→ ExtractedRecord
→ later canonical/history/analytics layers
```

Do not implement canonical job, taxonomy, history, analytics, serving, recommendation, or user-account tables in this task.

---

## 2. Non-negotiable rules

1. Alembic migrations must be fully explicit.
2. Do not call `Base.metadata.create_all()` or `Base.metadata.drop_all()` from migrations.
3. Do not generate tables dynamically from current SQLAlchemy metadata.
4. Every table, constraint, index, enum-like check, schema, extension, and foreign key must be declared explicitly in Alembic.
5. All timestamps must use `TIMESTAMPTZ`.
6. Store timestamps in UTC.
7. Do not use PostgreSQL native enum types in Migration 001 or 002.
8. Stable technical statuses must use `TEXT` or bounded `VARCHAR` with `CHECK` constraints.
9. Use `JSONB`, not generic `JSON`, for PostgreSQL JSON columns.
10. Large raw payloads must not be stored directly in ordinary relational columns by default.
11. Raw evidence must be append-only from the application perspective.
12. A failed fetch must never imply that a job posting is inactive.
13. Do not modify crawler behavior, API response contracts, canonical models, or dashboard code except where imports/configuration must remain valid.
14. Do not remove the existing Phase 3 models or migration in this task unless the implementation plan explicitly documents a clean-baseline replacement and tests it.
15. Prefer additive implementation under new PostgreSQL schemas.
16. The resulting database must work on PostgreSQL 16 and Supabase-compatible PostgreSQL.
17. SQLite may remain for isolated unit tests, but all migration and PostgreSQL-specific behavior must be tested on PostgreSQL.

---

## 3. Naming conventions

### 3.1 Schemas

Create these schemas:

```text
system
ingestion
```

Do not create `core`, `taxonomy`, `history`, `quality`, `analytics`, or `serving` in Migration 001 or 002 unless the repository requires empty schema placeholders for documented sequencing. The default is not to create unused schemas.

### 3.2 Database object names

Use snake_case.

Constraint naming:

```text
pk_<table>
fk_<table>__<column>__<referenced_table>
uq_<table>__<columns>
ck_<table>__<purpose>
```

Index naming:

```text
ix_<table>__<columns>
```

Examples:

```text
pk_sources
fk_crawl_runs__source_id__sources
uq_sources__slug
ck_crawl_runs__status
ix_fetch_events__source_id_fetched_at
```

### 3.3 IDs

Use:

- `UUID` for stable business/configuration entities;
- `BIGINT GENERATED ALWAYS AS IDENTITY` for high-volume event tables.

Use PostgreSQL `gen_random_uuid()` for UUID defaults.

### 3.4 Timestamp conventions

Every mutable entity should have:

```text
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Event and append-only tables usually require only `created_at`, `started_at`, `finished_at`, `fetched_at`, `observed_at`, or equivalent event timestamps.

Do not use database triggers for `updated_at` in this task. Application code must update it explicitly when a row changes.

### 3.5 JSONB conventions

JSONB values must default to an empty object or array only when an empty structure has a valid semantic meaning.

Use `NULL` when the value is unknown, unavailable, or not applicable.

---

# 4. Migration 001 — Foundation

## 4.1 Migration identity

Suggested Alembic revision:

```text
20260726_0001_database_v1_foundation
```

The exact revision identifier may follow repository conventions, but the migration name must clearly indicate Database V1 foundation.

## 4.2 Extensions

Create:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

`pgcrypto` is required for `gen_random_uuid()`.

Do not add optional extensions such as `pg_trgm`, `vector`, or PostGIS in this migration.

## 4.3 Schemas

Create:

```sql
CREATE SCHEMA IF NOT EXISTS system;
CREATE SCHEMA IF NOT EXISTS ingestion;
```

Downgrade must drop tables before schemas.

Do not drop schemas with `CASCADE`.

---

## 5. Migration 001 tables

Migration 001 must create these seven tables:

```text
system.pipeline_versions
system.retention_policies
system.background_jobs
system.audit_events
ingestion.sources
ingestion.source_policies
ingestion.parser_versions
```

---

## 5.1 `system.pipeline_versions`

Tracks immutable versions of crawler, extractor, normalizer, deduplication, quality, analytics, and other pipeline components.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `component` | `VARCHAR(50)` | No | — | Pipeline component |
| `version` | `VARCHAR(100)` | No | — | Semantic version or immutable build identifier |
| `git_commit_sha` | `VARCHAR(64)` | Yes | — | Git commit, normally 40-char SHA |
| `configuration_hash` | `VARCHAR(128)` | Yes | — | Hash of relevant runtime configuration |
| `metadata_json` | `JSONB` | No | `'{}'::jsonb` | Build metadata; must not contain secrets |
| `released_at` | `TIMESTAMPTZ` | Yes | — | Release/build timestamp |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Registry insertion time |

### Checks

`component` must be one of:

```text
crawler
discovery
fetcher
extractor
normalizer
validator
deduplicator
quality
analytics
serving
other
```

`version` must not be blank after trimming.

`git_commit_sha`, when present, must match:

```regex
^[0-9a-fA-F]{7,64}$
```

### Constraints

```text
PRIMARY KEY (id)
UNIQUE (component, version)
```

### Indexes

```text
ix_pipeline_versions__component_created_at
    (component, created_at DESC)
```

### Mutability

Rows are immutable after insertion except for correcting invalid metadata through an audited administrative process.

---

## 5.2 `system.retention_policies`

Defines retention by source and data class.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `source_id` | `UUID` | Yes | — | Nullable for global default; FK added after `ingestion.sources` exists |
| `data_class` | `VARCHAR(50)` | No | — | Retained data category |
| `retention_days` | `INTEGER` | Yes | — | Null means no automatic expiry |
| `action` | `VARCHAR(30)` | No | `'delete'` | Retention action |
| `is_active` | `BOOLEAN` | No | `true` | Policy activation |
| `policy_version` | `VARCHAR(100)` | No | — | Versioned policy identifier |
| `notes` | `TEXT` | Yes | — | Human-readable rationale |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last update |

### `data_class` allowed values

```text
raw_html
raw_json
structured_evidence
failed_response_body
fetch_metadata
extracted_record
crawl_error
audit_event
other
```

### `action` allowed values

```text
delete
archive
redact
retain
```

### Checks

```text
retention_days IS NULL OR retention_days >= 0
```

`policy_version` must not be blank.

### Constraints

After `ingestion.sources` exists, add:

```text
FOREIGN KEY (source_id)
REFERENCES ingestion.sources(id)
ON DELETE CASCADE
```

Unique:

```text
UNIQUE NULLS NOT DISTINCT (source_id, data_class, policy_version)
```

Use PostgreSQL 15+ syntax if Alembic supports it reliably. If the repository's Alembic/SQLAlchemy version does not expose `NULLS NOT DISTINCT`, implement equivalent uniqueness with two explicit partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_retention_policies__global_data_class_version
ON system.retention_policies (data_class, policy_version)
WHERE source_id IS NULL;

CREATE UNIQUE INDEX uq_retention_policies__source_data_class_version
ON system.retention_policies (source_id, data_class, policy_version)
WHERE source_id IS NOT NULL;
```

Prefer the partial-index implementation for clarity.

### Indexes

```text
ix_retention_policies__source_id
    (source_id)

ix_retention_policies__active_data_class
    (data_class, is_active)
```

---

## 5.3 `system.background_jobs`

Tracks scheduled refresh, cleanup, archive, backfill, and maintenance jobs.

This is operational metadata, not a general distributed queue.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `job_name` | `VARCHAR(150)` | No | — | Stable logical name |
| `job_type` | `VARCHAR(50)` | No | — | Job category |
| `status` | `VARCHAR(30)` | No | `'pending'` | Current state |
| `scheduled_for` | `TIMESTAMPTZ` | Yes | — | Intended execution time |
| `started_at` | `TIMESTAMPTZ` | Yes | — | Start time |
| `finished_at` | `TIMESTAMPTZ` | Yes | — | Finish time |
| `attempt_count` | `INTEGER` | No | `0` | Attempts |
| `max_attempts` | `INTEGER` | No | `1` | Allowed attempts |
| `payload_json` | `JSONB` | No | `'{}'::jsonb` | Non-secret execution input |
| `result_json` | `JSONB` | Yes | — | Sanitized result summary |
| `error_message` | `TEXT` | Yes | — | Sanitized error |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation time |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last update |

### `job_type` allowed values

```text
retention
archive
aggregate_refresh
materialized_view_refresh
backfill
data_quality
maintenance
other
```

### `status` allowed values

```text
pending
running
succeeded
failed
cancelled
skipped
```

### Checks

```text
attempt_count >= 0
max_attempts >= 1
attempt_count <= max_attempts
finished_at IS NULL OR started_at IS NOT NULL
finished_at IS NULL OR finished_at >= started_at
```

### Constraints

No global unique constraint on `job_name`; the same logical job may run repeatedly.

### Indexes

```text
ix_background_jobs__status_scheduled_for
    (status, scheduled_for)

ix_background_jobs__job_name_created_at
    (job_name, created_at DESC)
```

---

## 5.4 `system.audit_events`

Append-only audit trail for manual or privileged changes.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `actor_type` | `VARCHAR(30)` | No | — | Actor category |
| `actor_id` | `VARCHAR(255)` | Yes | — | User/service identifier |
| `action` | `VARCHAR(100)` | No | — | Action name |
| `entity_schema` | `VARCHAR(63)` | Yes | — | PostgreSQL schema |
| `entity_table` | `VARCHAR(63)` | Yes | — | Table name |
| `entity_id` | `VARCHAR(255)` | Yes | — | Entity identifier |
| `request_id` | `VARCHAR(100)` | Yes | — | Correlation/request ID |
| `before_json` | `JSONB` | Yes | — | Sanitized prior state |
| `after_json` | `JSONB` | Yes | — | Sanitized new state |
| `metadata_json` | `JSONB` | No | `'{}'::jsonb` | Additional non-secret metadata |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Event time |

### `actor_type` allowed values

```text
user
service
system
migration
unknown
```

### Checks

`action` must not be blank.

### Indexes

```text
ix_audit_events__created_at
    (created_at DESC)

ix_audit_events__entity
    (entity_schema, entity_table, entity_id)

ix_audit_events__request_id
    (request_id)
    WHERE request_id IS NOT NULL
```

### Mutability

Append-only. Application repositories must not expose update/delete methods.

---

## 5.5 `ingestion.sources`

Canonical registry of data sources.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `slug` | `VARCHAR(100)` | No | — | Stable lowercase identifier |
| `display_name` | `VARCHAR(255)` | No | — | Human-readable name |
| `base_url` | `TEXT` | No | — | Source base URL |
| `source_type` | `VARCHAR(50)` | No | `'job_board'` | Source category |
| `country_code` | `CHAR(2)` | Yes | — | ISO 3166-1 alpha-2 |
| `status` | `VARCHAR(30)` | No | `'researching'` | Compliance/operational state |
| `is_enabled` | `BOOLEAN` | No | `false` | Scheduler eligibility |
| `owner_contact` | `VARCHAR(255)` | Yes | — | Internal responsible owner |
| `metadata_json` | `JSONB` | No | `'{}'::jsonb` | Non-secret source metadata |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation time |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last update |

### `source_type` allowed values

```text
job_board
company_career_site
aggregator
government
community
other
```

### `status` allowed values

```text
researching
approved
paused
blocked
retired
```

### Checks

`slug` must match:

```regex
^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$
```

`display_name` must not be blank.

`base_url` must begin with `http://` or `https://`.

`country_code`, when present, must match two uppercase ASCII letters.

Critical scheduler rule:

```text
is_enabled = true
```

is valid only when:

```text
status = 'approved'
```

Enforce with:

```sql
CHECK (NOT is_enabled OR status = 'approved')
```

### Constraints

```text
PRIMARY KEY (id)
UNIQUE (slug)
```

### Indexes

```text
ix_sources__status_enabled
    (status, is_enabled)

ix_sources__source_type
    (source_type)
```

---

## 5.6 `ingestion.source_policies`

Versioned operational and compliance policy for each source.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `source_id` | `UUID` | No | — | FK to source |
| `policy_version` | `VARCHAR(100)` | No | — | Immutable version |
| `robots_review_status` | `VARCHAR(30)` | No | `'not_reviewed'` | robots review |
| `terms_review_status` | `VARCHAR(30)` | No | `'not_reviewed'` | terms review |
| `approved_paths` | `JSONB` | No | `'[]'::jsonb` | Array of approved path patterns |
| `blocked_paths` | `JSONB` | No | `'[]'::jsonb` | Array of blocked path patterns |
| `minimum_request_interval_seconds` | `NUMERIC(10,3)` | No | `2.000` | Minimum interval |
| `maximum_requests_per_run` | `INTEGER` | No | `30` | Hard per-run limit |
| `maximum_concurrent_requests` | `INTEGER` | No | `1` | Concurrency cap |
| `raw_retention_days` | `INTEGER` | Yes | `30` | Source-specific raw retention |
| `description_retention_days` | `INTEGER` | Yes | `90` | Extracted description retention |
| `allow_raw_storage` | `BOOLEAN` | No | `true` | Raw storage permitted |
| `allow_description_storage` | `BOOLEAN` | No | `true` | Description storage permitted |
| `notes` | `TEXT` | Yes | — | Review rationale |
| `reviewed_by` | `VARCHAR(255)` | Yes | — | Internal reviewer |
| `reviewed_at` | `TIMESTAMPTZ` | Yes | — | Review time |
| `valid_from` | `TIMESTAMPTZ` | No | `now()` | Effective start |
| `valid_to` | `TIMESTAMPTZ` | Yes | — | Effective end |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation time |

### Allowed review statuses

```text
not_reviewed
approved
restricted
rejected
needs_update
```

### Checks

```text
minimum_request_interval_seconds >= 0
maximum_requests_per_run >= 1
maximum_concurrent_requests >= 1
raw_retention_days IS NULL OR raw_retention_days >= 0
description_retention_days IS NULL OR description_retention_days >= 0
valid_to IS NULL OR valid_to > valid_from
reviewed_at IS NULL OR reviewed_by IS NOT NULL
```

JSONB shape checks:

```sql
jsonb_typeof(approved_paths) = 'array'
jsonb_typeof(blocked_paths) = 'array'
```

### Constraints

```text
FOREIGN KEY (source_id)
REFERENCES ingestion.sources(id)
ON DELETE CASCADE

UNIQUE (source_id, policy_version)
```

### Indexes

```text
ix_source_policies__source_id_valid_from
    (source_id, valid_from DESC)

ix_source_policies__active
    (source_id, valid_from, valid_to)
```

Only one active policy per source should be selected by application logic using the current timestamp. An exclusion constraint is not required in this migration.

---

## 5.7 `ingestion.parser_versions`

Registry of source-specific parser/extractor builds.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `source_id` | `UUID` | No | — | FK to source |
| `pipeline_version_id` | `UUID` | Yes | — | Optional link to system version |
| `parser_name` | `VARCHAR(150)` | No | — | Stable parser name |
| `version` | `VARCHAR(100)` | No | — | Version/build ID |
| `schema_version` | `VARCHAR(100)` | No | — | Extraction-contract version |
| `git_commit_sha` | `VARCHAR(64)` | Yes | — | Source revision |
| `configuration_hash` | `VARCHAR(128)` | Yes | — | Parser configuration hash |
| `is_active` | `BOOLEAN` | No | `false` | Whether newly scheduled runs may use it |
| `metadata_json` | `JSONB` | No | `'{}'::jsonb` | Build metadata |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Registry time |
| `retired_at` | `TIMESTAMPTZ` | Yes | — | Retirement time |

### Checks

`parser_name`, `version`, and `schema_version` must not be blank.

`git_commit_sha`, when present, must match:

```regex
^[0-9a-fA-F]{7,64}$
```

```text
retired_at IS NULL OR retired_at >= created_at
NOT is_active OR retired_at IS NULL
```

### Constraints

```text
FOREIGN KEY (source_id)
REFERENCES ingestion.sources(id)
ON DELETE CASCADE

FOREIGN KEY (pipeline_version_id)
REFERENCES system.pipeline_versions(id)
ON DELETE SET NULL

UNIQUE (source_id, parser_name, version)
```

### Indexes

```text
ix_parser_versions__source_id_active
    (source_id, is_active)

ix_parser_versions__pipeline_version_id
    (pipeline_version_id)
```

Application logic should prevent more than one active version for the same `(source_id, parser_name)`. This may be enforced with a partial unique index:

```sql
CREATE UNIQUE INDEX uq_parser_versions__one_active_parser
ON ingestion.parser_versions (source_id, parser_name)
WHERE is_active;
```

---

## 6. Migration 001 foreign-key ordering

Because `system.retention_policies` references `ingestion.sources`, create objects in this order:

1. extensions;
2. schemas;
3. `system.pipeline_versions`;
4. `system.background_jobs`;
5. `system.audit_events`;
6. `ingestion.sources`;
7. `system.retention_policies`;
8. `ingestion.source_policies`;
9. `ingestion.parser_versions`;
10. indexes;
11. grants/RLS preparation if included.

Downgrade in exact reverse dependency order.

---

# 7. Migration 002 — Ingestion execution and lineage

## 7.1 Migration identity

Suggested revision:

```text
20260726_0002_database_v1_ingestion
```

`down_revision` must reference Migration 001.

## 7.2 Migration 002 tables

Create these seven tables:

```text
ingestion.crawl_runs
ingestion.crawl_tasks
ingestion.raw_objects
ingestion.fetch_events
ingestion.extraction_runs
ingestion.extracted_records
ingestion.crawl_errors
```

---

## 8. Migration 002 tables

## 8.1 `ingestion.crawl_runs`

One execution of discovery, fetch, recheck, import, or reprocessing for one source.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | Primary key |
| `source_id` | `UUID` | No | — | Source |
| `source_policy_id` | `UUID` | Yes | — | Policy used |
| `parser_version_id` | `UUID` | Yes | — | Parser used |
| `pipeline_version_id` | `UUID` | Yes | — | Pipeline build |
| `run_type` | `VARCHAR(30)` | No | `'scheduled'` | Run purpose |
| `trigger_type` | `VARCHAR(30)` | No | `'manual'` | Trigger |
| `status` | `VARCHAR(30)` | No | `'pending'` | Run state |
| `requested_limit` | `INTEGER` | Yes | — | Requested record/request limit |
| `configuration_json` | `JSONB` | No | `'{}'::jsonb` | Sanitized runtime configuration |
| `git_commit_sha` | `VARCHAR(64)` | Yes | — | Executing commit |
| `started_at` | `TIMESTAMPTZ` | Yes | — | Start |
| `finished_at` | `TIMESTAMPTZ` | Yes | — | Finish |
| `discovered_count` | `INTEGER` | No | `0` | Discovered URLs/identities |
| `task_count` | `INTEGER` | No | `0` | Tasks created |
| `fetch_success_count` | `INTEGER` | No | `0` | Successful responses |
| `fetch_failure_count` | `INTEGER` | No | `0` | Failed responses |
| `unchanged_count` | `INTEGER` | No | `0` | Unchanged evidence |
| `extracted_count` | `INTEGER` | No | `0` | Extracted records |
| `accepted_count` | `INTEGER` | No | `0` | Accepted by extraction/validation gate |
| `rejected_count` | `INTEGER` | No | `0` | Rejected records |
| `error_count` | `INTEGER` | No | `0` | Structured errors |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation time |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last update |

### `run_type` allowed values

```text
scheduled
manual
backfill
recheck
reprocess
import
test
```

### `trigger_type` allowed values

```text
manual
scheduler
github_actions
api
system
test
```

### `status` allowed values

```text
pending
running
succeeded
partially_succeeded
failed
cancelled
skipped
```

### Checks

All counter fields must be `>= 0`.

```text
requested_limit IS NULL OR requested_limit >= 1
finished_at IS NULL OR started_at IS NOT NULL
finished_at IS NULL OR finished_at >= started_at
status != 'running' OR started_at IS NOT NULL
status NOT IN ('succeeded','partially_succeeded','failed','cancelled','skipped')
    OR finished_at IS NOT NULL
```

`git_commit_sha`, when present, must match the SHA regex defined above.

### Foreign keys

```text
source_id
→ ingestion.sources(id)
ON DELETE RESTRICT

source_policy_id
→ ingestion.source_policies(id)
ON DELETE SET NULL

parser_version_id
→ ingestion.parser_versions(id)
ON DELETE SET NULL

pipeline_version_id
→ system.pipeline_versions(id)
ON DELETE SET NULL
```

### Indexes

```text
ix_crawl_runs__source_id_started_at
    (source_id, started_at DESC)

ix_crawl_runs__status_created_at
    (status, created_at DESC)

ix_crawl_runs__parser_version_id
    (parser_version_id)

ix_crawl_runs__pipeline_version_id
    (pipeline_version_id)
```

---

## 8.2 `ingestion.crawl_tasks`

Represents one unit of crawl work such as a listing page, detail page, API page, sitemap shard, or recheck target.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `crawl_run_id` | `UUID` | No | — | Parent run |
| `source_id` | `UUID` | No | — | Denormalized for query efficiency |
| `task_type` | `VARCHAR(30)` | No | — | Work unit |
| `status` | `VARCHAR(30)` | No | `'pending'` | Task state |
| `priority` | `SMALLINT` | No | `0` | Relative priority |
| `source_job_id` | `VARCHAR(255)` | Yes | — | Known source identity |
| `requested_url` | `TEXT` | Yes | — | Target URL |
| `discovery_method` | `VARCHAR(150)` | Yes | — | Discovery provenance |
| `attempt_count` | `INTEGER` | No | `0` | Attempts |
| `max_attempts` | `INTEGER` | No | `1` | Max attempts |
| `scheduled_for` | `TIMESTAMPTZ` | Yes | — | Planned execution |
| `started_at` | `TIMESTAMPTZ` | Yes | — | Start |
| `finished_at` | `TIMESTAMPTZ` | Yes | — | Finish |
| `task_payload_json` | `JSONB` | No | `'{}'::jsonb` | Non-secret task metadata |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation time |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last update |

### `task_type` allowed values

```text
discovery
listing_page
detail_page
api_page
sitemap
recheck
reprocess
other
```

### `status` allowed values

```text
pending
running
succeeded
failed
cancelled
skipped
```

### Checks

```text
priority BETWEEN -32768 AND 32767
attempt_count >= 0
max_attempts >= 1
attempt_count <= max_attempts
requested_url IS NOT NULL OR source_job_id IS NOT NULL
finished_at IS NULL OR started_at IS NOT NULL
finished_at IS NULL OR finished_at >= started_at
```

### Foreign keys

```text
crawl_run_id
→ ingestion.crawl_runs(id)
ON DELETE CASCADE

source_id
→ ingestion.sources(id)
ON DELETE RESTRICT
```

### Constraints

Avoid duplicate detail tasks inside one run:

```text
UNIQUE (crawl_run_id, task_type, requested_url)
```

Because `requested_url` is nullable, also add a partial unique index for known source identity:

```sql
CREATE UNIQUE INDEX uq_crawl_tasks__run_type_source_job
ON ingestion.crawl_tasks (crawl_run_id, task_type, source_job_id)
WHERE source_job_id IS NOT NULL;
```

### Indexes

```text
ix_crawl_tasks__run_status_priority
    (crawl_run_id, status, priority DESC, id)

ix_crawl_tasks__source_id_source_job_id
    (source_id, source_job_id)
    WHERE source_job_id IS NOT NULL

ix_crawl_tasks__status_scheduled_for
    (status, scheduled_for)
```

---

## 8.3 `ingestion.raw_objects`

Immutable metadata and optional inline structured evidence.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `sha256` | `CHAR(64)` | No | — | Content digest |
| `storage_provider` | `VARCHAR(30)` | No | — | Storage location |
| `bucket_name` | `VARCHAR(255)` | Yes | — | External bucket/container |
| `object_key` | `TEXT` | Yes | — | External object path |
| `inline_payload_json` | `JSONB` | Yes | — | Small structured evidence only |
| `compression` | `VARCHAR(20)` | No | `'none'` | Compression type |
| `mime_type` | `VARCHAR(255)` | Yes | — | MIME type |
| `byte_size` | `BIGINT` | No | — | Original bytes |
| `redaction_status` | `VARCHAR(30)` | No | `'not_required'` | Redaction state |
| `retention_policy_id` | `UUID` | Yes | — | Applied policy |
| `expires_at` | `TIMESTAMPTZ` | Yes | — | Expiry |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Registration time |

### `storage_provider` allowed values

```text
inline
supabase_storage
filesystem
s3_compatible
github_artifact
other
```

### `compression` allowed values

```text
none
gzip
zstd
zip
other
```

### `redaction_status` allowed values

```text
not_required
pending
redacted
failed
```

### Checks

`sha256`:

```regex
^[0-9a-f]{64}$
```

```text
byte_size >= 0
```

Storage consistency:

```text
storage_provider = 'inline'
    → inline_payload_json IS NOT NULL
    → bucket_name IS NULL
    → object_key IS NULL

storage_provider != 'inline'
    → object_key IS NOT NULL
```

Do not enforce `bucket_name IS NOT NULL` for all external providers because filesystem or GitHub artifact references may not use buckets.

### Foreign keys

```text
retention_policy_id
→ system.retention_policies(id)
ON DELETE SET NULL
```

### Constraints

```text
UNIQUE (sha256)
```

### Indexes

```text
ix_raw_objects__expires_at
    (expires_at)
    WHERE expires_at IS NOT NULL

ix_raw_objects__retention_policy_id
    (retention_policy_id)

ix_raw_objects__created_at
    (created_at DESC)
```

### Application rules

- Append-only.
- Deduplicate by SHA-256.
- Do not overwrite payload/object references for an existing SHA except through audited repair.
- Do not store full HTML as `inline_payload_json`.
- `inline_payload_json` is intended for small JSON-LD, API JSON, headers, or structured evidence.
- Large payloads belong in external storage.

---

## 8.4 `ingestion.fetch_events`

One HTTP or equivalent fetch observation.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `crawl_run_id` | `UUID` | No | — | Parent run |
| `crawl_task_id` | `BIGINT` | Yes | — | Parent task |
| `source_id` | `UUID` | No | — | Source |
| `raw_object_id` | `BIGINT` | Yes | — | Body/evidence reference |
| `requested_url` | `TEXT` | No | — | Requested URL |
| `resolved_url` | `TEXT` | Yes | — | Final URL after redirects |
| `http_method` | `VARCHAR(10)` | No | `'GET'` | Method |
| `http_status` | `SMALLINT` | Yes | — | HTTP code |
| `content_type` | `VARCHAR(255)` | Yes | — | Response content type |
| `response_bytes` | `BIGINT` | Yes | — | Response size |
| `duration_ms` | `INTEGER` | Yes | — | Request duration |
| `attempt_number` | `INTEGER` | No | `1` | Attempt |
| `robots_allowed` | `BOOLEAN` | Yes | — | robots decision |
| `fetch_outcome` | `VARCHAR(30)` | No | — | Outcome |
| `etag` | `TEXT` | Yes | — | ETag |
| `last_modified` | `TEXT` | Yes | — | Raw Last-Modified header |
| `request_headers_json` | `JSONB` | No | `'{}'::jsonb` | Sanitized request metadata |
| `response_headers_json` | `JSONB` | No | `'{}'::jsonb` | Sanitized response headers |
| `fetched_at` | `TIMESTAMPTZ` | No | — | Observation time |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Database insertion time |

### `fetch_outcome` allowed values

```text
success
http_error
network_error
timeout
blocked_by_policy
robots_disallowed
invalid_content
cancelled
other_error
```

### Checks

```text
http_method IN ('GET', 'HEAD')
http_status IS NULL OR http_status BETWEEN 100 AND 599
response_bytes IS NULL OR response_bytes >= 0
duration_ms IS NULL OR duration_ms >= 0
attempt_number >= 1
```

Outcome consistency:

- `success` requires `http_status BETWEEN 200 AND 399`.
- `robots_disallowed` requires `robots_allowed = false`.
- `blocked_by_policy` may leave `http_status` null.
- Network/timeouts may leave `http_status` null.

Do not create overly restrictive checks that prevent valid non-HTTP fetch sources in future; this migration remains HTTP-oriented.

### Foreign keys

```text
crawl_run_id
→ ingestion.crawl_runs(id)
ON DELETE CASCADE

crawl_task_id
→ ingestion.crawl_tasks(id)
ON DELETE SET NULL

source_id
→ ingestion.sources(id)
ON DELETE RESTRICT

raw_object_id
→ ingestion.raw_objects(id)
ON DELETE SET NULL
```

### Constraints

No uniqueness constraint: multiple attempts and repeated observations are valid.

### Indexes

```text
ix_fetch_events__run_fetched_at
    (crawl_run_id, fetched_at)

ix_fetch_events__source_id_fetched_at
    (source_id, fetched_at DESC)

ix_fetch_events__task_id
    (crawl_task_id)

ix_fetch_events__http_status
    (http_status)
    WHERE http_status IS NOT NULL

ix_fetch_events__outcome_fetched_at
    (fetch_outcome, fetched_at DESC)

ix_fetch_events__raw_object_id
    (raw_object_id)
    WHERE raw_object_id IS NOT NULL
```

---

## 8.5 `ingestion.extraction_runs`

One parser execution over one fetch event/raw object.

A raw object may be reprocessed multiple times by different parser versions.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `crawl_run_id` | `UUID` | Yes | — | Run that initiated extraction |
| `fetch_event_id` | `BIGINT` | No | — | Input fetch |
| `raw_object_id` | `BIGINT` | Yes | — | Input evidence |
| `parser_version_id` | `UUID` | No | — | Parser build |
| `status` | `VARCHAR(30)` | No | `'pending'` | State |
| `started_at` | `TIMESTAMPTZ` | Yes | — | Start |
| `finished_at` | `TIMESTAMPTZ` | Yes | — | Finish |
| `record_count` | `INTEGER` | No | `0` | Extracted records |
| `warning_count` | `INTEGER` | No | `0` | Warnings |
| `error_count` | `INTEGER` | No | `0` | Errors |
| `metrics_json` | `JSONB` | No | `'{}'::jsonb` | Sanitized metrics |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Creation |

### `status` allowed values

```text
pending
running
succeeded
partially_succeeded
failed
cancelled
skipped
```

### Checks

Counters must be `>= 0`.

```text
finished_at IS NULL OR started_at IS NOT NULL
finished_at IS NULL OR finished_at >= started_at
status != 'running' OR started_at IS NOT NULL
```

### Foreign keys

```text
crawl_run_id
→ ingestion.crawl_runs(id)
ON DELETE SET NULL

fetch_event_id
→ ingestion.fetch_events(id)
ON DELETE CASCADE

raw_object_id
→ ingestion.raw_objects(id)
ON DELETE SET NULL

parser_version_id
→ ingestion.parser_versions(id)
ON DELETE RESTRICT
```

### Constraints

Prevent duplicate execution identity:

```text
UNIQUE (fetch_event_id, parser_version_id)
```

If future retry semantics require multiple extraction attempts, do not weaken the constraint in this task. Record one extraction run per fetch/parser pair and reflect retries in status/metrics or a future child attempt table.

### Indexes

```text
ix_extraction_runs__parser_version_id_created_at
    (parser_version_id, created_at DESC)

ix_extraction_runs__status_created_at
    (status, created_at DESC)

ix_extraction_runs__crawl_run_id
    (crawl_run_id)
```

---

## 8.6 `ingestion.extracted_records`

Immutable direct-extraction payload before canonical normalization.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `extraction_run_id` | `BIGINT` | No | — | Parent extraction |
| `source_id` | `UUID` | No | — | Source |
| `source_job_id` | `VARCHAR(255)` | No | — | Source identity |
| `fetch_event_id` | `BIGINT` | No | — | Evidence fetch |
| `raw_object_id` | `BIGINT` | Yes | — | Raw reference |
| `record_schema_version` | `VARCHAR(100)` | No | — | Extraction contract |
| `direct_payload_json` | `JSONB` | No | — | Direct/source-neutral record |
| `direct_hash` | `CHAR(64)` | No | — | Deterministic payload hash |
| `processing_status` | `VARCHAR(30)` | No | `'pending'` | Downstream state |
| `rejection_reason` | `TEXT` | Yes | — | Sanitized reason |
| `extracted_at` | `TIMESTAMPTZ` | No | — | Extraction event time |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | DB insertion |

### `processing_status` allowed values

```text
pending
accepted
rejected
quarantined
processed
superseded
```

### Checks

`source_job_id` and `record_schema_version` must not be blank.

`direct_hash` must match lowercase SHA-256.

```text
processing_status IN ('rejected','quarantined')
    OR rejection_reason IS NULL
```

The implementation may instead allow rejection notes for other states if tests/documentation justify it; do not store stack traces or secrets.

JSONB shape:

```sql
jsonb_typeof(direct_payload_json) = 'object'
```

### Foreign keys

```text
extraction_run_id
→ ingestion.extraction_runs(id)
ON DELETE CASCADE

source_id
→ ingestion.sources(id)
ON DELETE RESTRICT

fetch_event_id
→ ingestion.fetch_events(id)
ON DELETE CASCADE

raw_object_id
→ ingestion.raw_objects(id)
ON DELETE SET NULL
```

### Constraints

```text
UNIQUE (extraction_run_id, source_id, source_job_id)
```

This supports one extracted record per source identity per extraction run.

### Indexes

```text
ix_extracted_records__source_identity
    (source_id, source_job_id)

ix_extracted_records__processing_status_created_at
    (processing_status, created_at)

ix_extracted_records__fetch_event_id
    (fetch_event_id)

ix_extracted_records__direct_hash
    (direct_hash)
```

### Mutability

The extraction payload and hash are immutable.

Only downstream processing status and a sanitized rejection reason may change.

---

## 8.7 `ingestion.crawl_errors`

Structured and sanitized crawl/extraction errors.

### Columns

| Column | PostgreSQL type | Null | Default | Notes |
|---|---|---:|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity | Primary key |
| `crawl_run_id` | `UUID` | No | — | Parent run |
| `crawl_task_id` | `BIGINT` | Yes | — | Related task |
| `fetch_event_id` | `BIGINT` | Yes | — | Related fetch |
| `extraction_run_id` | `BIGINT` | Yes | — | Related extraction |
| `source_id` | `UUID` | No | — | Source |
| `stage` | `VARCHAR(30)` | No | — | Pipeline stage |
| `category` | `VARCHAR(50)` | No | — | Error category |
| `error_code` | `VARCHAR(150)` | Yes | — | Stable code |
| `retryable` | `BOOLEAN` | No | `false` | Retry recommendation |
| `severity` | `VARCHAR(20)` | No | `'error'` | Severity |
| `source_job_id` | `VARCHAR(255)` | Yes | — | Known source identity |
| `url` | `TEXT` | Yes | — | Related URL |
| `http_status` | `SMALLINT` | Yes | — | Related status |
| `sanitized_message` | `TEXT` | No | — | Safe error message |
| `details_json` | `JSONB` | No | `'{}'::jsonb` | Safe structured details |
| `occurred_at` | `TIMESTAMPTZ` | No | `now()` | Error time |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | DB insertion |

### `stage` allowed values

```text
policy
discovery
task
fetch
raw_storage
extraction
validation
processing
other
```

### `category` allowed values

```text
robots_disallowed
policy_blocked
http_error
network_error
timeout
invalid_url
invalid_content
parse_error
schema_error
storage_error
database_error
rate_limited
unexpected
```

### `severity` allowed values

```text
info
warning
error
critical
```

### Checks

```text
http_status IS NULL OR http_status BETWEEN 100 AND 599
length(trim(sanitized_message)) > 0
```

At least one contextual link must exist:

```text
crawl_task_id IS NOT NULL
OR fetch_event_id IS NOT NULL
OR extraction_run_id IS NOT NULL
OR url IS NOT NULL
OR source_job_id IS NOT NULL
```

### Foreign keys

```text
crawl_run_id
→ ingestion.crawl_runs(id)
ON DELETE CASCADE

crawl_task_id
→ ingestion.crawl_tasks(id)
ON DELETE SET NULL

fetch_event_id
→ ingestion.fetch_events(id)
ON DELETE SET NULL

extraction_run_id
→ ingestion.extraction_runs(id)
ON DELETE SET NULL

source_id
→ ingestion.sources(id)
ON DELETE RESTRICT
```

### Indexes

```text
ix_crawl_errors__run_occurred_at
    (crawl_run_id, occurred_at)

ix_crawl_errors__source_stage_category
    (source_id, stage, category)

ix_crawl_errors__retryable_occurred_at
    (retryable, occurred_at DESC)

ix_crawl_errors__severity_occurred_at
    (severity, occurred_at DESC)
```

### Security

Never store:

- cookies;
- authorization headers;
- API keys;
- full environment variables;
- raw stack traces containing secrets;
- full private response bodies.

---

# 9. SQLAlchemy implementation requirements

## 9.1 Module structure

Do not put all new models into the existing monolithic `models.py`.

Recommended structure:

```text
src/it_labor_market_intelligence/database/
├── base.py
├── models/
│   ├── __init__.py
│   ├── system.py
│   └── ingestion.py
├── repositories/
└── session.py
```

A less disruptive structure is acceptable, but models must remain organized by schema.

## 9.2 Metadata and schemas

Models must specify schemas explicitly:

```python
__table_args__ = {"schema": "ingestion"}
```

or a tuple containing constraints followed by the schema dictionary.

Foreign-key strings must include schema:

```python
ForeignKey("ingestion.sources.id")
```

## 9.3 PostgreSQL types

Use dialect types where required:

```python
from sqlalchemy.dialects.postgresql import JSONB, UUID
```

Use `BigInteger` with identity semantics for high-volume IDs.

Use `server_default`, not only Python defaults, for database-required defaults.

Examples:

```python
server_default=sa.text("gen_random_uuid()")
server_default=sa.text("now()")
server_default=sa.text("'{}'::jsonb")
server_default=sa.text("false")
```

## 9.4 Relationships

Relationships may be added where useful, but:

- do not create large eager-loading graphs;
- default to lazy/select behavior compatible with current repository patterns;
- use explicit cascade rules;
- do not allow deleting a source to silently delete historical events unless the FK specification says `CASCADE`.

## 9.5 Append-only entities

Do not add ordinary update/delete repository methods for:

```text
system.audit_events
ingestion.raw_objects
ingestion.fetch_events
ingestion.extracted_records payload fields
ingestion.crawl_errors
```

---

# 10. Alembic requirements

## 10.1 Explicit DDL

Each migration must explicitly call operations such as:

```python
op.execute("CREATE SCHEMA IF NOT EXISTS ...")
op.create_table(...)
op.create_index(...)
op.create_check_constraint(...)
op.create_foreign_key(...)
```

No metadata-driven create/drop calls.

## 10.2 Downgrade

Downgrade must:

- drop indexes before tables where Alembic requires it;
- drop child tables before parents;
- drop schemas only after all owned objects are removed;
- never use `CASCADE`;
- never drop unrelated legacy Phase 3 tables.

Migration 002 downgrade removes only Migration 002 objects.

Migration 001 downgrade removes only Migration 001 objects after Migration 002 has already been downgraded.

## 10.3 Migration idempotency expectations

Alembic migrations are not required to be safely callable twice outside Alembic's versioning, but:

- `upgrade head` from an empty PostgreSQL database must succeed;
- running `upgrade head` again must be a no-op through Alembic revision tracking;
- `downgrade base` must remove only objects introduced by these migrations;
- `upgrade head` after `downgrade base` must succeed again.

## 10.4 Legacy migration handling

The existing migration:

```text
alembic/versions/20260724_0001_phase3_schema.py
```

uses metadata-driven `create_all()` and `drop_all()`.

Codex must not silently rewrite history without documenting the decision.

Choose one of these approaches and explain it in the PR:

### Preferred for the current pre-production repository

Replace the unsafe baseline with a clean explicit migration chain if there is no production database relying on the old revision.

Requirements:

- preserve a clear migration history;
- ensure all tests recreate databases from scratch;
- document that existing pilot data must be reimported;
- do not retain an unsafe migration as an ancestor of the new production baseline.

### Alternative

Keep the legacy revision and add the new V1 migrations after it.

This is acceptable only if:

- the legacy tables are not dropped;
- new V1 tables use new schemas;
- tests clearly distinguish legacy prototype and V1 objects;
- documentation states that a future cleanup migration is required.

Do not invent a destructive migration that drops legacy tables automatically in this task.

---

# 11. Security, grants, and RLS

## 11.1 General access model

These schemas are private:

```text
system
ingestion
```

They must not be directly readable or writable by Supabase `anon`.

Expected operational access:

- database owner/migration role: full access;
- trusted backend/service role: controlled read/write;
- anonymous frontend: no direct access;
- authenticated frontend users: no direct access in this phase.

## 11.2 Migration behavior

Because local PostgreSQL may not have Supabase roles such as `anon`, `authenticated`, or `service_role`, migrations must not fail when those roles are absent.

Implement one of:

1. a separate Supabase-only grants migration later; or
2. conditional `DO $$ ... $$` role checks.

For Migration 001 and 002, the preferred behavior is:

- create schemas/tables;
- revoke public schema/table privileges where safe;
- do not create RLS policies referencing unavailable Supabase roles;
- document exact future Supabase grants.

At minimum:

```sql
REVOKE ALL ON SCHEMA system FROM PUBLIC;
REVOKE ALL ON SCHEMA ingestion FROM PUBLIC;
```

Do not revoke permissions required by the database owner.

## 11.3 RLS

RLS may be enabled in a later Supabase deployment migration.

If Codex enables RLS now:

- CI must create compatible roles or use owner bypass;
- tests must prove anonymous roles cannot access data;
- service access must remain functional.

The simpler accepted implementation is to defer RLS policy creation and document it as the next security migration.

---

# 12. Retention behavior

Migration 001 and 002 define retention metadata but do not implement destructive scheduled deletion.

Default recommended policies to seed only if the repository already has a safe seeding mechanism:

| Data class | Default |
|---|---:|
| `raw_html` | 30 days |
| `raw_json` | 90 days |
| `structured_evidence` | 365 days |
| `failed_response_body` | 14 days |
| `fetch_metadata` | 180 days |
| `extracted_record` | no automatic deletion |
| `crawl_error` | 180 days |
| `audit_event` | no automatic deletion |

Do not hard-code seed rows into schema migrations unless project conventions allow deterministic reference-data seeding.

No cleanup scheduler is in scope.

---

# 13. Integration tests

Create PostgreSQL-specific tests.

Recommended location:

```text
tests/integration/database/
```

## 13.1 Required test categories

### A. Empty-database migration

- Start PostgreSQL 16.
- Run `alembic upgrade head`.
- Assert schemas exist.
- Assert all 14 V1 tables exist.
- Assert migration revision is current.

### B. Downgrade/upgrade smoke test

- Upgrade to head.
- Downgrade Migration 002.
- Verify Migration 001 tables remain.
- Re-upgrade to head.
- Optionally downgrade to base in an isolated database.
- Verify clean re-upgrade succeeds.

### C. Constraints

Test at least:

- duplicate source slug rejected;
- source cannot be enabled unless approved;
- invalid source slug rejected;
- negative request limits rejected;
- invalid crawl status rejected;
- negative counters rejected;
- task requires URL or source job ID;
- raw object SHA must be valid;
- inline storage requires inline payload;
- external storage requires object key;
- duplicate raw SHA rejected;
- successful fetch requires 2xx/3xx HTTP status;
- extraction run uniqueness for fetch/parser;
- extracted record uniqueness per extraction run/source identity;
- invalid direct hash rejected;
- crawl error requires contextual linkage;
- timestamps reject impossible ordering.

### D. Foreign keys and deletion behavior

Test:

- source with crawl runs cannot be deleted due to `RESTRICT`;
- deleting a crawl run deletes its crawl tasks;
- deleting a crawl run deletes fetch events and crawl errors;
- deleting a source policy sets nullable references where specified;
- deleting a raw object sets nullable references to null;
- deleting an extraction run deletes extracted records.

### E. JSONB behavior

Test:

- JSONB objects/arrays round-trip correctly;
- source policy path fields reject non-array JSON;
- direct payload rejects non-object JSON.

### F. Repository/model smoke tests

- Insert and query each major entity through SQLAlchemy.
- Confirm UUID server defaults work.
- Confirm identity IDs are generated by PostgreSQL.
- Confirm schema-qualified tables are used.

---

# 14. CI requirements

Update `.github/workflows/ci.yml`.

## 14.1 PostgreSQL service

Add PostgreSQL 16 service:

```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_DB: it_labor_market_test
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - 5432:5432
    options: >-
      --health-cmd "pg_isready -U postgres -d it_labor_market_test"
      --health-interval 5s
      --health-timeout 5s
      --health-retries 10
```

## 14.2 Environment

Set:

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/it_labor_market_test
```

## 14.3 CI sequence

At minimum:

```text
install dependencies
alembic upgrade head
run PostgreSQL integration tests
run complete pytest suite
run Ruff
run Black or Ruff format check according to current repo convention
run MyPy
```

The current workflow uses Black while the README also references Ruff formatting. Preserve the currently enforced repository convention or consolidate it in a separate clearly scoped change.

## 14.4 Migration verification command

Add a CI step that proves:

```text
alembic upgrade head
alembic current
```

A downgrade/upgrade smoke test may run inside pytest to avoid modifying the shared CI database unexpectedly.

---

# 15. Documentation changes

Update or create:

```text
docs/DATABASE_V1_FOUNDATION.md
docs/DATABASE_DESIGN.md
docs/DATA_IMPORT_RUNBOOK.md
README.md
```

Documentation must explain:

- schemas;
- table responsibilities;
- identity strategy;
- raw-object storage strategy;
- migration commands;
- local PostgreSQL setup;
- retention metadata;
- security boundaries;
- legacy Phase 3 migration decision;
- how pilot data is reimported if baseline is reset.

Do not claim that full Database V1 is complete. Only Migration 001 and 002 are implemented.

---

# 16. Acceptance criteria

The task is complete only when all conditions below pass.

## Schema and migration

- [ ] `system` schema exists.
- [ ] `ingestion` schema exists.
- [ ] `pgcrypto` exists.
- [ ] Migration 001 creates exactly the specified foundation objects.
- [ ] Migration 002 creates exactly the specified ingestion objects.
- [ ] Migrations contain no `Base.metadata.create_all()`.
- [ ] Migrations contain no `Base.metadata.drop_all()`.
- [ ] No `DROP ... CASCADE`.
- [ ] All foreign keys include schema-qualified references.
- [ ] All specified checks, unique constraints, and indexes exist.
- [ ] `alembic upgrade head` succeeds on PostgreSQL 16.
- [ ] downgrade/upgrade smoke tests succeed.
- [ ] Existing unrelated tables are not dropped.

## Models

- [ ] SQLAlchemy models use explicit schemas.
- [ ] PostgreSQL columns use JSONB and UUID types appropriately.
- [ ] Server defaults are present.
- [ ] Append-only entities are not exposed through ordinary destructive repositories.
- [ ] Existing application imports remain valid or are updated safely.

## Tests and CI

- [ ] PostgreSQL integration tests exist.
- [ ] Constraint tests exist.
- [ ] Foreign-key behavior is tested.
- [ ] GitHub Actions starts PostgreSQL 16.
- [ ] GitHub Actions runs Alembic before tests.
- [ ] Existing test suite still passes.
- [ ] Ruff passes.
- [ ] Formatting check passes.
- [ ] MyPy passes, or any environment-specific blocker is documented with evidence.

## Security and documentation

- [ ] Public access to `system` and `ingestion` schemas is revoked or explicitly deferred with a documented Supabase migration.
- [ ] No secret values appear in configuration JSON, audit metadata, errors, request headers, or response headers.
- [ ] Retention behavior is documented.
- [ ] Legacy migration handling is documented.
- [ ] README commands are accurate.

---

# 17. Out of scope

Do not implement:

```text
core.companies
core.job_postings
core.locations
core.salary_offers
taxonomy tables
history.job_observations
quality.field_evidence
duplicate candidate algorithms
analytics facts
daily aggregates
serving views
Supabase frontend policies
user accounts
resumes
applications
recommendations
embeddings
LLM enrichment
crawler scheduling
raw cleanup jobs
object-storage upload clients
dashboard changes
```

Do not refactor the entire repository.

Do not rewrite crawler adapters unless required to keep code compiling after model/config changes.

Do not migrate pilot records into canonical V1 tables because those tables are not part of Migration 001 or 002.

---

# 18. Codex implementation workflow

Codex should follow this order:

1. Read:
   - `AGENTS_RULES.md`
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/DATA_SCHEMA.md`
   - `docs/DATA_SCHEMA_AUDIT.md`
   - `docs/DATABASE_DESIGN.md`
   - existing Alembic environment and migration files
   - current SQLAlchemy models and tests
2. Decide and document legacy migration handling.
3. Implement Migration 001.
4. Implement Migration 002.
5. Add or reorganize SQLAlchemy models.
6. Add PostgreSQL integration tests.
7. Update GitHub Actions.
8. Update documentation.
9. Run all required checks.
10. Produce a summary containing:
    - files changed;
    - migration design;
    - legacy migration decision;
    - test results;
    - unresolved risks;
    - explicit confirmation that no out-of-scope tables were added.

---

# 19. Review checklist for the human reviewer

## Migration safety

- [ ] Old migration history was not silently rewritten without explanation.
- [ ] Downgrade does not remove unrelated data.
- [ ] DDL is explicit and readable.
- [ ] Constraint/index names follow conventions.
- [ ] No PostgreSQL-native enum lock-in.
- [ ] No generic JSON columns.

## Data lineage

- [ ] CrawlRun links source, policy, parser, and pipeline versions.
- [ ] FetchEvent links task/run/source/raw object.
- [ ] ExtractionRun links fetch/raw/parser.
- [ ] ExtractedRecord links extraction/fetch/source/raw evidence.
- [ ] CrawlError links the relevant stage and entities.

## Cost and retention

- [ ] Raw payload duplication is prevented by SHA-256.
- [ ] Large payloads are external references.
- [ ] Expiry metadata is queryable.
- [ ] No cleanup is executed prematurely.

## Security

- [ ] Secrets cannot be placed in documented JSON fields.
- [ ] Ingestion schemas are not exposed to anonymous clients.
- [ ] Error text is explicitly sanitized.
- [ ] Audit records are append-only.

## Scope

- [ ] No canonical/history/analytics tables were added.
- [ ] No unrelated API/dashboard refactor occurred.
- [ ] Existing tests were not deleted merely to make CI pass.

---

# 20. Expected deliverables

Codex must deliver:

```text
1. Explicit Alembic Migration 001
2. Explicit Alembic Migration 002
3. SQLAlchemy system models
4. SQLAlchemy ingestion models
5. PostgreSQL integration tests
6. Migration smoke tests
7. Updated GitHub Actions PostgreSQL service
8. Updated database documentation
9. Implementation summary and unresolved-risk report
```

The implementation must remain reviewable as one focused database-foundation pull request.
