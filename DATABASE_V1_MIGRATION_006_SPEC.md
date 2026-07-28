# Database V1 — Migration 006 Serving, Dashboard & Job Search API

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`  
**Database:** PostgreSQL 16 / Supabase-compatible PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration:** Alembic  
**Scope:** stable read/query contracts for website job search, job details, and labor-market dashboards.

---

## 1. Goal

Migration 006 adds two schemas:

```text
serving  -- private cache and internal views
api      -- exposed function-only API contract
```

It must support:

- current job cards and job details;
- PostgreSQL full-text job search;
- filters for source, company, location, occupation, skill, employment type,
  seniority, work mode, status, posting date, and salary;
- market, company, location, occupation, skill, and salary dashboard queries;
- versioned PostgreSQL RPC functions suitable for Supabase/PostgREST.

The `api` schema must contain functions only. Internal tables and views remain
private.

---

## 2. Non-negotiable rules

1. Explicit Alembic DDL only.
2. No `Base.metadata.create_all()`, `drop_all()`, or `DROP ... CASCADE`.
3. Use schema-qualified names, `TIMESTAMPTZ`, `JSONB`, arrays, and `TSVECTOR`.
4. No PostgreSQL native enums.
5. Do not expose `serving`, `analytics`, `history`, `quality`, `core`,
   `taxonomy`, `ingestion`, or `system` through Supabase Data API.
6. Public functions use `_v1` suffix, `SECURITY DEFINER`, `STABLE`, fixed
   `search_path`, schema-qualified SQL, and no dynamic SQL.
7. Revoke `PUBLIC` execute privileges before exact grants.
8. Client roles receive function execution only.
9. Search documents must be generated from the current history observation.
10. Stale documents must never be returned.
11. Search uses explicit `simple` text configuration and a GIN `TSVECTOR` index.
12. Salary filters never mix currency, period, or tax basis.
13. Unknown salary stays null, never zero.
14. Bound search limits, offsets, and dashboard date ranges.
15. Existing Migration 001–005 tests remain green.
16. Frontend, production refresh workers, users, resumes, recommendations,
    embeddings, vector search, LLM enrichment, and crawler changes are out of
    scope.

---

## 3. Migration identity

Suggested revision:

```text
20260727_0006
```

Required:

```text
down_revision = "20260727_0005"
```

Create:

```sql
CREATE SCHEMA IF NOT EXISTS serving;
CREATE SCHEMA IF NOT EXISTS api;

