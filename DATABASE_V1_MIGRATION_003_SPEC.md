# Database V1 — Migration 003 Core & Taxonomy Specification

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`  
**Target:** PostgreSQL 16 / Supabase PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration tool:** Alembic  
**Audience:** Codex  
**Status:** Implementation-ready  

## 1. Objective

Implement Database V1 Migration 003 after the already-merged Migration 001 and 002.

Migration 003 creates the canonical current-state layer for:

- companies;
- source job postings;
- repeatable locations;
- salary offers;
- versioned skills;
- versioned occupations;
- employment type and seniority reference data.

Data flow after this migration:

```text
ingestion.extracted_records
→ normalization/application service
→ core.job_postings
→ company/location/salary/skill/occupation relations
→ later history and analytics migrations
```

This migration does **not** implement observation history, change events, field-level evidence, analytics facts, serving views, user data, recommendations, or a full canonical importer.

## 2. Non-negotiable rules

1. Use explicit Alembic DDL only.
2. Do not call `Base.metadata.create_all()` or `Base.metadata.drop_all()`.
3. Do not use `DROP ... CASCADE`.
4. Use schema-qualified PostgreSQL names.
5. Use `TIMESTAMPTZ` for timestamps and `JSONB` for JSON.
6. Do not use PostgreSQL native enum types.
7. Preserve source posting identity with `UNIQUE (source_id, source_job_id)`.
8. Do not merge companies merely because normalized names match.
9. Do not collapse multiple locations into one scalar city.
10. Do not flatten all salary information onto `job_postings`.
11. Do not mix salary periods, currencies, or tax bases.
12. Undisclosed/negotiable salary must not become disclosed numeric salary.
13. Keep cross-source postings separate.
14. Retain lineage to `ingestion.extracted_records` where specified.
15. Keep Migration 001 and 002 behavior and tests intact.
16. Do not rewrite the current Phase 3 API in this task.
17. Do not expose `core` or `taxonomy` to Supabase `anon`.
18. Do not add history, analytics, serving, deduplication, resume, user, embedding, or LLM tables.

## 3. Migration identity

Suggested revision:

```text
20260726_0003_database_v1_core_taxonomy
```

Required parent:

```text
down_revision = "20260726_0002"
```

Alembic revision identifiers and extractor versions are separate version systems. Gold examples
must use a generic synthetic extractor version such as `0.0.0-example`, not an `m003` marker.

## 4. Schemas

Create:

```sql
CREATE SCHEMA IF NOT EXISTS taxonomy;
CREATE SCHEMA IF NOT EXISTS core;
REVOKE ALL ON SCHEMA taxonomy FROM PUBLIC;
REVOKE ALL ON SCHEMA core FROM PUBLIC;
```

Do not create Supabase-specific roles or RLS policies yet.

## 5. Table inventory

Migration 003 creates exactly 17 tables.

### Taxonomy

```text
taxonomy.taxonomy_versions
taxonomy.employment_types
taxonomy.seniority_levels
taxonomy.occupations
taxonomy.occupation_aliases
taxonomy.skills
taxonomy.skill_aliases
```

### Core

```text
core.locations
core.companies
core.company_aliases
core.company_domains
core.job_postings
core.job_posting_descriptions
core.job_posting_locations
core.salary_offers
core.job_posting_skills
core.job_posting_occupations
```

---

# 6. Taxonomy tables

## 6.1 `taxonomy.taxonomy_versions`

Registers immutable occupation and skill taxonomy releases.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `taxonomy_type` | `VARCHAR(30)` | No | — |
| `version` | `VARCHAR(100)` | No | — |
| `status` | `VARCHAR(20)` | No | `'draft'` |
| `name` | `VARCHAR(255)` | No | — |
| `description` | `TEXT` | Yes | — |
| `source_name` | `VARCHAR(255)` | Yes | — |
| `source_url` | `TEXT` | Yes | — |
| `license_name` | `VARCHAR(255)` | Yes | — |
| `metadata_json` | `JSONB` | No | `'{}'::jsonb` |
| `valid_from` | `TIMESTAMPTZ` | Yes | — |
| `valid_to` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed values:

```text
taxonomy_type: occupation | skill
status: draft | active | retired
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (taxonomy_type, version)
length(trim(version)) > 0
length(trim(name)) > 0
valid_to IS NULL OR valid_from IS NOT NULL
valid_to IS NULL OR valid_to > valid_from
status != 'active' OR valid_from IS NOT NULL
```

`taxonomy_type` is immutable after insertion. An explicit PostgreSQL
`BEFORE UPDATE OF taxonomy_type` trigger must allow an update only when the new type equals the
old type and otherwise raise a constraint-style error. Other fields remain updateable when their
ordinary constraints are satisfied.

Only one active version per type:

```sql
CREATE UNIQUE INDEX uq_taxonomy_versions__one_active_type
ON taxonomy.taxonomy_versions (taxonomy_type)
WHERE status = 'active';
```

Index:

```text
ix_taxonomy_versions__type_created_at (taxonomy_type, created_at DESC)
```

## 6.2 `taxonomy.employment_types`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `code` | `VARCHAR(30)` | No | — |
| `display_name` | `VARCHAR(100)` | No | — |
| `sort_order` | `SMALLINT` | No | `0` |
| `is_active` | `BOOLEAN` | No | `true` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Constraints:

```text
PRIMARY KEY (code)
UNIQUE (display_name)
code ~ '^[a-z][a-z0-9_]*$'
length(trim(display_name)) > 0
sort_order >= 0
```

Seed deterministically:

| code | display_name | sort_order |
|---|---|---:|
| `full_time` | Full-time | 10 |
| `part_time` | Part-time | 20 |
| `contract` | Contract | 30 |
| `temporary` | Temporary | 40 |
| `internship` | Internship | 50 |
| `freelance` | Freelance | 60 |
| `other` | Other | 90 |
| `unknown` | Unknown | 99 |

## 6.3 `taxonomy.seniority_levels`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `code` | `VARCHAR(30)` | No | — |
| `display_name` | `VARCHAR(100)` | No | — |
| `rank_order` | `SMALLINT` | No | — |
| `is_management` | `BOOLEAN` | No | `false` |
| `is_active` | `BOOLEAN` | No | `true` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Constraints:

```text
PRIMARY KEY (code)
UNIQUE (display_name)
UNIQUE (rank_order)
code ~ '^[a-z][a-z0-9_]*$'
length(trim(display_name)) > 0
rank_order >= 0
```

Seed deterministically:

| code | display_name | rank_order | management |
|---|---|---:|---:|
| `intern` | Intern | 10 | false |
| `entry` | Entry level | 20 | false |
| `junior` | Junior | 30 | false |
| `mid` | Mid-level | 40 | false |
| `senior` | Senior | 50 | false |
| `lead` | Lead | 60 | false |
| `manager` | Manager | 70 | true |
| `director` | Director | 80 | true |
| `executive` | Executive | 90 | true |
| `unknown` | Unknown | 99 | false |

## 6.4 `taxonomy.occupations`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `taxonomy_version_id` | `UUID` | No | — |
| `canonical_code` | `VARCHAR(100)` | No | — |
| `canonical_name` | `VARCHAR(255)` | No | — |
| `normalized_name` | `VARCHAR(255)` | No | — |
| `parent_id` | `UUID` | Yes | — |
| `description` | `TEXT` | Yes | — |
| `external_system` | `VARCHAR(100)` | Yes | — |
| `external_id` | `VARCHAR(255)` | Yes | — |
| `is_active` | `BOOLEAN` | No | `true` |
| `valid_from` | `TIMESTAMPTZ` | Yes | — |
| `valid_to` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Foreign keys:

```text
taxonomy_version_id → taxonomy.taxonomy_versions(id) ON DELETE RESTRICT
(parent_id, taxonomy_version_id) → taxonomy.occupations(id, taxonomy_version_id) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (id, taxonomy_version_id)
UNIQUE (taxonomy_version_id, canonical_code)
length(trim(canonical_code)) > 0
length(trim(canonical_name)) > 0
length(trim(normalized_name)) > 0
valid_to IS NULL OR valid_from IS NOT NULL
valid_to IS NULL OR valid_to > valid_from
parent_id IS NULL OR parent_id != id
```

Indexes:

```text
ix_occupations__taxonomy_version_id (taxonomy_version_id)
ix_occupations__parent_id (parent_id)
ix_occupations__normalized_name (normalized_name)
ix_occupations__active_name (is_active, canonical_name)
```

Do not make `normalized_name` globally unique.

An explicit PostgreSQL trigger rejects an occupation whose taxonomy version has a
`taxonomy_type` other than `occupation`. The composite parent foreign key ensures that a parent
occupation belongs to the child's taxonomy version.

## 6.5 `taxonomy.occupation_aliases`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `occupation_id` | `UUID` | No | — |
| `source_id` | `UUID` | Yes | — |
| `alias` | `VARCHAR(500)` | No | — |
| `normalized_alias` | `VARCHAR(500)` | No | — |
| `language_code` | `VARCHAR(10)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `is_verified` | `BOOLEAN` | No | `false` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Foreign keys:

