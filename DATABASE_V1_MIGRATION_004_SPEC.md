# Database V1 — Migration 004 History & Data Quality

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`  
**Database:** PostgreSQL 16 / Supabase-compatible PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration:** Alembic  
**Scope:** immutable job history, lifecycle/change events, field evidence, validation issues, and advisory duplicate groups.

---

## 1. Goal

Migration 004 adds:

```text
history
quality
```

It must support:

- immutable versions of each source posting;
- changes in title, company, salary, skills, location, occupation, and status;
- first-seen, closed, expired, removed, reactivated, and repost events;
- field-level evidence and confidence;
- validation issues with review/resolution state;
- advisory duplicate candidates and clusters without deleting source postings.

It does **not** implement analytics, serving views, the full observation writer, automatic diffing, lifecycle scheduling, dedup algorithms, API migration, dashboard changes, users, resumes, recommendations, embeddings, or LLM features.

---

## 2. Non-negotiable rules

1. Explicit Alembic DDL only.
2. No `Base.metadata.create_all()` or `drop_all()`.
3. No `DROP ... CASCADE`.
4. Schema-qualified PostgreSQL names.
5. `TIMESTAMPTZ` for timestamps.
6. `JSONB`, not generic JSON.
7. No PostgreSQL native enums.
8. Historical rows and events are append-only.
9. Field evidence and duplicate candidates are append-only.
10. A history row must match both the job’s source identity and the extracted record’s source identity.
11. A current/previous observation pointer may only reference the same job.
12. A → B → A canonical hashes must be allowed.
13. Unchanged recrawls should update `last_seen_at` without requiring a new observation.
14. Duplicate groups are advisory; no source posting is deleted or destructively merged.
15. Existing Migration 001–003 tests must remain green.

---

## 3. Migration identity

Suggested revision:

```text
20260727_0004
```

Required:

```text
down_revision = "20260726_0003"
```

Create:

```sql
CREATE SCHEMA IF NOT EXISTS history;
CREATE SCHEMA IF NOT EXISTS quality;
REVOKE ALL ON SCHEMA history FROM PUBLIC;
REVOKE ALL ON SCHEMA quality FROM PUBLIC;
```

---

## 4. Exact table inventory

### `history` — 9 tables

```text
history.job_observations
history.observation_descriptions
history.observation_locations
history.observation_salaries
history.observation_skills
history.observation_occupations
history.job_status_events
history.job_change_events
history.job_repost_events
```

### `quality` — 6 tables

```text
quality.validation_runs
quality.data_quality_issues
quality.field_evidence
quality.duplicate_candidates
quality.duplicate_clusters
quality.duplicate_cluster_members
```

Exactly 15 new tables.

---

## 5. Existing-table changes

### `core.job_postings`

Add:

```text
current_observation_id BIGINT NULL
```

Add:

```text
UNIQUE (id, source_id, source_job_id)
UNIQUE (id, source_id)
```

Name:

```text
uq_job_postings__id_source_identity
```

After `history.job_observations` exists, add:

```text
(current_observation_id, id)
→ history.job_observations(id, job_posting_id)
ON DELETE SET NULL (current_observation_id)
```

Name:

```text
fk_job_postings__current_observation__job_observations
```

Index:

```text
ix_job_postings__current_observation_id
(current_observation_id)
WHERE current_observation_id IS NOT NULL
```

Migration 003’s constraint on:

```text
ingestion.extracted_records (id, source_id, source_job_id)
```

must remain unchanged.

Add supporting uniqueness for composite lineage foreign keys:

```text
ingestion.crawl_runs (id, source_id)
ingestion.extracted_records (id, source_id)
```

---

## 6. Append-only enforcement

Create:

```text
history.prevent_append_only_mutation()
```

A `BEFORE UPDATE OR DELETE` trigger must raise SQLSTATE `23514`.

Attach to:

```text
history.job_observations
history.observation_locations
history.observation_salaries
history.observation_skills
history.observation_occupations
history.job_status_events
history.job_change_events
history.job_repost_events
quality.duplicate_candidates
```

Use specialized retention/review triggers for `history.observation_descriptions` and
`quality.field_evidence`. Do not attach the generic trigger to validation runs, quality issues,
clusters, or cluster members.

---

# 7. History tables

## 7.1 `history.job_observations`

One immutable canonical state of one source posting.

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `source_id` | `UUID` | No | — |
| `source_job_id` | `VARCHAR(255)` | No | — |
| `extracted_record_id` | `BIGINT` | No | — |
| `crawl_run_id` | `UUID` | Yes | — |
| `previous_observation_id` | `BIGINT` | Yes | — |
| `observation_reason` | `VARCHAR(30)` | No | — |
| `observed_at` | `TIMESTAMPTZ` | No | — |
| `canonical_hash` | `CHAR(64)` | No | — |
| `source_content_hash` | `CHAR(64)` | Yes | — |
| `status` | `VARCHAR(20)` | No | — |
| `source_url` | `TEXT` | No | — |
| `canonical_url` | `TEXT` | Yes | — |
| `title_raw` | `TEXT` | No | — |
| `title_normalized` | `TEXT` | Yes | — |
| `company_id` | `UUID` | Yes | — |
| `company_name_raw` | `TEXT` | Yes | — |
| `location_raw` | `TEXT` | Yes | — |
| `employment_type_code` | `VARCHAR(30)` | Yes | — |
| `seniority_level_code` | `VARCHAR(30)` | Yes | — |
| `work_mode` | `VARCHAR(30)` | Yes | — |
| `experience_min_years` | `NUMERIC(6,2)` | Yes | — |
| `experience_max_years` | `NUMERIC(6,2)` | Yes | — |
| `posted_at` | `TIMESTAMPTZ` | Yes | — |
| `expires_at` | `TIMESTAMPTZ` | Yes | — |
| `canonical_payload_json` | `JSONB` | No | `'{}'::jsonb` |
| `extractor_version` | `VARCHAR(100)` | Yes | — |
| `normalization_version` | `VARCHAR(100)` | No | — |
| `confidence_score` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed `observation_reason`:

```text
first_seen
content_changed
status_changed
reprocessed
manual_correction
backfill
other
```

Allowed status:

```text
active
expired
closed
removed
unknown
```

Allowed work mode:

```text
onsite
hybrid
remote
flexible
unknown
```

Foreign keys:

```text
(job_posting_id, source_id, source_job_id)
→ core.job_postings(id, source_id, source_job_id)
ON DELETE RESTRICT