REVOKE ALL ON SCHEMA serving FROM PUBLIC;
REVOKE ALL ON SCHEMA api FROM PUBLIC;
```

---

## 4. Exact inventory

### Tables — 3

```text
serving.refresh_runs
serving.job_search_documents
serving.job_search_salary_offers
```

### Internal views — 7

```text
serving.v_current_job_cards
serving.v_market_overview_daily
serving.v_company_hiring_daily
serving.v_location_demand_daily
serving.v_occupation_demand_daily
serving.v_skill_demand_daily
serving.v_salary_metrics_daily
```

### Public API functions — 8

```text
api.search_jobs_v1
api.get_job_v1
api.market_overview_v1
api.company_hiring_v1
api.location_demand_v1
api.occupation_demand_v1
api.skill_demand_v1
api.salary_metrics_v1
```

No materialized views are required. Analytics daily tables are already
pre-aggregated; regular views avoid a second refresh lifecycle.

---

# 5. `serving.refresh_runs`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `run_type` | `VARCHAR(30)` | No | — |
| `status` | `VARCHAR(30)` | No | `'pending'` |
| `document_version` | `VARCHAR(100)` | No | — |
| `source_id` | `UUID` | Yes | — |
| `watermark_observed_at` | `TIMESTAMPTZ` | Yes | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `rows_upserted` | `BIGINT` | No | `0` |
| `rows_deleted` | `BIGINT` | No | `0` |
| `salary_rows_replaced` | `BIGINT` | No | `0` |
| `error_count` | `INTEGER` | No | `0` |
| `configuration_json` | `JSONB` | No | `'{}'::jsonb` |
| `metrics_json` | `JSONB` | No | `'{}'::jsonb` |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed:

```text
run_type: incremental, backfill, rebuild, validation, test
status: pending, running, succeeded, partially_succeeded, failed, cancelled
```

FK:

```text
source_id → ingestion.sources(id) ON DELETE SET NULL
```

Checks:

- document version is nonblank;
- counters are nonnegative;
- JSONB values are objects;
- finish is not earlier than start;
- lifecycle matrix:

```text
pending: started_at NULL, finished_at NULL
running: started_at NOT NULL, finished_at NULL
terminal: started_at NOT NULL, finished_at NOT NULL
```

Indexes:

```text
(status, created_at DESC)
(source_id, created_at DESC) WHERE source_id IS NOT NULL
(document_version, created_at DESC)
```

Once referenced, `source_id` and `document_version` are immutable.

---

# 6. `serving.job_search_documents`

One current search document per source posting.

The loader supplies only:

```text
job_posting_id
observation_id
refresh_run_id
document_version
```

A database trigger derives all copied fields.

## Columns

```text
job_posting_id UUID PRIMARY KEY
observation_id BIGINT NOT NULL UNIQUE
source_id UUID NOT NULL
source_job_id VARCHAR(255) NOT NULL
company_id UUID NULL
source_url TEXT NOT NULL
canonical_url TEXT NULL
title TEXT NOT NULL
title_normalized TEXT NULL
company_name TEXT NULL
description_excerpt TEXT NULL
employment_type_code VARCHAR(30) NULL
seniority_level_code VARCHAR(30) NULL
work_mode VARCHAR(30) NULL
status VARCHAR(20) NOT NULL
posted_at TIMESTAMPTZ NULL
expires_at TIMESTAMPTZ NULL
first_seen_at TIMESTAMPTZ NOT NULL
last_seen_at TIMESTAMPTZ NOT NULL
location_ids UUID[] NOT NULL DEFAULT '{}'
location_labels TEXT[] NOT NULL DEFAULT '{}'
locations_json JSONB NOT NULL DEFAULT '[]'
occupation_ids UUID[] NOT NULL DEFAULT '{}'
occupation_names TEXT[] NOT NULL DEFAULT '{}'
occupations_json JSONB NOT NULL DEFAULT '[]'
skill_ids UUID[] NOT NULL DEFAULT '{}'
skill_names TEXT[] NOT NULL DEFAULT '{}'
skills_json JSONB NOT NULL DEFAULT '[]'
salary_disclosed BOOLEAN NOT NULL DEFAULT false
search_vector TSVECTOR NOT NULL
refresh_run_id UUID NOT NULL
document_version VARCHAR(100) NOT NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

FKs:

```text
job_posting_id → core.job_postings(id) RESTRICT
observation_id → history.job_observations(id) RESTRICT
source_id → ingestion.sources(id) RESTRICT
company_id → core.companies(id) RESTRICT
refresh_run_id → serving.refresh_runs(id) RESTRICT
```

Checks:

- source job ID/title nonblank;
- URLs valid;
- excerpt at most 1200 characters;
- JSON values are arrays;
- arrays contain no nulls;
- ID/name array cardinalities match;
- `last_seen_at >= first_seen_at`;
- expiry is not earlier than posting;
- document version nonblank.

## Builder trigger

Create:

```text
serving.build_job_search_document()
```

Attach `BEFORE INSERT OR UPDATE`.

Required behavior:

1. Reject changing `job_posting_id`.
2. Lock `core.job_postings` row.
3. Require `current_observation_id = NEW.observation_id`.
4. Require the observation belongs to the same job/source.
5. Require refresh run source is null or matches observation source.
6. Require document version equals refresh-run document version.
7. Populate scalar fields from history/current core state.
8. Prefer canonical company name; fall back to historical raw company name.
9. Include description excerpt only when text exists and is not redacted/expired.
10. Build deterministic location, occupation, and skill arrays/JSON from
    historical child rows.
