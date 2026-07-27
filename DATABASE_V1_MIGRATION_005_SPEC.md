# Database V1 — Migration 005 Analytics Warehouse & Daily Aggregates

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`  
**Database:** PostgreSQL 16 / Supabase-compatible PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration:** Alembic  
**Scope:** private analytics warehouse, observation facts, conformed dimensions, and rebuildable daily aggregates.

---

## 1. Goal

Migration 005 adds the private `analytics` schema. It turns immutable history into storage suitable for labor-market dashboards and reports.

It must support:

- active, new, closed, expired, removed, and reactivated posting counts;
- skill, occupation, company, location, work-mode, and source trends;
- disclosed salary statistics without mixing currencies, periods, or tax bases;
- idempotent fact loading;
- recalculation of old dates when late data arrives;
- traceability to the analytics refresh that produced each row.

It does not implement the production ETL scheduler, serving views, RPC, RLS, dashboards, forecasting, recommendations, users, resumes, embeddings, or LLM features.

---

## 2. Rules

1. Explicit Alembic DDL only.
2. No `Base.metadata.create_all()`, `drop_all()`, or `DROP ... CASCADE`.
3. Use schema-qualified names, `TIMESTAMPTZ`, `DATE`, and PostgreSQL `JSONB`.
4. No native PostgreSQL enums.
5. Facts derive from `history`, not fetch/request counts.
6. One history row may create only one corresponding fact row.
7. Daily aggregates are mutable and rebuildable.
8. Late data must be able to recalculate previous dates.
9. Unknown salary stays `NULL`, never zero.
10. Currency, salary period, and tax basis must remain separate.
11. Duplicate clusters do not automatically reduce source-posting counts.
12. Existing Migration 001–004 tests remain green.

---

## 3. Migration identity and schema

Suggested revision:

```text
20260727_0005
```

Required:

```text
down_revision = "20260727_0004"
```

Create:

```sql
CREATE SCHEMA IF NOT EXISTS analytics;
REVOKE ALL ON SCHEMA analytics FROM PUBLIC;
```

---

## 4. Exact inventory — 18 tables

### Control and dimensions

```text
analytics.refresh_runs
analytics.dim_dates
analytics.dim_sources
analytics.dim_companies
analytics.dim_locations
analytics.dim_occupations
analytics.dim_skills
```

### Facts and bridges

```text
analytics.fact_job_observations
analytics.fact_salary_observations
analytics.bridge_job_observation_locations
analytics.bridge_job_observation_occupations
analytics.bridge_job_observation_skills
```

### Daily aggregates

```text
analytics.daily_market_metrics
analytics.daily_company_hiring
analytics.daily_location_demand
analytics.daily_occupation_demand
analytics.daily_skill_demand
analytics.daily_salary_metrics
```

---

# 5. Control and dimensions

## 5.1 `analytics.refresh_runs`

One analytics load/rebuild.

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `run_type` | `VARCHAR(30)` | No | — |
| `status` | `VARCHAR(30)` | No | `'pending'` |
| `calculation_version` | `VARCHAR(100)` | No | — |
| `window_start_date` | `DATE` | Yes | — |
| `window_end_date` | `DATE` | Yes | — |
| `watermark_observed_at` | `TIMESTAMPTZ` | Yes | — |
| `lookback_days` | `INTEGER` | No | `7` |
| `source_id` | `UUID` | Yes | — |
| `trigger_type` | `VARCHAR(30)` | No | `'manual'` |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `fact_rows_inserted` | `BIGINT` | No | `0` |
| `dimension_rows_inserted` | `BIGINT` | No | `0` |
| `dimension_rows_updated` | `BIGINT` | No | `0` |
| `aggregate_rows_upserted` | `BIGINT` | No | `0` |
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
trigger_type: manual, scheduler, github_actions, api, system, test
```

FK:

```text
source_id → ingestion.sources(id) ON DELETE SET NULL
```

Checks:

- calculation version is not blank;
- lookback and counters are nonnegative;
- end date requires start date and is not earlier;
- JSONB values are objects;
- terminal status requires start and finish timestamps;
- `running` status requires `started_at`;
- finish is not earlier than start.
- pending runs require both lifecycle timestamps NULL; running requires only `started_at`; terminal
  statuses require both timestamps non-NULL.