```text
occupation_id → taxonomy.occupations(id) ON DELETE CASCADE
source_id → ingestion.sources(id) ON DELETE SET NULL
```

Checks:

```text
length(trim(alias)) > 0
length(trim(normalized_alias)) > 0
confidence IS NULL OR confidence BETWEEN 0 AND 1
```

Partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_occupation_aliases__global
ON taxonomy.occupation_aliases (occupation_id, normalized_alias)
WHERE source_id IS NULL;

CREATE UNIQUE INDEX uq_occupation_aliases__source
ON taxonomy.occupation_aliases (occupation_id, source_id, normalized_alias)
WHERE source_id IS NOT NULL;
```

Indexes:

```text
ix_occupation_aliases__normalized_alias (normalized_alias)
ix_occupation_aliases__source_id (source_id)
```

Aliases must not be globally unique across all occupations.

## 6.6 `taxonomy.skills`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `taxonomy_version_id` | `UUID` | No | — |
| `canonical_code` | `VARCHAR(100)` | No | — |
| `canonical_name` | `VARCHAR(255)` | No | — |
| `normalized_name` | `VARCHAR(255)` | No | — |
| `skill_type` | `VARCHAR(30)` | No | `'other'` |
| `parent_id` | `UUID` | Yes | — |
| `description` | `TEXT` | Yes | — |
| `external_system` | `VARCHAR(100)` | Yes | — |
| `external_id` | `VARCHAR(255)` | Yes | — |
| `is_active` | `BOOLEAN` | No | `true` |
| `valid_from` | `TIMESTAMPTZ` | Yes | — |
| `valid_to` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed `skill_type`:

```text
programming_language
framework
library
database
cloud
devops
tool
platform
methodology
security
data
ai_ml
domain
soft_skill
other
```

Foreign keys:

```text
taxonomy_version_id → taxonomy.taxonomy_versions(id) ON DELETE RESTRICT
(parent_id, taxonomy_version_id) → taxonomy.skills(id, taxonomy_version_id) ON DELETE RESTRICT
```

Constraints and indexes mirror `taxonomy.occupations`:

```text
PRIMARY KEY (id)
UNIQUE (id, taxonomy_version_id)
UNIQUE (taxonomy_version_id, canonical_code)
parent_id IS NULL OR parent_id != id
ix_skills__taxonomy_version_id (taxonomy_version_id)
ix_skills__parent_id (parent_id)
ix_skills__normalized_name (normalized_name)
ix_skills__type_active (skill_type, is_active)
```

Do not create skill co-occurrence or relation tables in Migration 003.

An explicit PostgreSQL trigger rejects a skill whose taxonomy version has a `taxonomy_type` other
than `skill`. The composite parent foreign key ensures that a parent skill belongs to the child's
taxonomy version.

## 6.7 `taxonomy.skill_aliases`

Use the same structure and behavior as `occupation_aliases`, replacing `occupation_id` with `skill_id`.

Foreign keys:

```text
skill_id → taxonomy.skills(id) ON DELETE CASCADE
source_id → ingestion.sources(id) ON DELETE SET NULL
```

Partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_skill_aliases__global
ON taxonomy.skill_aliases (skill_id, normalized_alias)
WHERE source_id IS NULL;

CREATE UNIQUE INDEX uq_skill_aliases__source
ON taxonomy.skill_aliases (skill_id, source_id, normalized_alias)
WHERE source_id IS NOT NULL;
```