11. Set salary-disclosed from historical salary rows.
12. Generate weighted search vector:

```text
A: title and normalized title
B: company, occupations, skills
C: locations
D: description excerpt
```

Use explicit:

```sql
to_tsvector('simple', ...)
```

13. Set `updated_at = now()`.
14. Raise SQLSTATE `23514` on mismatch.

Even after locking, current views must filter:

```text
document.observation_id = core.job_postings.current_observation_id
```

so stale documents disappear until refreshed.

## Indexes

```text
GIN(search_vector)
GIN(skill_ids)
GIN(occupation_ids)
GIN(location_ids)
(status, posted_at DESC, job_posting_id)
(source_id, posted_at DESC)
(company_id, posted_at DESC) WHERE company_id IS NOT NULL
(employment_type_code, posted_at DESC)
(seniority_level_code, posted_at DESC)
(work_mode, posted_at DESC)
(refresh_run_id)
```

---

# 7. `serving.job_search_salary_offers`

Current searchable salary components.

```text
id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
job_posting_id UUID NOT NULL
observation_salary_id BIGINT NOT NULL UNIQUE
currency CHAR(3) NULL
period VARCHAR(20) NULL
tax_basis VARCHAR(20) NOT NULL
compensation_type VARCHAR(30) NOT NULL
is_disclosed BOOLEAN NOT NULL
is_negotiable BOOLEAN NOT NULL
is_estimated BOOLEAN NOT NULL
amount_min NUMERIC(20,2) NULL
amount_max NUMERIC(20,2) NULL
amount_exact NUMERIC(20,2) NULL
normalized_monthly_min NUMERIC(20,2) NULL
normalized_monthly_max NUMERIC(20,2) NULL
normalized_annual_min NUMERIC(20,2) NULL
normalized_annual_max NUMERIC(20,2) NULL
refresh_run_id UUID NOT NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

FKs:

```text
job_posting_id → serving.job_search_documents(job_posting_id) CASCADE
observation_salary_id → history.observation_salaries(id) RESTRICT
refresh_run_id → serving.refresh_runs(id) RESTRICT
```

Apply salary checks compatible with history.

Create `serving.validate_search_salary_offer()` trigger:

- historical salary must belong to parent document observation;
- all copied fields must equal history;
- refresh run must equal parent document refresh run;
- set updated time;
- reject mismatch with SQLSTATE `23514`.

Indexes:

```text
(job_posting_id)
(currency, period, tax_basis)
(currency, period, tax_basis, amount_min, amount_max) WHERE is_disclosed
(currency, normalized_monthly_min, normalized_monthly_max)
(refresh_run_id)
```

---

# 8. Internal views

Do not grant these views to client roles.

## `serving.v_current_job_cards`

Columns:

```text
job_posting_id, observation_id, source_id, source_slug, source_display_name,
source_job_id, company_id, source_url, canonical_url, title, title_normalized,
company_name, description_excerpt, employment_type_code,
seniority_level_code, work_mode, status, posted_at, expires_at, first_seen_at,
last_seen_at, location_ids, location_labels, locations_json, occupation_ids,
occupation_names, occupations_json, skill_ids, skill_names, skills_json,
salary_disclosed, search_vector, document_version, updated_at
```

Must filter current observation equality.

## Daily views

Create stable dimension-name views over Migration 005 analytics tables:

```text
v_market_overview_daily
v_company_hiring_daily
v_location_demand_daily
v_occupation_demand_daily
v_skill_demand_daily
v_salary_metrics_daily
```

They must expose operational UUIDs/names, not analytics surrogate keys.

Each view includes:

```text
metric_date
source_id/source_slug where applicable
dimension operational ID and label
metric columns
calculation_version
calculated_at
```

Unknown analytics location/occupation rows expose null operational IDs and
documented labels.

---

# 9. API function security

Every API function:

```text
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, api, serving
```

Use schema-qualified references and no dynamic SQL.

For exact signatures:

```sql
REVOKE ALL ON FUNCTION api.<signature> FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.<signature>
TO anon, authenticated, service_role;
```

Invalid parameters raise SQLSTATE `22023`.

---

# 10. `api.search_jobs_v1`

## Signature

```sql
api.search_jobs_v1(
  p_query TEXT DEFAULT NULL,
  p_source_ids UUID[] DEFAULT NULL,
  p_company_ids UUID[] DEFAULT NULL,
  p_location_ids UUID[] DEFAULT NULL,
  p_occupation_ids UUID[] DEFAULT NULL,
  p_skill_ids UUID[] DEFAULT NULL,
  p_employment_types TEXT[] DEFAULT NULL,
  p_seniority_levels TEXT[] DEFAULT NULL,
  p_work_modes TEXT[] DEFAULT NULL,
  p_statuses TEXT[] DEFAULT ARRAY['active']::text[],
  p_posted_after TIMESTAMPTZ DEFAULT NULL,
  p_salary_currency TEXT DEFAULT NULL,
  p_salary_period TEXT DEFAULT NULL,
  p_salary_tax_basis TEXT DEFAULT NULL,
  p_salary_min NUMERIC DEFAULT NULL,
  p_salary_max NUMERIC DEFAULT NULL,
  p_sort TEXT DEFAULT 'relevance',
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0
)
```

Return:

```text
job_posting_id UUID
observation_id BIGINT
title TEXT
company_id UUID
company_name TEXT
source_id UUID
source_slug TEXT
source_display_name TEXT
source_url TEXT
canonical_url TEXT
status TEXT
posted_at TIMESTAMPTZ
expires_at TIMESTAMPTZ
first_seen_at TIMESTAMPTZ
last_seen_at TIMESTAMPTZ
employment_type_code TEXT
seniority_level_code TEXT
work_mode TEXT
location_labels TEXT[]
occupation_names TEXT[]
skill_names TEXT[]
salary_disclosed BOOLEAN
salary_offers_json JSONB
rank_score REAL
total_count BIGINT
```

Search:

```sql
websearch_to_tsquery('simple', p_query)
search_vector @@ query
ts_rank_cd(search_vector, query)
```

Blank query bypasses FTS and uses rank `0`.

Location/occupation/skill arrays use **any-match** semantics.

Salary amount filters require currency and period. Match one disclosed salary
row whose range overlaps the requested range:

```text
lower = COALESCE(amount_min, amount_exact, amount_max)
upper = COALESCE(amount_max, amount_exact, amount_min)
```

Allowed sort:

```text
relevance
newest
oldest
```

Limits:

```text
1 <= limit <= 50
0 <= offset <= 1000
salary values nonnegative
minimum <= maximum
```

Return `total_count` before pagination. Salary JSON ordering must be
deterministic.

---

# 11. `api.get_job_v1`

Signature:

```sql
api.get_job_v1(p_job_posting_id UUID)
```

Return zero or one current job with:

```text
all card fields
description_excerpt
locations_json
occupations_json
skills_json
salary_offers_json
document_version
updated_at
```

Do not return raw HTML, ingestion payloads, quality review notes, internal
hashes, crawler errors, or authorization data.

---

# 12. Dashboard RPC contracts

Common defaults:

```text
start_date = current_date - 30
end_date = current_date
```

Validation:

```text
end >= start
date window <= 366 days
1 <= limit <= 1000
0 <= offset <= 5000
```

## `api.market_overview_v1`

Filters:

```text
date range
source IDs
employment types
seniority levels
work modes
```

Return one aggregated row per date with active/new/closed/expired/removed/
reactivated/content-changed/salary-disclosed/remote counts.

## `api.company_hiring_v1`

Filters:

```text
date range, source IDs, company IDs, limit, offset
```

Return daily company/source rows.

## `api.location_demand_v1`

Filters:

```text
date range, source IDs, location IDs, work modes,
include_unknown, limit, offset
```

## `api.occupation_demand_v1`

Filters:

```text
date range, source IDs, occupation IDs,
include_unknown, limit, offset
```

## `api.skill_demand_v1`

Filters:

```text
date range, source IDs, skill IDs, requirement types, limit, offset
```

## `api.salary_metrics_v1`

Filters:

```text
date range, source IDs, occupation IDs, location IDs,
currency, period, tax basis, include_unknown_dimensions, limit, offset
```

Never combine currency, period, or tax basis.

All functions return operational IDs and labels, never analytics surrogate keys.

---

# 13. Grants, roles, and RLS

## CI roles

Before Migration 006 in local CI, create these `NOLOGIN` roles when absent:

```text
anon
authenticated
service_role
```

Do not create them inside production Alembic migration.

## Grants

```sql
GRANT USAGE ON SCHEMA api TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA serving TO service_role;
```

Do not grant `serving` usage to `anon` or `authenticated`.

Enable RLS on all three serving tables. Create no client policies.

Grant `service_role` cache DML and required sequence usage.

Revoke all view privileges from:

```text
PUBLIC, anon, authenticated, service_role
```

Functions access views through definer privileges.

Grant exact API function execution only.

## Supabase deployment setting

Expose only:

```text
api
```

Do not expose `serving` or internal schemas. Reload the PostgREST schema cache
after changing exposed schemas or function signatures.

---

# 14. Refresh semantics

Migration 006 defines storage and API contracts, not the production worker.

Future transaction:

```text
1. start serving refresh run
2. find changed current observations
3. upsert search documents
4. replace salary rows for affected documents
5. update counters
6. mark succeeded
7. commit
```

Source-scoped runs may refresh only their source. Global runs may refresh all.

When core advances before serving refresh, stale documents remain stored but
are hidden by `v_current_job_cards`.

---

# 15. SQLAlchemy

Add:

```text
src/it_labor_market_intelligence/database/v1_models/serving.py
```

Models:

```text
ServingRefreshRun
JobSearchDocument
JobSearchSalaryOffer
```

Use explicit schema, schema-qualified FKs, PostgreSQL UUID, ARRAY, JSONB, and
TSVECTOR.

Views, triggers, grants, and API functions remain Alembic-authoritative.

---

# 16. Upgrade and downgrade

Upgrade:

1. create schemas and revoke public access;
2. create refresh runs;
3. create search documents and builder trigger;
4. create salary rows and validation trigger;
5. create indexes and refresh-lineage protection;
6. enable RLS;
7. create seven internal views;
8. create eight API functions;
9. revoke defaults and apply exact grants.

Downgrade:

1. revoke function execution;
2. drop eight functions using exact signatures;
3. drop seven views;
4. drop triggers/functions;
5. drop salary rows, documents, refresh runs;
6. drop `api`;
7. drop `serving`.

No `CASCADE`. Migration 001–005 remain untouched.

Before production downgrade, remove `api` from Supabase exposed schemas or
coordinate deployment to avoid a missing PostgREST schema.

---

# 17. PostgreSQL integration tests

Create:

```text
tests/integration/database/test_database_v1_serving.py
```

Required coverage:

### Inventory

- two schemas;
- three serving tables;
- seven serving views;
- `api` has no tables/views;
- exactly eight `_v1` functions;
- Alembic head 006.

### Document builder

- derives scalar fields, arrays, JSON, excerpt, salary flag, and search vector;
- deterministic ordering;
- redacted descriptions not exposed;
- wrong/noncurrent observation rejected;
- source/version refresh mismatch rejected;
- global refresh accepted;
- job identity immutable.

### Current safety and concurrency

- stale document hidden after current observation advances;
- refreshed current document returns;
- two-connection test serializes document refresh and current-observation
  update using bounded timeouts.

### Salary rows

- correct lineage accepted;
- cross-observation and copied-field mismatch rejected;
- refresh run matches parent;
- cache deletion never alters history.

### Search

- title/company/skill/occupation/location terms searchable;
- title match ranks above description-only match;
- punctuation and quoted web-style input do not error;
- blank query accepted;
- stale rows excluded;
- active default and status override;
- deterministic sorting and total count;
- every filter works;
- salary boundaries remain separate;
- invalid limits/ranges/sort rejected.

### Job detail

- one current row;
- deterministic salary/detail JSON;
- no private/raw fields;
- stale document returns zero.

### Dashboard

- inclusive dates;
- filters work;
- no surrogate keys;
- unknown-dimension flags work;
- salary categories remain separate;
- oversized date windows/pagination rejected.

### Security

Using `anon` and `authenticated`:

- execute API functions;
- cannot use/select/write serving objects.

Using `service_role`:

- manage serving cache;
- execute API functions.

Inspect functions:

```text
SECURITY DEFINER
STABLE
fixed search_path
PUBLIC has no execute
```

Assert RLS enabled and no client policies.

### Indexes

Verify GIN search/array indexes and salary/date indexes exist.

### Downgrade/re-upgrade

Downgrade to 005 removes only `api` and `serving`; re-upgrade succeeds.

CI runs migration tests, full pytest, Ruff, Black, and MyPy.

---

# 18. Documentation

Create:

```text
docs/DATABASE_V1_SERVING_API.md
```

Update:

```text
README.md
docs/API_REFERENCE.md
docs/DATABASE_DESIGN.md
docs/DATABASE_V1_ANALYTICS.md
docs/DATA_SCHEMA.md
docs/DATA_IMPORT_RUNBOOK.md
```

Document schema boundary, RPC signatures, return fields, search ranking,
filters, pagination, salary overlap, stale-document safety, refresh workflow,
Supabase exposure, grants/RLS, contract versioning, and downgrade procedure.

---

# 19. Acceptance checklist

- [ ] Direct child of Migration 005.
- [ ] Three tables, seven views, eight API functions.
- [ ] `api` contains functions only.
- [ ] Search documents derive from current history.
- [ ] Stale documents are hidden.
- [ ] Weighted `simple` FTS and GIN index.
- [ ] Salary lineage and category separation.
- [ ] All public functions are versioned and security hardened.
- [ ] Client roles receive execute-only access.
- [ ] Serving tables have RLS.
- [ ] No internal surrogate/private data exposed.
- [ ] Limits and date windows bounded.
- [ ] Safe downgrade/re-upgrade.
- [ ] PostgreSQL tests, pytest, Ruff, Black, and MyPy pass.
- [ ] No frontend, scheduler, user, recommendation, vector, LLM, crawler, or
      importer work added.

---

# 20. Codex prompt

```text
Read AGENT_RULES.md and DATABASE_V1_MIGRATION_006_SPEC.md.