Indexes:

```text
(status, created_at DESC)
(calculation_version, created_at DESC)
(source_id, created_at DESC) WHERE source_id IS NOT NULL
(window_start_date, window_end_date)
```

---

## 5.2 `analytics.dim_dates`

One row per UTC calendar date.

| Column | Type | Null |
|---|---|---:|
| `date_key` | `INTEGER` | No |
| `calendar_date` | `DATE` | No |
| `year` | `SMALLINT` | No |
| `quarter` | `SMALLINT` | No |
| `month` | `SMALLINT` | No |
| `month_name` | `VARCHAR(20)` | No |
| `week_of_year` | `SMALLINT` | No |
| `day_of_month` | `SMALLINT` | No |
| `day_of_week` | `SMALLINT` | No |
| `day_name` | `VARCHAR(20)` | No |
| `is_weekend` | `BOOLEAN` | No |
| `month_start_date` | `DATE` | No |
| `month_end_date` | `DATE` | No |
| `quarter_start_date` | `DATE` | No |
| `quarter_end_date` | `DATE` | No |
| `created_at` | `TIMESTAMPTZ` | No, default `now()` |

Constraints:

```text
PRIMARY KEY (date_key)
UNIQUE (calendar_date)
date_key = YYYYMMDD
quarter 1..4
month 1..12
week 1..53
day_of_week 1..7
```

Every derived field must match `calendar_date`: year, quarter, month, localized month/day names,
ISO week/day values, weekend flag, and month/quarter boundaries. Seeded date rows reject UPDATE
and DELETE with SQLSTATE `23514`.

Seed with PostgreSQL `generate_series`:

```text
2020-01-01 through 2035-12-31
```

---

## 5.3 Conformed dimensions

All dimensions use a warehouse surrogate key while retaining the operational ID.

### `analytics.dim_sources`

```text
source_key BIGINT IDENTITY PK
source_id UUID NOT NULL UNIQUE FK ingestion.sources RESTRICT
slug VARCHAR(100) NOT NULL UNIQUE
display_name VARCHAR(255) NOT NULL
source_type VARCHAR(50) NOT NULL
country_code CHAR(2) NULL
status VARCHAR(30) NOT NULL
is_enabled BOOLEAN NOT NULL
source_updated_at TIMESTAMPTZ NOT NULL
warehouse_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Indexes: `(source_type)`, `(status, is_enabled)`.

### `analytics.dim_companies`

```text
company_key BIGINT IDENTITY PK
company_id UUID NOT NULL UNIQUE FK core.companies RESTRICT
canonical_name VARCHAR(500) NOT NULL
normalized_name VARCHAR(500) NOT NULL
company_type VARCHAR(30) NOT NULL
headquarters_location_id UUID NULL FK core.locations SET NULL
resolution_status VARCHAR(30) NOT NULL
company_updated_at TIMESTAMPTZ NOT NULL
warehouse_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Do not make `normalized_name` unique.

### `analytics.dim_locations`

```text
location_key BIGINT GENERATED BY DEFAULT AS IDENTITY PK
location_id UUID NULL UNIQUE
resolution_key VARCHAR(750) NOT NULL UNIQUE
location_type VARCHAR(30) NOT NULL
country_code CHAR(2) NULL
admin_level_1 VARCHAR(255) NULL
admin_level_2 VARCHAR(255) NULL
locality VARCHAR(255) NULL
canonical_label VARCHAR(750) NOT NULL
normalized_label VARCHAR(750) NOT NULL
latitude NUMERIC(9,6) NULL
longitude NUMERIC(9,6) NULL
location_updated_at TIMESTAMPTZ NULL
warehouse_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Rules:

- normal rows require `location_id` and FK to `core.locations(id)` with `RESTRICT`;
- only `location_key = -1` may have null `location_id`;
- seed `location_key = -1`, label `Unknown location`.

### `analytics.dim_occupations`

```text
occupation_key BIGINT GENERATED BY DEFAULT AS IDENTITY PK
occupation_id UUID NULL UNIQUE
taxonomy_version_id UUID NULL
taxonomy_version VARCHAR(100) NOT NULL
canonical_code VARCHAR(100) NOT NULL
canonical_name VARCHAR(255) NOT NULL
normalized_name VARCHAR(255) NOT NULL
parent_occupation_id UUID NULL
is_active BOOLEAN NOT NULL
occupation_updated_at TIMESTAMPTZ NULL
warehouse_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Rules:

- normal rows require operational occupation and taxonomy version FKs with `RESTRICT`;
- only `occupation_key = -1` may have null operational IDs;
- seed `occupation_key = -1`, code/name `unknown`.

### `analytics.dim_skills`

```text
skill_key BIGINT IDENTITY PK
skill_id UUID NOT NULL UNIQUE FK taxonomy.skills RESTRICT
taxonomy_version_id UUID NOT NULL FK taxonomy.taxonomy_versions RESTRICT
taxonomy_version VARCHAR(100) NOT NULL
canonical_code VARCHAR(100) NOT NULL
canonical_name VARCHAR(255) NOT NULL
normalized_name VARCHAR(255) NOT NULL
skill_type VARCHAR(30) NOT NULL
parent_skill_id UUID NULL
is_active BOOLEAN NOT NULL
skill_updated_at TIMESTAMPTZ NOT NULL
warehouse_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Dimensions use Type 1 behavior: update descriptive attributes while preserving the surrogate key.
PostgreSQL validation triggers require every normal occupation/skill dimension row to match its
operational entity's taxonomy-version ID, version string, and parent. The unknown occupation `-1`
row remains exempt because it deliberately has no operational identity.

Once assigned, each dimension surrogate and operational identity is immutable. Source, company,
location, occupation, and skill identity triggers reject reassignment with SQLSTATE `23514`; only
descriptive Type 1 attributes may change. Unknown location and occupation `-1` members can never be
converted into operational entities.

---

# 6. Observation facts

## 6.1 `analytics.fact_job_observations`

Grain: one `history.job_observations` row.

```text
job_observation_fact_id BIGINT IDENTITY PK
observation_id BIGINT NOT NULL UNIQUE FK history.job_observations RESTRICT
job_posting_id UUID NOT NULL FK core.job_postings RESTRICT
source_key BIGINT NOT NULL FK dim_sources RESTRICT
company_key BIGINT NULL FK dim_companies RESTRICT
observed_date_key INTEGER NOT NULL FK dim_dates RESTRICT
posted_date_key INTEGER NULL FK dim_dates RESTRICT
expires_date_key INTEGER NULL FK dim_dates RESTRICT
previous_observation_id BIGINT NULL
observation_reason VARCHAR(30) NOT NULL
status VARCHAR(20) NOT NULL
employment_type_code VARCHAR(30) NULL
seniority_level_code VARCHAR(30) NULL
work_mode VARCHAR(30) NULL
experience_min_years NUMERIC(6,2) NULL
experience_max_years NUMERIC(6,2) NULL
salary_disclosed BOOLEAN NOT NULL DEFAULT false
skill_count INTEGER NOT NULL DEFAULT 0
occupation_count INTEGER NOT NULL DEFAULT 0
location_count INTEGER NOT NULL DEFAULT 0
is_first_observation BOOLEAN NOT NULL DEFAULT false
is_status_change BOOLEAN NOT NULL DEFAULT false
is_content_change BOOLEAN NOT NULL DEFAULT false
canonical_hash CHAR(64) NOT NULL
normalization_version VARCHAR(100) NOT NULL
refresh_run_id UUID NOT NULL FK refresh_runs RESTRICT
loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Checks:

- counts are nonnegative;
- canonical hash is lowercase SHA-256;
- normalization version is nonblank;
- `is_first_observation = (previous_observation_id IS NULL)`.

Important indexes:

```text
(observed_date_key, source_key)
(job_posting_id, observed_date_key)
(company_key, observed_date_key) WHERE company_key IS NOT NULL
(status, observed_date_key)
(work_mode, observed_date_key)
(refresh_run_id)
```

Fact rows are append-only from the application perspective.

PostgreSQL validates every copied job-fact field against `history.job_observations`, including
NULL-safe company identity and UTC-derived date keys. The source key must resolve to the historical
source. Derived metrics are exact: salary disclosure means at least one disclosed historical
salary; skill, occupation, and location counts count their corresponding historical child rows;
first observations have both change flags false, while later flags compare status and canonical
hash with the previous observation. UPDATE and DELETE are rejected with SQLSTATE `23514`.