---

# 7. Core tables

## 7.1 `core.locations`

Canonical resolved locations, not raw source strings.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `resolution_key` | `VARCHAR(750)` | No | — |
| `location_type` | `VARCHAR(30)` | No | — |
| `country_code` | `CHAR(2)` | Yes | — |
| `admin_level_1` | `VARCHAR(255)` | Yes | — |
| `admin_level_2` | `VARCHAR(255)` | Yes | — |
| `locality` | `VARCHAR(255)` | Yes | — |
| `street_address` | `TEXT` | Yes | — |
| `postal_code` | `VARCHAR(30)` | Yes | — |
| `latitude` | `NUMERIC(9,6)` | Yes | — |
| `longitude` | `NUMERIC(9,6)` | Yes | — |
| `canonical_label` | `VARCHAR(750)` | No | — |
| `normalized_label` | `VARCHAR(750)` | No | — |
| `geocoding_provider` | `VARCHAR(100)` | Yes | — |
| `geocoding_version` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed `location_type`:

```text
country | region | province | city | district | address | remote_scope | other
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (resolution_key)
length(trim(resolution_key)) > 0
length(trim(canonical_label)) > 0
length(trim(normalized_label)) > 0
country_code IS NULL OR country_code ~ '^[A-Z]{2}$'
latitude IS NULL OR latitude BETWEEN -90 AND 90
longitude IS NULL OR longitude BETWEEN -180 AND 180
(latitude IS NULL) = (longitude IS NULL)
confidence IS NULL OR confidence BETWEEN 0 AND 1
```

Indexes:

```text
ix_locations__normalized_label (normalized_label)
ix_locations__country_admin (country_code, admin_level_1, admin_level_2, locality)
ix_locations__type (location_type)
```

Do not add PostGIS in this migration.