(extracted_record_id, source_id, source_job_id)
→ ingestion.extracted_records(id, source_id, source_job_id)
ON DELETE RESTRICT

crawl_run_id → ingestion.crawl_runs(id) ON DELETE RESTRICT
(previous_observation_id, job_posting_id)
→ history.job_observations(id, job_posting_id) ON DELETE RESTRICT
company_id → core.companies(id) ON DELETE RESTRICT
employment_type_code → taxonomy.employment_types(code) ON DELETE RESTRICT
seniority_level_code → taxonomy.seniority_levels(code) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (id, job_posting_id)
UNIQUE (id, job_posting_id, source_id)
UNIQUE (id, extracted_record_id)
UNIQUE (job_posting_id, extracted_record_id, normalization_version)

source_job_id/title_raw/normalization_version not blank
source_url begins http:// or https://
canonical_url is null or begins http:// or https://
canonical_hash is lowercase SHA-256
source_content_hash is null or lowercase SHA-256
canonical_payload_json is an object
confidence_score is null or between 0 and 1
experience values are nonnegative and min <= max
expires_at is null, or posted_at is null, or expires_at >= posted_at
previous_observation_id is null or differs from id
```

Do **not** make canonical hash unique. This must allow A → B → A.

Indexes:

```text
(job_posting_id, observed_at DESC, id DESC)
(source_id, observed_at DESC)
(canonical_hash)
(extracted_record_id)
(crawl_run_id) WHERE crawl_run_id IS NOT NULL
(status, observed_at DESC)
(company_id, observed_at DESC) WHERE company_id IS NOT NULL
```

Attach append-only trigger.

---

## 7.2 `history.observation_descriptions`

| Column | Type | Null | Default |
|---|---|---:|---|
| `observation_id` | `BIGINT` | No | — |
| `description_text` | `TEXT` | Yes | — |
| `description_format` | `VARCHAR(20)` | No | `'plain'` |
| `language_code` | `VARCHAR(10)` | Yes | — |
| `content_hash` | `CHAR(64)` | No | — |
| `redaction_status` | `VARCHAR(30)` | No | `'not_required'` |
| `retained_until` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed format:

```text
plain
html
markdown
```

Allowed redaction state:

```text
not_required
pending
redacted
expired
failed
```

Rules:

```text
PRIMARY KEY (observation_id)
observation_id → history.job_observations(id) ON DELETE RESTRICT
content_hash is lowercase SHA-256
description text is nonblank when present
description_text may be null only for redacted/expired rows
```

Indexes:

```text
(content_hash)
(retained_until) WHERE retained_until IS NOT NULL
```

Attach a specialized trigger. It always rejects deletion and changes to identity, format,
language, content hash, retention date, or creation time. The only permitted update changes
`description_text` from non-null to null while changing `redaction_status` to `redacted` or
`expired`. Text cannot be restored, and a redacted/expired row cannot return to another state.

---

## 7.3 `history.observation_locations`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `observation_id` | `BIGINT` | No | — |
| `location_id` | `UUID` | No | — |
| `relationship_type` | `VARCHAR(30)` | No | `'workplace'` |
| `is_primary` | `BOOLEAN` | No | `false` |
| `is_remote` | `BOOLEAN` | No | `false` |
| `remote_scope` | `VARCHAR(30)` | Yes | — |
| `source_text` | `TEXT` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Foreign keys:

```text
observation_id → history.job_observations(id) ON DELETE RESTRICT
location_id → core.locations(id) ON DELETE RESTRICT
```

Rules:

```text
UNIQUE (observation_id, location_id, relationship_type)
confidence is null or between 0 and 1
is_remote = (remote_scope IS NOT NULL)
```

One primary per relationship:

```sql
CREATE UNIQUE INDEX uq_observation_locations__one_primary
ON history.observation_locations (observation_id, relationship_type)
WHERE is_primary;
```

Attach append-only trigger.

---

## 7.4 `history.observation_salaries`

Use the same salary semantics as `core.salary_offers`.

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `observation_id` | `BIGINT` | No | — |
| `offer_index` | `SMALLINT` | No | `0` |
| `raw_text` | `TEXT` | Yes | — |
| `amount_min` | `NUMERIC(20,2)` | Yes | — |
| `amount_max` | `NUMERIC(20,2)` | Yes | — |
| `amount_exact` | `NUMERIC(20,2)` | Yes | — |
| `currency` | `CHAR(3)` | Yes | — |
| `period` | `VARCHAR(20)` | Yes | — |
| `compensation_type` | `VARCHAR(30)` | No | `'base_salary'` |
| `tax_basis` | `VARCHAR(20)` | No | `'unknown'` |
| `is_disclosed` | `BOOLEAN` | No | `false` |
| `is_negotiable` | `BOOLEAN` | No | `false` |
| `is_estimated` | `BOOLEAN` | No | `false` |
| `normalized_monthly_min` | `NUMERIC(20,2)` | Yes | — |
| `normalized_monthly_max` | `NUMERIC(20,2)` | Yes | — |
| `normalized_annual_min` | `NUMERIC(20,2)` | Yes | — |
| `normalized_annual_max` | `NUMERIC(20,2)` | Yes | — |
| `fx_rate` | `NUMERIC(20,8)` | Yes | — |
| `fx_rate_date` | `DATE` | Yes | — |
| `normalization_method` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Foreign keys:

```text
observation_id → history.job_observations(id) ON DELETE RESTRICT
```

The historical salary snapshot is self-contained. It has no foreign key to a mutable current
`core.salary_offers` row.

Rules:

```text
UNIQUE (observation_id, offer_index)
offer_index >= 0
valid period/compensation_type/tax_basis
all amounts nonnegative
min <= max
currency null or uppercase 3 letters
fx_rate and fx_rate_date both null or both non-null
fx_rate > 0
confidence null or between 0 and 1
disclosed salary has at least one source amount
nondisclosed and nonestimated salary has no source amount
nondisclosed negotiable salary has no source amount
```

Attach append-only trigger.

---

## 7.5 `history.observation_skills`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `observation_id` | `BIGINT` | No | — |
| `skill_id` | `UUID` | No | — |
| `requirement_type` | `VARCHAR(20)` | No | `'mentioned'` |
| `evidence_text` | `TEXT` | Yes | — |
| `evidence_section` | `VARCHAR(100)` | Yes | — |
| `extraction_method` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Rules:

```text
observation_id → history.job_observations(id) ON DELETE RESTRICT
skill_id → taxonomy.skills(id) ON DELETE RESTRICT
UNIQUE (observation_id, skill_id, requirement_type)
requirement_type in required/preferred/mentioned/unknown
confidence null or between 0 and 1
```

Attach append-only trigger.

---

## 7.6 `history.observation_occupations`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `observation_id` | `BIGINT` | No | — |
| `occupation_id` | `UUID` | No | — |
| `is_primary` | `BOOLEAN` | No | `false` |
| `classification_method` | `VARCHAR(100)` | Yes | — |
| `classifier_version` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Rules:

```text
observation_id → history.job_observations(id) ON DELETE RESTRICT
occupation_id → taxonomy.occupations(id) ON DELETE RESTRICT
UNIQUE (observation_id, occupation_id)
confidence null or between 0 and 1
```

One primary:

```sql
CREATE UNIQUE INDEX uq_observation_occupations__one_primary
ON history.observation_occupations (observation_id)
WHERE is_primary;
```

Attach append-only trigger.

---

## 7.7 `history.job_status_events`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `observation_id` | `BIGINT` | Yes | — |
| `from_status` | `VARCHAR(20)` | Yes | — |
| `to_status` | `VARCHAR(20)` | No | — |
| `event_type` | `VARCHAR(40)` | No | — |
| `event_at` | `TIMESTAMPTZ` | No | — |
| `rule_version` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `evidence_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Event types:

```text
first_seen
source_marked_active
source_marked_closed
expiry_elapsed
repeated_not_found
reactivated
manual_correction
backfill
other
```

Foreign keys:

```text
job_posting_id → core.job_postings(id) ON DELETE RESTRICT
(observation_id, job_posting_id)
→ history.job_observations(id, job_posting_id) ON DELETE RESTRICT
```

Rules:

```text
from_status is null or differs from to_status
valid statuses
evidence_json is an object
confidence null or between 0 and 1
```

Critical index:

```text
(observation_id) WHERE observation_id IS NOT NULL
```

Attach append-only trigger.

---

## 7.8 `history.job_change_events`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `from_observation_id` | `BIGINT` | No | — |
| `to_observation_id` | `BIGINT` | No | — |
| `field_path` | `VARCHAR(500)` | No | — |
| `change_type` | `VARCHAR(30)` | No | — |
| `old_value_json` | `JSONB` | Yes | — |
| `new_value_json` | `JSONB` | Yes | — |
| `detected_at` | `TIMESTAMPTZ` | No | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Change types:

```text
field_added
field_removed
field_changed
status_changed
reclassified
corrected
other
```

Composite foreign keys must prove both observations belong to the same job.

Rules:

```text
UNIQUE (from_observation_id, to_observation_id, field_path, change_type)
from_observation_id != to_observation_id
field_path not blank
old_value_json IS DISTINCT FROM new_value_json
```