When a refresh run is source-scoped, its source must match the fact's source. Global runs with
NULL source may process multiple sources.

---

## 6.2 `analytics.fact_salary_observations`

Grain: one `history.observation_salaries` row.

```text
salary_fact_id BIGINT IDENTITY PK
observation_salary_id BIGINT NOT NULL UNIQUE FK history.observation_salaries RESTRICT
observation_id BIGINT NOT NULL FK history.job_observations RESTRICT
job_observation_fact_id BIGINT NOT NULL FK fact_job_observations RESTRICT
observed_date_key INTEGER NOT NULL FK dim_dates RESTRICT
source_key BIGINT NOT NULL FK dim_sources RESTRICT
company_key BIGINT NULL FK dim_companies RESTRICT
amount_min NUMERIC(20,2) NULL
amount_max NUMERIC(20,2) NULL
amount_exact NUMERIC(20,2) NULL
currency CHAR(3) NULL
period VARCHAR(20) NULL
compensation_type VARCHAR(30) NOT NULL
tax_basis VARCHAR(20) NOT NULL
is_disclosed BOOLEAN NOT NULL
is_negotiable BOOLEAN NOT NULL
is_estimated BOOLEAN NOT NULL
normalized_monthly_min NUMERIC(20,2) NULL
normalized_monthly_max NUMERIC(20,2) NULL
normalized_annual_min NUMERIC(20,2) NULL
normalized_annual_max NUMERIC(20,2) NULL
fx_rate NUMERIC(20,8) NULL
fx_rate_date DATE NULL
confidence NUMERIC(5,4) NULL
refresh_run_id UUID NOT NULL FK refresh_runs RESTRICT
loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Apply salary checks compatible with `history.observation_salaries`.

Unknown/undisclosed values remain null.

PostgreSQL validates that the salary belongs to the stated observation and job fact, that source,
company, and observed date match the job fact, and that every copied salary value matches the
historical salary. A source-scoped refresh must match the fact source. UPDATE and DELETE are
rejected with SQLSTATE `23514`.

---

# 7. Bridge tables

## `analytics.bridge_job_observation_locations`

Grain: one historical observation-location row.

```text
job_observation_fact_id BIGINT NOT NULL
observation_location_id BIGINT NOT NULL UNIQUE
location_key BIGINT NOT NULL
relationship_type VARCHAR(30) NOT NULL
is_primary BOOLEAN NOT NULL
is_remote BOOLEAN NOT NULL
remote_scope VARCHAR(30) NULL
confidence NUMERIC(5,4) NULL
refresh_run_id UUID NOT NULL
loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
PRIMARY KEY (job_observation_fact_id, observation_location_id)
```

Use FKs to fact, history location, dimension, and refresh run. Enforce remote consistency.
PostgreSQL also proves that the historical child belongs to the fact's observation, the dimension
resolves to the same operational location, and every copied relationship field matches history.
Bridge refresh runs are either global or source-matched to the job fact.

## `analytics.bridge_job_observation_occupations`

```text
job_observation_fact_id BIGINT NOT NULL
observation_occupation_id BIGINT NOT NULL UNIQUE
occupation_key BIGINT NOT NULL
is_primary BOOLEAN NOT NULL
classification_method VARCHAR(100) NULL
classifier_version VARCHAR(100) NULL
confidence NUMERIC(5,4) NULL
refresh_run_id UUID NOT NULL
loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
PRIMARY KEY (job_observation_fact_id, observation_occupation_id)
```

Partial unique index: one primary occupation per job fact.
PostgreSQL validates observation ownership, operational dimension identity, and copied
classification fields. Bridge refresh runs are either global or source-matched to the job fact.

## `analytics.bridge_job_observation_skills`

```text
job_observation_fact_id BIGINT NOT NULL
observation_skill_id BIGINT NOT NULL UNIQUE
skill_key BIGINT NOT NULL
requirement_type VARCHAR(20) NOT NULL
confidence NUMERIC(5,4) NULL
refresh_run_id UUID NOT NULL
loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
PRIMARY KEY (job_observation_fact_id, observation_skill_id)
```

Requirement type:

```text
required, preferred, mentioned, unknown
```

PostgreSQL validates observation ownership, operational skill identity, and copied requirement
and confidence fields. All three bridges reject UPDATE and DELETE with SQLSTATE `23514` through
the same reusable append-only trigger used by both fact tables. Dimensions, refresh runs, and daily
aggregates do not use that trigger.

---

# 8. Daily aggregates

Every daily table includes:

```text
refresh_run_id UUID NOT NULL FK analytics.refresh_runs RESTRICT
calculation_version VARCHAR(100) NOT NULL
calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Every daily row's source dimension must match a source-scoped refresh (global refreshes are valid),
and `calculation_version` must equal the referenced refresh run's calculation version.