## 7.2 `core.companies`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `canonical_name` | `VARCHAR(500)` | No | — |
| `normalized_name` | `VARCHAR(500)` | No | — |
| `legal_name` | `VARCHAR(500)` | Yes | — |
| `company_type` | `VARCHAR(30)` | No | `'unknown'` |
| `headquarters_location_id` | `UUID` | Yes | — |
| `website_url` | `TEXT` | Yes | — |
| `employee_count_min` | `INTEGER` | Yes | — |
| `employee_count_max` | `INTEGER` | Yes | — |
| `resolution_status` | `VARCHAR(30)` | No | `'provisional'` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed values:

```text
company_type:
employer | recruitment_agency | outsourcing | consulting | government |
education | nonprofit | unknown | other

resolution_status:
unresolved | provisional | verified | merged | retired
```

Foreign key:

```text
headquarters_location_id → core.locations(id) ON DELETE SET NULL
```

Checks:

```text
length(trim(canonical_name)) > 0
length(trim(normalized_name)) > 0
website_url IS NULL OR website_url ~ '^https?://'
employee_count_min IS NULL OR employee_count_min >= 0
employee_count_max IS NULL OR employee_count_max >= 0
employee_count_min IS NULL OR employee_count_max IS NULL
    OR employee_count_min <= employee_count_max
```

Indexes:

```text
ix_companies__normalized_name (normalized_name)
ix_companies__resolution_status (resolution_status)
ix_companies__headquarters_location_id (headquarters_location_id)
```

Do **not** make `normalized_name` unique.

## 7.3 `core.company_aliases`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `company_id` | `UUID` | No | — |
| `source_id` | `UUID` | Yes | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
| `alias` | `VARCHAR(500)` | No | — |
| `normalized_alias` | `VARCHAR(500)` | No | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `is_verified` | `BOOLEAN` | No | `false` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Foreign keys:

```text
company_id → core.companies(id) ON DELETE CASCADE
source_id → ingestion.sources(id) ON DELETE SET NULL
extracted_record_id → ingestion.extracted_records(id) ON DELETE SET NULL
```

Checks:

```text
length(trim(alias)) > 0
length(trim(normalized_alias)) > 0
confidence IS NULL OR confidence BETWEEN 0 AND 1
```

Partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_company_aliases__global
ON core.company_aliases (company_id, normalized_alias)
WHERE source_id IS NULL;

CREATE UNIQUE INDEX uq_company_aliases__source
ON core.company_aliases (company_id, source_id, normalized_alias)
WHERE source_id IS NOT NULL;
```

Indexes:

```text
ix_company_aliases__normalized_alias (normalized_alias)
ix_company_aliases__source_id (source_id)
ix_company_aliases__extracted_record_id (extracted_record_id)
```

## 7.4 `core.company_domains`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `company_id` | `UUID` | No | — |
| `source_id` | `UUID` | Yes | — |
| `domain` | `VARCHAR(255)` | No | — |
| `domain_type` | `VARCHAR(30)` | No | `'corporate'` |
| `is_verified` | `BOOLEAN` | No | `false` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed `domain_type`:

```text
corporate | career | email | social | other
```

Foreign keys:

```text
company_id → core.companies(id) ON DELETE CASCADE
source_id → ingestion.sources(id) ON DELETE SET NULL
```

Checks:

```text
domain = lower(domain)
domain ~ '^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$'
position('.' in domain) > 0
```

Constraint:

```text
UNIQUE (company_id, domain, domain_type)
```

Do not make domain globally unique.

Indexes:

```text
ix_company_domains__domain (domain)
ix_company_domains__source_id (source_id)
```

## 7.5 `core.job_postings`

Current canonical state of one posting from one source.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `source_id` | `UUID` | No | — |
| `source_job_id` | `VARCHAR(255)` | No | — |
| `latest_extracted_record_id` | `BIGINT` | Yes | — |
| `company_id` | `UUID` | Yes | — |
| `source_url` | `TEXT` | No | — |
| `canonical_url` | `TEXT` | Yes | — |
| `title_raw` | `TEXT` | No | — |
| `title_normalized` | `TEXT` | Yes | — |
| `company_name_raw` | `TEXT` | Yes | — |
| `company_name_status` | `VARCHAR(30)` | No | `'unverified'` |
| `location_raw` | `TEXT` | Yes | — |
| `employment_type_code` | `VARCHAR(30)` | Yes | — |
| `seniority_level_code` | `VARCHAR(30)` | Yes | — |
| `work_mode` | `VARCHAR(30)` | Yes | — |
| `experience_min_years` | `NUMERIC(6,2)` | Yes | — |
| `experience_max_years` | `NUMERIC(6,2)` | Yes | — |
| `current_status` | `VARCHAR(20)` | No | `'unknown'` |
| `posted_at` | `TIMESTAMPTZ` | Yes | — |
| `expires_at` | `TIMESTAMPTZ` | Yes | — |
| `first_seen_at` | `TIMESTAMPTZ` | No | — |
| `last_seen_at` | `TIMESTAMPTZ` | No | — |
| `last_changed_at` | `TIMESTAMPTZ` | No | — |
| `closed_at` | `TIMESTAMPTZ` | Yes | — |
| `source_content_hash` | `CHAR(64)` | Yes | — |
| `canonical_hash` | `CHAR(64)` | Yes | — |
| `extractor_version` | `VARCHAR(100)` | Yes | — |
| `normalization_version` | `VARCHAR(100)` | Yes | — |
| `confidence_score` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed values:

```text
company_name_status:
disclosed | hidden_by_source | absent | parse_error | unverified