Critical indexes:

```text
(to_observation_id)
(field_path)
```

Attach append-only trigger.

---

## 7.9 `history.job_repost_events`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `previous_observation_id` | `BIGINT` | No | — |
| `new_observation_id` | `BIGINT` | No | — |
| `repost_type` | `VARCHAR(30)` | No | — |
| `previous_posted_at` | `TIMESTAMPTZ` | Yes | — |
| `new_posted_at` | `TIMESTAMPTZ` | Yes | — |
| `detection_method` | `VARCHAR(100)` | No | — |
| `method_version` | `VARCHAR(100)` | No | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `evidence_json` | `JSONB` | No | `'{}'::jsonb` |
| `detected_at` | `TIMESTAMPTZ` | No | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Repost types:

```text
source_repost
date_refresh
content_refresh
suspected_repost
other
```

Both observation FKs must prove the same job.

Rules:

```text
UNIQUE (previous_observation_id, new_observation_id, method_version)
previous_observation_id != new_observation_id
method names not blank
confidence null or between 0 and 1
evidence_json is an object
```

Critical index:

```text
(new_observation_id)
```

Attach append-only trigger.

---

# 8. Quality tables

## 8.1 `quality.validation_runs`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `source_id` | `UUID` | Yes | — |
| `crawl_run_id` | `UUID` | Yes | — |
| `pipeline_version_id` | `UUID` | Yes | — |
| `scope_type` | `VARCHAR(30)` | No | — |
| `ruleset_version` | `VARCHAR(100)` | No | — |
| `status` | `VARCHAR(30)` | No | `'pending'` |
| `scope_json` | `JSONB` | No | `'{}'::jsonb` |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `records_checked_count` | `INTEGER` | No | `0` |
| `issues_found_count` | `INTEGER` | No | `0` |
| `critical_issue_count` | `INTEGER` | No | `0` |
| `metrics_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Scope:

```text
extracted_record
observation
crawl_run
batch
full_scan
other
```

Status:

```text
pending
running
succeeded
partially_succeeded
failed
cancelled
```

Rules:

```text
foreign keys to source/crawl run/pipeline version use ON DELETE SET NULL
(crawl_run_id, source_id) must match ingestion.crawl_runs(id, source_id) when both are present
ruleset_version not blank
JSONB fields are objects
counters nonnegative
critical count <= issue count
finished_at requires started_at and is >= started_at
running requires started_at
terminal statuses require finished_at
```

---

## 8.2 `quality.data_quality_issues`

Mutable review entity. Status changes must be audited by the application/system audit mechanism.

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `validation_run_id` | `UUID` | No | — |
| `source_id` | `UUID` | Yes | — |
| `crawl_run_id` | `UUID` | Yes | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
| `job_posting_id` | `UUID` | Yes | — |
| `observation_id` | `BIGINT` | Yes | — |
| `issue_code` | `VARCHAR(150)` | No | — |
| `field_path` | `VARCHAR(500)` | Yes | — |
| `severity` | `VARCHAR(20)` | No | `'warning'` |
| `status` | `VARCHAR(30)` | No | `'open'` |
| `fingerprint` | `CHAR(64)` | No | — |
| `message` | `TEXT` | No | — |
| `rule_version` | `VARCHAR(100)` | No | — |
| `evidence_json` | `JSONB` | No | `'{}'::jsonb` |
| `detected_at` | `TIMESTAMPTZ` | No | `now()` |
| `reviewed_by` | `VARCHAR(255)` | Yes | — |
| `reviewed_at` | `TIMESTAMPTZ` | Yes | — |
| `resolved_at` | `TIMESTAMPTZ` | Yes | — |
| `resolution_notes` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Severity:

```text
info
warning
error
critical
```

Status:

```text
open
acknowledged
resolved
false_positive
suppressed
```

Foreign keys:

```text
validation_run_id → quality.validation_runs(id) ON DELETE RESTRICT
source/crawl/extracted record use ON DELETE RESTRICT
job_posting_id → core.job_postings(id) ON DELETE RESTRICT
(observation_id, job_posting_id)
→ history.job_observations(id, job_posting_id) ON DELETE RESTRICT
(crawl_run_id, source_id) → ingestion.crawl_runs(id, source_id)
(extracted_record_id, source_id) → ingestion.extracted_records(id, source_id)
(job_posting_id, source_id) → core.job_postings(id, source_id)
(observation_id, job_posting_id, source_id)
→ history.job_observations(id, job_posting_id, source_id) ON DELETE RESTRICT
```

Rules:

```text
UNIQUE (validation_run_id, fingerprint)
fingerprint is lowercase SHA-256
issue_code/message/rule_version not blank
evidence_json is an object
at least one context: source, crawl run, extracted record, job, or observation
observation requires job_posting_id
reviewed_at requires reviewed_by
resolved/false_positive/suppressed require resolved_at
open/acknowledged require resolved_at IS NULL
```

Critical indexes:

```text
(source_id, detected_at DESC)
(job_posting_id)
(observation_id)
(issue_code)
```

---

## 8.3 `quality.field_evidence`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `observation_id` | `BIGINT` | No | — |
| `field_path` | `VARCHAR(500)` | No | — |
| `evidence_index` | `SMALLINT` | No | `0` |
| `classification` | `VARCHAR(30)` | No | — |
| `raw_value_json` | `JSONB` | Yes | — |
| `normalized_value_json` | `JSONB` | Yes | — |
| `evidence_path` | `TEXT` | Yes | — |
| `evidence_section` | `VARCHAR(100)` | Yes | — |
| `extraction_method` | `VARCHAR(100)` | Yes | — |
| `extractor_version` | `VARCHAR(100)` | Yes | — |
| `normalization_rule` | `VARCHAR(150)` | Yes | — |
| `normalization_version` | `VARCHAR(100)` | Yes | — |
| `inference_method` | `VARCHAR(150)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `review_status` | `VARCHAR(30)` | No | `'unreviewed'` |
| `reviewed_by` | `VARCHAR(255)` | Yes | — |
| `reviewed_at` | `TIMESTAMPTZ` | Yes | — |
| `review_notes` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Classification:

```text
direct_structured
direct_html
description_derived
normalized
inferred
not_available
unverified
```

Review status:

```text
unreviewed
verified
rejected
needs_review
```

Rules:

```text
observation FK uses ON DELETE RESTRICT
UNIQUE (observation_id, field_path, evidence_index)
evidence_index >= 0
field_path not blank
confidence null or between 0 and 1
not_available requires raw and normalized values null
other classes require at least one evidence element
inferred requires inference_method
normalized requires normalization_rule and normalization_version
verified/rejected requires reviewed_by and reviewed_at
verified/rejected cannot return to unreviewed
```

Attach a specialized trigger that always rejects deletion, keeps all content and lineage columns
immutable, and permits updates only to `review_status`, `reviewed_by`, `reviewed_at`, and
`review_notes` under the review rules above.

---

## 8.4 `quality.duplicate_candidates`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `left_job_posting_id` | `UUID` | No | — |
| `right_job_posting_id` | `UUID` | No | — |
| `candidate_reason` | `VARCHAR(50)` | No | — |
| `method_version` | `VARCHAR(100)` | No | — |
| `score` | `NUMERIC(5,4)` | No | — |
| `feature_vector_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Reasons:

```text
same_source_url
same_company_title_location
similar_content
repost_pattern
manual
other
```

Rules:

```text
both jobs use ON DELETE RESTRICT
UNIQUE (left_job_posting_id, right_job_posting_id, method_version)
left_job_posting_id < right_job_posting_id
score between 0 and 1
method_version not blank
feature vector is an object
```

Attach append-only trigger.

---

## 8.5 `quality.duplicate_clusters`

| Column | Type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `cluster_type` | `VARCHAR(30)` | No | — |
| `method_version` | `VARCHAR(100)` | No | — |
| `score` | `NUMERIC(5,4)` | Yes | — |
| `review_status` | `VARCHAR(30)` | No | `'pending'` |
| `created_by` | `VARCHAR(20)` | No | `'automated'` |
| `notes` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Cluster type:

```text
exact_duplicate
near_duplicate
repost_series
possible_duplicate
other
```

Review state:

```text
pending
approved
rejected
needs_review
```

Created by:

```text
automated
manual
```

Rules:

```text
method_version not blank
score null or between 0 and 1
```

Critical index:

```text
(review_status, created_at DESC)
```

---

## 8.6 `quality.duplicate_cluster_members`

| Column | Type | Null | Default |
|---|---|---:|---|
| `cluster_id` | `UUID` | No | — |
| `job_posting_id` | `UUID` | No | — |
| `member_role` | `VARCHAR(20)` | No | `'member'` |
| `membership_score` | `NUMERIC(5,4)` | Yes | — |
| `added_by` | `VARCHAR(20)` | No | `'automated'` |
| `evidence_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Rules:

```text
PRIMARY KEY (cluster_id, job_posting_id)
cluster delete cascades only membership rows
job posting delete is restricted
member_role in representative/member
added_by in automated/manual
membership score null or between 0 and 1
evidence JSON is an object
```

One representative:

```sql
CREATE UNIQUE INDEX uq_duplicate_cluster_members__one_representative
ON quality.duplicate_cluster_members (cluster_id)
WHERE member_role = 'representative';
```

A pending cluster may temporarily have no representative.

---

# 9. Required behavior

## First observation

```text
insert/upsert current core state
insert observation and child snapshots
insert first status event
set current_observation_id
```

## Unchanged recrawl

```text
update last_seen_at only
no duplicate observation
no change events
```

## Changed state

```text
insert new observation
link previous_observation_id
insert complete child snapshots
insert per-field change events
insert status event only when status changes
update current core state and current_observation_id
```

## Reprocessing

Same extracted record may create another observation only when `normalization_version` differs.

## Lifecycle

One failed fetch must never directly imply closed/removed.

---

# 10. SQLAlchemy

Add:

```text
src/it_labor_market_intelligence/database/v1_models/history.py
src/it_labor_market_intelligence/database/v1_models/quality.py
```

Update:

```text
core.py
__init__.py
```

Use `V1Base`, explicit schemas, schema-qualified FKs, PostgreSQL `JSONB` and `UUID`, server defaults, and matching composite constraints.