Rows are rebuildable and may be updated.

## 8.1 `analytics.daily_market_metrics`

Grain:

```text
metric_date × source × employment type × seniority × work mode
```

Metrics:

```text
active_posting_count
new_posting_count
closed_posting_count
expired_posting_count
removed_posting_count
reactivated_posting_count
content_changed_count
salary_disclosed_count
remote_posting_count
```

Primary key is the full grain. Counts are nonnegative.

## 8.2 `analytics.daily_company_hiring`

Grain:

```text
metric_date × company × source
```

Metrics:

```text
active_posting_count
new_posting_count
closed_posting_count
unique_occupation_count
unique_skill_count
salary_disclosed_count
remote_posting_count
```

## 8.3 `analytics.daily_location_demand`

Grain:

```text
metric_date × location × source × work mode
```

Metrics:

```text
active_posting_count
new_posting_count
closed_posting_count
salary_disclosed_count
```

## 8.4 `analytics.daily_occupation_demand`

Grain:

```text
metric_date × occupation × source
```

Metrics:

```text
active_posting_count
new_posting_count
closed_posting_count
salary_disclosed_count
remote_posting_count
```

## 8.5 `analytics.daily_skill_demand`

Grain:

```text
metric_date × skill × source × requirement type
```

Metrics:

```text
active_posting_count
new_posting_count
closed_posting_count
company_count
occupation_count
```

## 8.6 `analytics.daily_salary_metrics`

Grain:

```text
metric_date × source × occupation × location × currency × period × tax basis
```

Use the seeded `-1` unknown occupation/location keys where classification is unavailable.

Metrics:

```text
disclosed_salary_count
estimated_salary_count
negotiable_salary_count
amount_min_average
amount_max_average
amount_exact_average
normalized_monthly_min_average
normalized_monthly_max_average
normalized_annual_min_average
normalized_annual_max_average
normalized_monthly_min_median
normalized_monthly_max_median
normalized_annual_min_median
normalized_annual_max_median
```

Rules:

- currencies are uppercase three-letter codes;
- periods and tax bases are valid;
- counts and numeric metrics are nonnegative;
- average and median minimum values cannot exceed their corresponding maximum values;
- do not combine different currencies, periods, or tax bases;
- aggregate rows require at least one disclosed salary.

All daily tables require date and dimension FKs and indexes supporting date-descending trend queries.

---

# 9. Refresh semantics

Migration 005 defines storage contracts. The production refresh worker is a later task.

Required future behavior:

1. Upsert dimensions by operational ID while preserving warehouse keys.
2. Load facts using a watermark plus configurable lookback window.
3. Use unique history IDs so repeated loads are idempotent.
4. Collect every affected date, including old dates from late data.
5. Rebuild affected daily grains inside a transaction.
6. Store `refresh_run_id` and `calculation_version`.
7. Never partially update a date window after a failed refresh.
8. Daily active count means the latest observation at or before the end of the UTC date.
9. Event counts use events occurring on that UTC date.

---

# 10. SQLAlchemy

Add:

```text
src/it_labor_market_intelligence/database/v1_models/analytics.py
```

Update package exports.

Requirements:

- use `V1Base`;
- explicit `analytics` schema;
- schema-qualified FKs;
- migration/model parity;
- PostgreSQL UUID and JSONB;
- facts documented as append-only;
- aggregates remain mutable/rebuildable.

Alembic remains authoritative for date seeding, sentinel rows, checks, and partial indexes.

---

# 11. Upgrade and downgrade

Upgrade order:

1. schema and access revoke;
2. refresh runs;
3. date dimension and seed;
4. source/company/location/occupation/skill dimensions;
5. `-1` unknown location and occupation rows;
6. job fact;
7. salary fact;
8. bridge tables;
9. daily aggregate tables;
10. indexes.

Downgrade reverses that order and drops only `analytics`.

Migration 001–004 schemas and data must remain untouched.

---

# 12. PostgreSQL integration tests

Create:

```text
tests/integration/database/test_database_v1_analytics.py
```

Required coverage:

- exactly 18 analytics tables;
- date seed boundaries and leap day;
- dimension uniqueness and Type 1 updates;
- `-1` unknown location/occupation rows;
- one observation fact per history observation;
- one salary fact per historical salary row;
- null salary remains null;
- copied fact and bridge lineage rejects every cross-wired field;
- fact/bridge append-only trigger inventory and mutation rejection;
- taxonomy dimension identity, deterministic immutable dates, and running lifecycle checks;
- all five daily salary minimum/maximum directions reject inverted ranges;
- bridge uniqueness and one primary occupation;
- refresh-run lifecycle and date-window checks;
- every aggregate grain rejects duplicates;
- aggregate rows allow controlled update/upsert;
- skill requirement types remain separate;
- work modes remain separate;
- USD/VND, month/year, gross/net remain separate;
- late old-dated data can replace the affected old aggregate grain;
- downgrade to Migration 004 removes only analytics;
- re-upgrade succeeds.

CI must pass:

```text
alembic upgrade head
alembic current
full pytest
Ruff
Black
MyPy
```

---

# 13. Documentation

Create:

```text
docs/DATABASE_V1_ANALYTICS.md
```

Update:

```text
README.md
docs/DATABASE_DESIGN.md
docs/DATABASE_V1_HISTORY_QUALITY.md
docs/DATA_SCHEMA.md
docs/DATA_IMPORT_RUNBOOK.md
```

Document table grain, UTC dates, source-posting count rules, late data, salary separation, calculation versions, sentinel dimensions, private access, and Migration 006 scope.

---

# 14. Out of scope

Do not implement:

```text
production analytics scheduler
full ETL loader
automatic aggregate jobs
materialized/serving views
Supabase RPC or RLS
dashboard API/UI
search engine
forecasting or ML
recommendations
users/resumes/applications
embeddings or LLM enrichment
crawler/canonical importer changes
automatic duplicate-count reduction
```

---

# 15. Acceptance checklist

- [ ] Direct child of Migration 004.
- [ ] Exactly 18 analytics tables.
- [ ] Explicit DDL and safe downgrade.
- [ ] Deterministic date dimension.
- [ ] Stable dimension surrogate keys.
- [ ] Unique history-to-fact mappings.
- [ ] Null salary preserved.
- [ ] Daily grain uniqueness enforced.
- [ ] Late dates can be recalculated.
- [ ] Calculation version and refresh lineage recorded.
- [ ] Currency/period/tax basis never mixed.
- [ ] Migration 001–004 remain intact.
- [ ] PostgreSQL tests, pytest, Ruff, Black, and MyPy pass.
- [ ] No serving/dashboard/scheduler work added.

---

# 16. Codex prompt

```text
Read AGENT_RULES.md and DATABASE_V1_MIGRATION_005_SPEC.md.

Confirm the current branch is main and pull the latest origin/main.

Create:
feat/database-v1-migration-005-analytics

Implement Database V1 Migration 005 exactly as specified.

Use explicit Alembic DDL. Add the private analytics schema, refresh-run
tracking, date and conformed dimensions, observation-level facts, bridge
tables, and rebuildable daily aggregates. Add schema-qualified SQLAlchemy
models, PostgreSQL integration tests, and documentation.

Use deterministic analytics-only unknown dimension rows with surrogate key -1
for unknown location and occupation. Do not invent operational UUIDs.

Do not implement serving views, RPC, RLS, dashboards, a production ETL
scheduler, crawler changes, recommendations, users, resumes, embeddings,
LLM enrichment, forecasting, or automatic duplicate-count reduction.

Run PostgreSQL migration and downgrade/re-upgrade tests, full pytest, Ruff,
Black, and MyPy.

Push the branch and create a draft pull request into main. Do not merge.
Return the PR link, final commit, table count, and final CI status.
```