work_mode:
onsite | hybrid | remote | flexible | unknown

current_status:
active | expired | closed | removed | unknown
```

Foreign keys:

```text
source_id → ingestion.sources(id) ON DELETE RESTRICT
(latest_extracted_record_id, source_id, source_job_id) →
  ingestion.extracted_records(id, source_id, source_job_id)
  ON DELETE SET NULL (latest_extracted_record_id)
company_id → core.companies(id) ON DELETE RESTRICT
employment_type_code → taxonomy.employment_types(code) ON DELETE RESTRICT
seniority_level_code → taxonomy.seniority_levels(code) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (source_id, source_job_id)
length(trim(source_job_id)) > 0
length(trim(title_raw)) > 0
source_url ~ '^https?://'
canonical_url IS NULL OR canonical_url ~ '^https?://'
experience_min_years IS NULL OR experience_min_years >= 0
experience_max_years IS NULL OR experience_max_years >= 0
experience_min_years IS NULL OR experience_max_years IS NULL
    OR experience_min_years <= experience_max_years
confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1
source_content_hash IS NULL OR source_content_hash ~ '^[0-9a-f]{64}$'
canonical_hash IS NULL OR canonical_hash ~ '^[0-9a-f]{64}$'
last_seen_at >= first_seen_at
last_changed_at >= first_seen_at
closed_at IS NULL OR closed_at >= first_seen_at
expires_at IS NULL OR posted_at IS NULL OR expires_at >= posted_at
```

Do not require `posted_at`.

Indexes:

```text
ix_job_postings__company_id (company_id)
ix_job_postings__status_last_seen (current_status, last_seen_at DESC)
ix_job_postings__posted_at (posted_at DESC) WHERE posted_at IS NOT NULL
ix_job_postings__employment_type (employment_type_code)
ix_job_postings__seniority (seniority_level_code)
ix_job_postings__work_mode (work_mode)
ix_job_postings__canonical_url (canonical_url) WHERE canonical_url IS NOT NULL
ix_job_postings__latest_extracted_record_id (latest_extracted_record_id)
```

Do not add full-text or trigram indexes yet.

## 7.6 `core.job_posting_descriptions`

Current retained description only; historical versions come later.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `job_posting_id` | `UUID` | No | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
| `description_text` | `TEXT` | No | — |
| `description_format` | `VARCHAR(20)` | No | `'plain'` |
| `language_code` | `VARCHAR(10)` | Yes | — |
| `content_hash` | `CHAR(64)` | No | — |
| `redaction_status` | `VARCHAR(30)` | No | `'not_required'` |
| `retained_until` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed values:

```text
description_format: plain | html | markdown
redaction_status: not_required | pending | redacted | failed
```

Foreign keys:

```text
job_posting_id → core.job_postings(id) ON DELETE CASCADE
extracted_record_id → ingestion.extracted_records(id) ON DELETE SET NULL
```

Constraints:

```text
PRIMARY KEY (job_posting_id)
length(trim(description_text)) > 0
content_hash ~ '^[0-9a-f]{64}$'
```

Indexes:

```text
ix_job_posting_descriptions__extracted_record_id (extracted_record_id)
ix_job_posting_descriptions__retained_until (retained_until)
    WHERE retained_until IS NOT NULL
```

Application code must enforce source retention policy before storage.

## 7.7 `core.job_posting_locations`

Supports multiple locations per posting.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `location_id` | `UUID` | No | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
| `relationship_type` | `VARCHAR(30)` | No | `'workplace'` |
| `is_primary` | `BOOLEAN` | No | `false` |
| `is_remote` | `BOOLEAN` | No | `false` |
| `remote_scope` | `VARCHAR(30)` | Yes | — |
| `source_text` | `TEXT` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed values:

```text
relationship_type:
workplace | applicant_eligible | company_office | relocation_destination | other