Confirm the current branch is main and pull the latest origin/main.

Create:
feat/database-v1-migration-006-serving-api

Implement Database V1 Migration 006 exactly as specified.

Create the private serving schema and the exposed function-only api schema.
Add the current job-search cache, serving salary rows, internal analytics views,
weighted PostgreSQL full-text search, and eight versioned SECURITY DEFINER RPC
functions.

Add schema-qualified SQLAlchemy models for serving tables, PostgreSQL
integration tests for lineage, stale-document hiding, full-text search,
filters, dashboard functions, grants, RLS, and concurrent current-observation
updates.

The api schema must contain functions only. Do not grant anon or authenticated
direct access to serving tables or views. Use exact function grants and fixed
safe search paths.

Update CI so local PostgreSQL creates NOLOGIN anon, authenticated, and
service_role roles before Migration 006 is applied.

Do not implement frontend pages, dashboards, a production refresh scheduler,
webhooks, users, resumes, recommendations, embeddings, semantic/vector search,
LLM enrichment, forecasting, crawler changes, or canonical importer changes.

Run PostgreSQL migration and downgrade/re-upgrade tests, full pytest, Ruff,
Black, and MyPy.

Push the branch and create a draft pull request into main. Do not merge.
Return the PR link, final commit, table/view/function counts, and final CI
status.
```