Alembic remains authoritative for triggers and partial indexes.

Do not add generic update/delete repositories for append-only models.

---

# 11. Upgrade order

1. Create schemas and revoke public access.
2. Add supporting source-identity constraints.
3. Create generic append-only and specialized retention/review trigger functions.
4. Create `history.job_observations`.
5. Add `current_observation_id`, FK, and index.
6. Create history child tables.
7. Create history event tables.
8. Create quality tables.
9. Attach generic append-only and specialized retention/review triggers.
10. Create remaining indexes.

---

# 12. Downgrade order

1. Drop quality cluster members/clusters/candidates/evidence/issues/runs.
2. Drop history events.
3. Drop history child tables.
4. Drop current-observation FK/index/column.
5. Drop `history.job_observations`.
6. Drop generic and specialized trigger functions.
7. Drop Migration 004 supporting identity constraints.
8. Drop `quality` schema.
9. Drop `history` schema.

Do not remove Migration 003’s extracted-record identity constraint.  
Do not drop `system`, `ingestion`, `taxonomy`, or `core`.

---

# 13. PostgreSQL integration tests

Create:

```text
tests/integration/database/test_database_v1_history_quality.py
```

Required tests:

### Schema/migration

- exactly 9 history and 6 quality tables;
- Alembic head is Migration 004;
- downgrade to 003 removes only Migration 004;
- re-upgrade succeeds.

### Observations