remote_scope:
vietnam | asia | timezone_limited | worldwide | unspecified
```

Foreign keys:

```text
job_posting_id → core.job_postings(id) ON DELETE CASCADE
location_id → core.locations(id) ON DELETE RESTRICT
extracted_record_id → ingestion.extracted_records(id) ON DELETE SET NULL
```

Constraints:

```text
UNIQUE (job_posting_id, location_id, relationship_type)
confidence IS NULL OR confidence BETWEEN 0 AND 1
is_remote = (remote_scope IS NOT NULL)
```

Only one primary location per relationship type:

```sql
CREATE UNIQUE INDEX uq_job_posting_locations__one_primary
ON core.job_posting_locations (job_posting_id, relationship_type)
WHERE is_primary;
```

Indexes:

```text
ix_job_posting_locations__location_id (location_id)
ix_job_posting_locations__job_posting_id (job_posting_id)
ix_job_posting_locations__remote (is_remote, remote_scope)
ix_job_posting_locations__extracted_record_id (extracted_record_id)
```

## 7.8 `core.salary_offers`

One posting may have multiple compensation components.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
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
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed values:

```text
period: hour | day | week | month | year | project | unknown
compensation_type:
base_salary | total_compensation | bonus | commission | equity | allowance | other
tax_basis: gross | net | unknown
```

Foreign keys:

```text
job_posting_id → core.job_postings(id) ON DELETE CASCADE
extracted_record_id → ingestion.extracted_records(id) ON DELETE SET NULL
```

Checks:

```text
all amount fields are NULL or >= 0
amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max
normalized_monthly_min IS NULL OR normalized_monthly_max IS NULL
    OR normalized_monthly_min <= normalized_monthly_max
normalized_annual_min IS NULL OR normalized_annual_max IS NULL
    OR normalized_annual_min <= normalized_annual_max
currency IS NULL OR currency ~ '^[A-Z]{3}$'
(fx_rate IS NULL) = (fx_rate_date IS NULL)
fx_rate IS NULL OR fx_rate > 0
confidence IS NULL OR confidence BETWEEN 0 AND 1
```

Disclosure semantics:

```text
is_disclosed
OR is_estimated
OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL)

NOT is_disclosed
OR amount_min IS NOT NULL
OR amount_max IS NOT NULL
OR amount_exact IS NOT NULL

NOT (is_negotiable AND NOT is_disclosed)
OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL)
```

Do not require currency/period for nondisclosed salary.

Indexes:

```text
ix_salary_offers__job_posting_id (job_posting_id)
ix_salary_offers__currency_period (currency, period) WHERE currency IS NOT NULL
ix_salary_offers__disclosed (is_disclosed)
ix_salary_offers__normalized_monthly
    (currency, normalized_monthly_min, normalized_monthly_max)
    WHERE normalized_monthly_min IS NOT NULL OR normalized_monthly_max IS NOT NULL
ix_salary_offers__extracted_record_id (extracted_record_id)
```

## 7.9 `core.job_posting_skills`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `skill_id` | `UUID` | No | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
| `requirement_type` | `VARCHAR(20)` | No | `'mentioned'` |
| `evidence_text` | `TEXT` | Yes | — |
| `evidence_section` | `VARCHAR(100)` | Yes | — |
| `extraction_method` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed `requirement_type`:

```text
required | preferred | mentioned | unknown
```

Foreign keys:

```text
job_posting_id → core.job_postings(id) ON DELETE CASCADE
skill_id → taxonomy.skills(id) ON DELETE RESTRICT
extracted_record_id → ingestion.extracted_records(id) ON DELETE SET NULL
```

Constraints:

```text
UNIQUE (job_posting_id, skill_id, requirement_type)
confidence IS NULL OR confidence BETWEEN 0 AND 1
```

Indexes:

```text
ix_job_posting_skills__skill_id (skill_id)
ix_job_posting_skills__job_posting_id (job_posting_id)
ix_job_posting_skills__requirement_type (requirement_type)
ix_job_posting_skills__extracted_record_id (extracted_record_id)
```

## 7.10 `core.job_posting_occupations`

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `job_posting_id` | `UUID` | No | — |
| `occupation_id` | `UUID` | No | — |
| `extracted_record_id` | `BIGINT` | Yes | — |
| `is_primary` | `BOOLEAN` | No | `false` |
| `classification_method` | `VARCHAR(100)` | Yes | — |
| `classifier_version` | `VARCHAR(100)` | Yes | — |
| `confidence` | `NUMERIC(5,4)` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Foreign keys:

```text
job_posting_id → core.job_postings(id) ON DELETE CASCADE
occupation_id → taxonomy.occupations(id) ON DELETE RESTRICT
extracted_record_id → ingestion.extracted_records(id) ON DELETE SET NULL
```

Constraints:

```text
UNIQUE (job_posting_id, occupation_id)
confidence IS NULL OR confidence BETWEEN 0 AND 1
```

Only one primary occupation:

```sql
CREATE UNIQUE INDEX uq_job_posting_occupations__one_primary
ON core.job_posting_occupations (job_posting_id)
WHERE is_primary;
```

Indexes:

```text
ix_job_posting_occupations__occupation_id (occupation_id)
ix_job_posting_occupations__job_posting_id (job_posting_id)
ix_job_posting_occupations__extracted_record_id (extracted_record_id)
```

---

# 8. Creation and downgrade order

Upgrade order:

1. Create `taxonomy` and `core` schemas.
2. Revoke public privileges.
3. Add the supporting extracted-record source-identity uniqueness.
4. Create `taxonomy.taxonomy_versions`, the entity-type enforcement function, and the
   taxonomy-type immutability function/trigger.
5. Create and seed `taxonomy.employment_types`.
6. Create and seed `taxonomy.seniority_levels`.
7. Create occupations and occupation aliases, including the occupation-type trigger.
8. Create skills and skill aliases, including the skill-type trigger.
9. Create `core.locations`.
10. Create companies, company aliases, and company domains.
11. Create `core.job_postings`.
12. Create descriptions, posting locations, salaries, posting skills, and posting occupations.
13. Create indexes.

Downgrade in exact reverse dependency order.

Downgrade must remove only Migration 003 objects and schemas. It must not remove `system` or `ingestion`.

# 9. SQLAlchemy requirements

Extend:

```text
src/it_labor_market_intelligence/database/v1_models/
├── __init__.py
├── base.py
├── system.py
├── ingestion.py
├── taxonomy.py
└── core.py
```

Requirements:

- continue using `V1Base`;
- declare schemas explicitly;
- use schema-qualified foreign keys;
- use PostgreSQL `UUID` and `JSONB` types;
- use server defaults for UUIDs, timestamps, booleans, JSONB, and identity IDs;
- keep ORM metadata aligned with migration columns, nullability, defaults, and keys;
- do not add generic destructive repository methods;
- do not replace the Phase 3 API models in this task.

# 10. Service boundary

Migration 003 is a storage task.

Do not implement a large canonical importer in the same PR.

A later task will implement:

```text
accepted ingestion.extracted_records
→ canonical normalization
→ upsert core.job_postings
→ update current child rows
→ record history in Migration 004
```

Do not claim historical change tracking is complete.

# 11. PostgreSQL integration tests

Extend the existing Database V1 integration suite or add:

```text
tests/integration/database/test_database_v1_core.py
```

Required tests:

## Schema and migration

- `taxonomy` and `core` exist;
- exactly the specified tables exist;
- Alembic head is Migration 003;
- downgrade to Migration 002 removes only Migration 003;
- re-upgrade succeeds;
- Migration 001/002 tables remain after downgrade.

## Reference rows

- all required employment-type codes exist;
- all required seniority codes exist.

## Taxonomy versions

- changing a skill taxonomy version to occupation is rejected;
- changing an occupation taxonomy version to skill is rejected;
- valid taxonomy-version name or status updates are accepted.

## Companies

- duplicate company `normalized_name` values are allowed;
- blank company names are rejected;
- invalid employee ranges are rejected;
- duplicate alias for same company/source is rejected;
- same alias may belong to different candidate companies;
- domains containing scheme/path are rejected;
- deleting a company referenced by a job is restricted.

## Locations

- valid locations insert successfully;
- invalid latitude/longitude is rejected;
- latitude without longitude is rejected;
- duplicate `resolution_key` is rejected;
- one posting supports multiple locations;
- only one primary location per relationship type;
- remote rows require `remote_scope`;
- non-remote rows reject a non-null `remote_scope`.

## Job postings

- duplicate `(source_id, source_job_id)` is rejected;
- same source job ID across different sources is allowed;
- invalid URL is rejected;
- blank title is rejected;
- negative experience is rejected;
- min experience greater than max is rejected;
- invalid confidence/hash is rejected;
- invalid first/last-seen ordering is rejected;
- `closed_at` before `first_seen_at` is rejected;
- deleting a source with postings is restricted;
- matching extracted-record identity is accepted;
- extracted records with another source or source job ID are rejected;
- deleting the linked extracted record sets only `latest_extracted_record_id` to null without
  modifying the posting source identity.

## Descriptions

- only one current description per job;
- empty description and invalid hash are rejected;
- deleting a job cascades to the description.

## Salaries

- disclosed numeric salary is accepted;
- disclosed salary without numeric amount is rejected;
- nondisclosed negotiable salary with null numeric values is accepted;
- nondisclosed negotiable salary with numeric values is rejected;
- negative salary and reversed ranges are rejected;
- invalid currency is rejected;
- FX rate/date must appear together;
- monthly normalized ranges are ordered;
- monthly and yearly rows remain separate valid records;
- deleting a job cascades to salary rows.

## Skills

- multiple skills per posting are supported;
- the same skill with different requirement types is allowed;
- duplicate `(job, skill, requirement_type)` is rejected;
- invalid confidence is rejected;
- deleting referenced skills is restricted;
- aliases are not globally unique across different skills;
- a non-skill taxonomy version is rejected;
- a parent from another taxonomy version is rejected.

## Occupations

- one primary plus multiple secondary occupations are supported;
- a second primary occupation is rejected;
- duplicate occupation assignment is rejected;
- a non-occupation taxonomy version is rejected;
- a parent from another taxonomy version is rejected;
- deleting referenced occupations is restricted;
- aliases are not globally unique across different occupations.

# 12. CI

Keep the existing PostgreSQL 16 CI service.

All must pass:

```text
alembic upgrade head
alembic current
pytest
Ruff
Black
MyPy
```

Do not weaken or skip existing integration tests.

# 13. Security

`taxonomy` and `core` remain private internal schemas.

Do not grant direct access to:

```text
PUBLIC
anon
authenticated
```

Do not store credentials, cookies, authorization headers, secret environment values, or unredacted private contact data in core/taxonomy metadata.

Serving views and RLS belong in a later migration.

# 14. Documentation

Update:

```text
README.md
docs/DATABASE_DESIGN.md
docs/DATABASE_V1_FOUNDATION.md
docs/DATA_IMPORT_RUNBOOK.md
```

Create:

```text
docs/DATABASE_V1_CORE.md
```

Document:

- source posting identity;
- why company normalized names are not unique;
- multi-location support;
- salary disclosure rules;
- taxonomy versioning;
- current-state versus history boundary;
- downgrade procedure;
- current API compatibility limitation;
- next migration scope.

# 15. Out of scope

Do not implement:

```text
history.job_observations
history.job_change_events
history.job_status_events
quality.field_evidence
quality issue redesign
duplicate candidate/cluster redesign
skill relation graph
skill co-occurrence
industry/language/benefit taxonomies
analytics facts or aggregates
materialized views
Supabase RPC or RLS
users, resumes, applications
recommendations
embeddings or LLM enrichment
full canonical importer
API migration
dashboard or crawler changes
PostGIS or vector extensions
```

# 16. Acceptance criteria

- [ ] Migration 003 directly follows Migration 002.
- [ ] `taxonomy` and `core` schemas are created and private.
- [ ] Exactly 17 specified tables are created.
- [ ] Reference seed rows are deterministic.
- [ ] Explicit DDL only; no metadata-driven create/drop.
- [ ] No `DROP ... CASCADE`.
- [ ] Safe downgrade preserves Migration 001/002.
- [ ] Company normalized names are not unique.
- [ ] Job source identity is unique by source and source job ID.
- [ ] Multi-location postings work.
- [ ] Salary remains separate by component/period/currency/tax basis.
- [ ] Undisclosed negotiable salary cannot contain source numeric amounts.
- [ ] One primary occupation is enforced.
- [ ] Multiple secondary occupations work.
- [ ] Skill requirement types are preserved.
- [ ] Current description is separated from the main posting row.
- [ ] Required lineage FKs exist.
- [ ] PostgreSQL tests pass.
- [ ] Ruff, Black, MyPy, and existing tests pass.
- [ ] Documentation is updated.
- [ ] No out-of-scope features are added.

# 17. Codex workflow

1. Read `AGENT_RULES.md`.
2. Read this specification.
3. Read Migration 001 and 002.
4. Read current `v1_models` and integration tests.
5. Implement explicit Migration 003.
6. Add `taxonomy.py` and `core.py`.
7. Export the models in `v1_models/__init__.py`.
8. Add PostgreSQL integration tests.
9. Update documentation.
10. Run all checks.
11. Create a focused branch and draft PR into `main`.
12. Do not merge.
13. Report changed files, migration revision, table inventory, test/CI results, unresolved risks, and scope confirmation.

# 18. Prompt to give Codex

```text
Read AGENT_RULES.md and DATABASE_V1_MIGRATION_003_SPEC.md.

Implement Database V1 Migration 003 exactly as specified.

Do not add history, analytics, serving, deduplication, users, resumes, recommendations, embeddings, LLM, dashboard, crawler, API migration, or a full canonical importer.

Use explicit Alembic DDL. Add schema-qualified SQLAlchemy models, PostgreSQL integration tests, CI-compatible validation, and documentation.

Create a new branch and a draft pull request into main. Do not merge. Report the PR link and final CI status.
```

# 19. Human review checklist

- [ ] No company merge is forced by normalized name.
- [ ] Source postings remain separate.
- [ ] Locations are repeatable.
- [ ] Salary is not flattened onto `job_postings`.
- [ ] Skills and occupations are versioned.
- [ ] No history claims are made.
- [ ] DDL and downgrade are explicit and safe.
- [ ] Partial unique indexes correctly handle primary location/occupation.
- [ ] PostgreSQL `NULL` behavior is tested in salary and conditional checks.
- [ ] Foreign-key delete actions match the specification.
- [ ] No importer/API/dashboard refactor is included.