- correct source identity accepted;
- wrong source or source job ID rejected;
- previous observation from another job rejected;
- current pointer to another job’s observation rejected;
- duplicate same job/extracted-record/version rejected;
- A → B → A hashes accepted with distinct lineage;
- invalid hashes/JSON/ranges rejected.

### Append-only

- update and delete observation rejected;
- update/delete immutable child snapshot rejected;
- update/delete event rejected;
- description deletion and non-retention updates rejected;
- field-evidence content update and deletion rejected;
- update/delete duplicate candidate rejected;
- verify every required generic and specialized table has its trigger;
- no `ON DELETE SET NULL` action targets an append-only history table.

### Historical children

- multiple locations;
- one primary location per relationship;
- remote consistency both ways;
- month/year salary remain separate;
- salary NULL/FX/disclosure rules;
- deleting a current salary does not change or block its self-contained historical snapshot;
- required/preferred same skill allowed;
- one primary occupation;
- description redaction/hash semantics and one-way text removal.

### Events

- valid first status event;
- same from/to status rejected;
- cross-job observation event rejected;
- identical old/new change rejected;
- repost observations must belong to same job.

### Quality

- validation lifecycle and counters;
- validation-run source/crawl identity consistency;
- valid source-only issue;
- mismatched source/crawl, source/extracted-record, source/job, or observation lineage rejected;
- deleting referenced issue context is rejected;
- issue requires context;
- issue fingerprint uniqueness per run;
- resolution/review state consistency;
- field-evidence class and review-workflow requirements;
- canonical duplicate pair ordering;
- one cluster representative;
- cluster deletion never deletes jobs.

CI must run PostgreSQL 16, full pytest, Ruff, Black, and MyPy.

---

# 14. Documentation

Create:

```text
docs/DATABASE_V1_HISTORY_QUALITY.md
```

Update:

```text
README.md
docs/DATABASE_DESIGN.md
docs/DATABASE_V1_CORE.md
docs/DATA_SCHEMA.md
docs/DATA_IMPORT_RUNBOOK.md
```

Document:

- current state versus history;
- unchanged recrawl behavior;
- A → B → A support;
- lifecycle status meanings;
- append-only rules;
- field evidence classifications;
- issue lifecycle;
- duplicate groups are advisory;
- downgrade behavior;
- next migration: analytics warehouse.

---

# 15. Acceptance checklist

- [ ] Direct child of Migration 003.
- [ ] Exactly 15 new tables.
- [ ] Explicit DDL, no metadata create/drop.
- [ ] No `DROP ... CASCADE`.
- [ ] Current and previous observations constrained to same job.
- [ ] Observation source/extracted-record identity enforced.
- [ ] A → B → A supported.
- [ ] Historical rows/events append-only.
- [ ] Field evidence and duplicate candidates append-only.
- [ ] Multi-location, salary, skill, occupation snapshots work.
- [ ] Quality issue lifecycle is valid.
- [ ] Duplicate grouping does not merge/delete postings.
- [ ] Downgrade leaves Migration 001–003 intact.
- [ ] PostgreSQL tests, full pytest, Ruff, Black, and MyPy pass.
- [ ] No out-of-scope feature added.

---

# 16. Codex prompt

```text
Read AGENT_RULES.md and DATABASE_V1_MIGRATION_004_SPEC.md.

Confirm the current branch is main and pull the latest origin/main.

Create:
feat/database-v1-migration-004-history-quality

Implement Database V1 Migration 004 exactly as specified.

Use explicit Alembic DDL. Add schema-qualified SQLAlchemy history and quality models, update CoreJobPosting with the current-observation pointer, add PostgreSQL integration tests, and update documentation.

Do not implement analytics, serving, dashboard, crawler changes, API migration, the full observation writer, automatic diffing, lifecycle scheduling, dedup algorithms, users, resumes, recommendations, embeddings, or LLM features.

Run PostgreSQL migration and downgrade/re-upgrade tests, full pytest, Ruff, Black, and MyPy.

Push the branch and create a draft pull request into main. Do not merge. Return the PR link and final CI status.
```
