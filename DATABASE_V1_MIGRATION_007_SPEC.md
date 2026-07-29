# Database V1 — Migration 007 Operations Hardening & Recovery

**Repository:** `DangKhoa257/IT-Labor-Market-Intelligence-Platform`  
**Database:** PostgreSQL 16 / Supabase-compatible PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration tool:** Alembic  
**Audience:** Codex implementation agent  
**Status:** Implementation-ready specification  
**Scope:** security hardening, performance hardening, retention/archive control,
backup/restore readiness, operational health, and release-readiness contracts

---

## 1. Goal

Migration 007 completes the major Database V1 structural work.

Migrations 001–006 already provide:

```text
system
ingestion
taxonomy
core
history
quality
analytics
serving
api
```

Migration 007 adds:

```text
operations
```

It must provide database-level contracts for:

- least-privilege security verification;
- RLS and grant auditing;
- detection of unsafe API functions;
- performance and storage health;
- advisory partition planning;
- controlled retention and archival authorization;
- archive manifests and checksums;
- backup inventory and verification;
- restore-drill evidence;
- maintenance and health-check history;
- deployment/release readiness.

Migration 007 stores and validates operational evidence. It does not execute
cloud-provider backups, upload archive files, delete retained data, schedule
jobs, or repartition populated production tables.

---

## 2. Database V1 boundary

Migration 007 is expected to be the final major Database V1 schema migration.

After Migration 007, normal development should prefer:

```text
small corrective migrations
measured index changes
new API contract versions
application workers
deployment automation
backfill operations
```

An optional Migration 008 may later contain narrowly scoped backfill or
scheduler-support changes. It is not required to declare Database V1 structurally
complete.

---

## 3. Non-negotiable rules

1. Use explicit Alembic DDL.
2. Do not use `Base.metadata.create_all()` or `Base.metadata.drop_all()`.
3. Do not use `DROP ... CASCADE`.
4. Use schema-qualified PostgreSQL names.
5. Use `TIMESTAMPTZ` for timestamps.
6. Use PostgreSQL `JSONB`, not generic JSON.
7. Do not create PostgreSQL native enum types.
8. Do not store passwords, database connection strings, access tokens,
   encryption keys, private keys, cookies, or provider credentials.
9. Provider object IDs, key references, checksums, and storage URIs are allowed.
10. The `operations` schema is private and must never be exposed through the
    Supabase Data API.
11. `anon` and `authenticated` receive no `operations` access.
12. `PUBLIC` receives no `operations` access or function execution.
13. Only `service_role` receives operational DML and function execution.
14. Enable RLS on every `operations` table and create no client policies.
15. Retention authorization must never execute arbitrary SQL.
16. A retention function may authorize deletion, but it must not perform the
    physical deletion.
17. No destructive run may be authorized when a legal hold is active.
18. Archive-required policies must have a verified manifest before deletion is
    authorized.
19. Archive and backup checksums use lowercase SHA-256.
20. A successful restore drill requires all mandatory critical checks to pass.
21. Partition conversion of existing populated tables is out of scope.
22. Partition policies are advisory metadata until a dedicated migration
    implements them.
23. Index changes must be additive and must not remove existing indexes.
24. Existing Migration 001–006 tests must remain green.
25. Do not weaken Migration 006 API security or grants.
26. Do not implement frontend, crawler, analytics, serving, recommendation,
    user, resume, embedding, or LLM features.

---

## 4. Migration identity

Suggested revision:

```text
20260728_0007
```

Required:

```text
down_revision = "20260727_0006"
```

Create:

```sql
CREATE SCHEMA IF NOT EXISTS operations;
REVOKE ALL ON SCHEMA operations FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA operations TO service_role;
```

---

# 5. Exact object inventory

## Tables — 12

```text
operations.partition_policies
operations.retention_policies
operations.retention_runs
operations.retention_run_items
operations.archive_manifests
operations.archive_objects
operations.backup_snapshots
operations.restore_drills
operations.restore_drill_checks
operations.maintenance_runs
operations.health_check_runs
operations.health_check_results
```

## Views — 7

```text
operations.v_security_privilege_violations
operations.v_unindexed_foreign_keys
operations.v_table_storage_health
operations.v_data_freshness
operations.v_backup_restore_readiness
operations.v_retention_readiness
operations.v_release_readiness
```

## Callable operational functions — 6

```text
operations.assert_security_baseline_v1
operations.authorize_retention_delete_v1
operations.finalize_archive_manifest_v1
operations.finalize_backup_snapshot_v1
operations.finalize_restore_drill_v1
operations.finalize_health_check_run_v1
```

## Internal trigger functions

```text
operations.enforce_run_lifecycle
operations.protect_finalized_operational_record
operations.protect_policy_identity
operations.protect_archive_object_after_verification
```

No object in `operations` is a public application API.

---

# 6. Shared conventions

## 6.1 Status timestamps

For run-like tables:

```text
pending
→ started_at IS NULL
→ finished_at IS NULL

running or another active processing state
→ started_at IS NOT NULL
→ finished_at IS NULL

terminal state
→ started_at IS NOT NULL
→ finished_at IS NOT NULL
→ finished_at >= started_at
```

## 6.2 Identity immutability

After a row has dependent evidence, or after it reaches a terminal/verified
state, its identity and lineage fields must not change.

## 6.3 JSON objects

Unless explicitly documented as an array:

```text
jsonb_typeof(value) = 'object'
```

## 6.4 SHA-256

All SHA-256 fields must satisfy:

```text
^[0-9a-f]{64}$
```

## 6.5 Finalization

Finalization functions must:

1. lock the parent row `FOR UPDATE`;
2. inspect all required child evidence;
3. reject invalid state with SQLSTATE `23514`;
4. update the parent in one transaction;
5. prevent later evidence mutation that would invalidate the result.

Finalizer-only transitions use the trusted `SECURITY DEFINER` function-owner
execution context, observed by non-`SECURITY DEFINER` lifecycle triggers.
Custom GUC values are not an authorization boundary. The migration/schema owner
is an administrative principal and is explicitly trusted for migration work.

Retention-item transitions are forward-only. Archive-required items progress
from `candidate` to `archived`, `skipped`, or `failed`, and only the retention
authorization function can move an archived item to `delete_authorized`.
No-archive candidates may instead be authorized by that function. Skipped and
failed items remain unchanged; an authorized item can become `deleted` only
while its parent run is authorized or deleting. That deletion-evidence update
may change only `status` and `updated_at`; target identity, timestamps, archive
lineage, checksum, error evidence, and creation time remain immutable. A
terminal parent makes every child mutation immutable.

An authorized item may instead transition once to `failed` while its parent is
authorized or deleting, provided it records a nonblank error message. This
transition freezes the same identity, archive lineage, checksum, and creation
evidence as deletion; no failed or deleted item can move again.

Before a `deleting` retention run becomes terminal, PostgreSQL locks and counts
its items. Parent counters must exactly match deleted, skipped, and failed
items, and no candidate, archived, or authorized item may remain. `succeeded`
requires no failures; `partially_succeeded` requires both deletions and
failures; `failed` requires failures and no deletions. Archive-required runs
report archived count as deleted plus failed items, while no-archive runs keep
that count at zero.

Execution identities freeze when a run starts or its child evidence begins.
Archive manifests, backup evidence, restore drills, health checks, and
maintenance runs preserve their defining identity through processing and
finalization. Provider locations and key references must be non-secret: no
PostgreSQL connection URI, credentials, JWT/key material, user-info, query, or
fragment is permitted.

Verified backup evidence is completely immutable. Its only permitted lifecycle
updates are `succeeded → expired → deleted`; those updates may change only
`status` and `updated_at` and preserve successful backup timestamps.

---

# 7. `operations.partition_policies`

Advisory partition plan for large append-only tables. Migration 007 does not
physically partition any existing table.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `target_schema` | `VARCHAR(63)` | No | — |
| `target_table` | `VARCHAR(63)` | No | — |
| `partition_key` | `VARCHAR(63)` | No | — |
| `partition_strategy` | `VARCHAR(20)` | No | `'range'` |
| `partition_interval` | `VARCHAR(20)` | No | `'month'` |
| `activation_row_threshold` | `BIGINT` | No | — |
| `retention_partition_count` | `INTEGER` | Yes | — |
| `status` | `VARCHAR(20)` | No | `'advisory'` |
| `approved_by` | `VARCHAR(255)` | Yes | — |
| `approved_at` | `TIMESTAMPTZ` | Yes | — |
| `implemented_revision` | `VARCHAR(100)` | Yes | — |
| `rationale` | `TEXT` | No | — |
| `configuration_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed strategy:

```text
range
list
hash
```

Allowed interval:

```text
day
week
month
quarter
year
custom
```

Allowed status:

```text
advisory
planned
approved
implemented
disabled
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (target_schema, target_table)
target identifiers and partition key are nonblank
activation_row_threshold > 0
retention_partition_count IS NULL OR retention_partition_count > 0
jsonb_typeof(configuration_json) = 'object'
approved status requires approved_by and approved_at
implemented status requires implemented_revision
```

Validate the target relation and partition-key column through PostgreSQL
catalogs. The validator may use `to_regclass`; it must not execute dynamic SQL.

Seed exactly these advisory rows:

| Target | Key | Interval | Activation threshold |
|---|---|---:|---:|
| `history.job_observations` | `observed_at` | month | 5,000,000 |
| `history.job_status_events` | `event_at` | month | 2,000,000 |
| `history.job_change_events` | `detected_at` | month | 5,000,000 |
| `analytics.fact_job_observations` | `loaded_at` | month | 5,000,000 |
| `analytics.fact_salary_observations` | `loaded_at` | month | 5,000,000 |
| `quality.data_quality_issues` | `detected_at` | quarter | 2,000,000 |

All seeded rows remain `advisory`.

Indexes:

```text
(status, target_schema, target_table)
(activation_row_threshold)
```

Once status is `approved` or `implemented`, target identity, partition key,
strategy, interval, and threshold are immutable.

---

# 8. `operations.retention_policies`

A reviewed policy contract. It does not execute retention.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `policy_code` | `VARCHAR(100)` | No | — |
| `target_schema` | `VARCHAR(63)` | No | — |
| `target_table` | `VARCHAR(63)` | No | — |
| `record_class` | `VARCHAR(50)` | No | — |
| `time_column` | `VARCHAR(63)` | No | — |
| `archive_after_days` | `INTEGER` | Yes | — |
| `delete_after_days` | `INTEGER` | Yes | — |
| `batch_size` | `INTEGER` | No | `1000` |
| `requires_archive` | `BOOLEAN` | No | `true` |
| `legal_hold` | `BOOLEAN` | No | `false` |
| `legal_hold_reason` | `TEXT` | Yes | — |
| `enabled` | `BOOLEAN` | No | `false` |
| `policy_version` | `VARCHAR(100)` | No | — |
| `selection_contract_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_by` | `VARCHAR(255)` | No | — |
| `approved_by` | `VARCHAR(255)` | Yes | — |
| `approved_at` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed `record_class`:

```text
raw_payload
fetch_event
description_text
temporary_evidence
operational_log
other
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (policy_code)
UNIQUE (target_schema, target_table, record_class)
identifiers, policy code/version, and created_by are nonblank
archive_after_days IS NULL OR archive_after_days >= 0
delete_after_days IS NULL OR delete_after_days >= 0
both days NULL is forbidden
when both exist, delete_after_days >= archive_after_days
batch_size BETWEEN 1 AND 100000
jsonb_typeof(selection_contract_json) = 'object'
legal_hold requires a nonblank legal_hold_reason
enabled requires approved_by and approved_at
```

Validate the target relation and time-column existence through catalogs. Do not
execute the selection contract.

After any retention run references the policy, its target identity, windows,
archive requirement, and policy version are immutable. Legal hold may always
move from false to true. Clearing a hold requires a new policy version and
fresh approval.

Migration 007 must not enable a destructive policy by default.

Indexes:

```text
(enabled, legal_hold)
(target_schema, target_table)
(policy_version)
```

---

# 9. `operations.retention_runs`

One dry-run or execution attempt under one policy.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `policy_id` | `UUID` | No | — |
| `status` | `VARCHAR(30)` | No | `'pending'` |
| `dry_run` | `BOOLEAN` | No | `true` |
| `cutoff_at` | `TIMESTAMPTZ` | No | — |
| `candidate_count` | `BIGINT` | No | `0` |
| `archived_count` | `BIGINT` | No | `0` |
| `deleted_count` | `BIGINT` | No | `0` |
| `skipped_count` | `BIGINT` | No | `0` |
| `failed_count` | `BIGINT` | No | `0` |
| `requested_by` | `VARCHAR(255)` | No | — |
| `delete_authorized_by` | `VARCHAR(255)` | Yes | — |
| `delete_authorized_at` | `TIMESTAMPTZ` | Yes | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `metrics_json` | `JSONB` | No | `'{}'::jsonb` |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed status:

```text
pending
running
archive_pending
archive_verified
delete_authorized
deleting
succeeded
partially_succeeded
failed
cancelled
```

Foreign key:

```text
policy_id → operations.retention_policies(id) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
requested_by is nonblank
all counters >= 0 and each <= candidate_count
jsonb_typeof(metrics_json) = 'object'
dry-run rows cannot enter delete_authorized or deleting
delete_authorized status requires actor and timestamp
terminal timestamps follow shared lifecycle rules
```

Forward lifecycle:

```text
pending → running/cancelled
running → archive_pending/archive_verified/failed/cancelled
archive_pending → archive_verified/failed/cancelled
archive_verified → delete_authorized/succeeded/partially_succeeded/failed/cancelled
delete_authorized → deleting/cancelled
deleting → succeeded/partially_succeeded/failed
```

Only `authorize_retention_delete_v1` may set `delete_authorized`.

Indexes:

```text
(policy_id, created_at DESC)
(status, created_at DESC)
(cutoff_at)
```

---

# 10. `operations.retention_run_items`

Per-record evidence. Do not store the full retained record.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `retention_run_id` | `UUID` | No | — |
| `target_record_key` | `TEXT` | No | — |
| `record_timestamp` | `TIMESTAMPTZ` | No | — |
| `status` | `VARCHAR(30)` | No | `'candidate'` |
| `archive_object_id` | `BIGINT` | Yes | — |
| `record_sha256` | `CHAR(64)` | Yes | — |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed status:

```text
candidate
archived
delete_authorized
deleted
skipped
failed
```

Foreign keys:

```text
retention_run_id → operations.retention_runs(id) ON DELETE RESTRICT
archive_object_id → operations.archive_objects(id) ON DELETE RESTRICT
```

Add the archive-object FK after `archive_objects` exists.

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (retention_run_id, target_record_key)
target_record_key is nonblank
record_sha256 is null or valid lowercase SHA-256
failed requires a nonblank error_message
```

Archived/delete-authorized/deleted rows require an archive object when the
parent policy requires archive. A deleted item cannot return to an earlier
state. Direct transition to deleted requires an authorized/deleting parent.

Indexes:

```text
(retention_run_id, status)
(record_timestamp)
(archive_object_id) WHERE archive_object_id IS NOT NULL
```

# 11. `operations.archive_manifests`

One logical archive dataset.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `retention_run_id` | `UUID` | Yes | — |
| `target_schema` | `VARCHAR(63)` | No | — |
| `target_table` | `VARCHAR(63)` | No | — |
| `archive_format` | `VARCHAR(20)` | No | — |
| `status` | `VARCHAR(30)` | No | `'pending'` |
| `storage_provider` | `VARCHAR(50)` | No | — |
| `manifest_uri` | `TEXT` | No | — |
| `schema_revision` | `VARCHAR(100)` | No | — |
| `compression` | `VARCHAR(20)` | No | `'zstd'` |
| `encryption_method` | `VARCHAR(50)` | No | — |
| `encryption_key_reference` | `TEXT` | Yes | — |
| `object_count` | `INTEGER` | No | `0` |
| `row_count` | `BIGINT` | No | `0` |
| `byte_count` | `BIGINT` | No | `0` |
| `min_record_timestamp` | `TIMESTAMPTZ` | Yes | — |
| `max_record_timestamp` | `TIMESTAMPTZ` | Yes | — |
| `manifest_sha256` | `CHAR(64)` | Yes | — |
| `created_by` | `VARCHAR(255)` | No | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `completed_at` | `TIMESTAMPTZ` | Yes | — |
| `verified_by` | `VARCHAR(255)` | Yes | — |
| `verified_at` | `TIMESTAMPTZ` | Yes | — |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed format:

```text
parquet
csv
jsonl
```

Allowed status:

```text
pending
writing
written
verified
failed
expired
```

Allowed compression:

```text
none
gzip
zstd
snappy
```

Foreign key:

```text
retention_run_id → operations.retention_runs(id) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
partial UNIQUE (retention_run_id) WHERE retention_run_id IS NOT NULL
identifiers, provider, URI, revision, encryption method, and creator nonblank
URI must not contain a query string or embedded credential
counts >= 0
timestamp bounds are both null or min <= max
manifest SHA is null or valid
encryption_method != 'none' requires key reference
written/verified requires completed_at
verified requires checksum, actor, and timestamp
failed requires error_message
```

Indexes:

```text
(status, created_at DESC)
(target_schema, target_table, created_at DESC)
(retention_run_id) WHERE retention_run_id IS NOT NULL
(verified_at DESC) WHERE verified_at IS NOT NULL
```

---

# 12. `operations.archive_objects`

One physical archive object.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `archive_manifest_id` | `UUID` | No | — |
| `sequence_number` | `INTEGER` | No | — |
| `partition_label` | `VARCHAR(255)` | Yes | — |
| `storage_uri` | `TEXT` | No | — |
| `content_type` | `VARCHAR(100)` | No | — |
| `compression` | `VARCHAR(20)` | No | — |
| `status` | `VARCHAR(20)` | No | `'pending'` |
| `row_count` | `BIGINT` | No | `0` |
| `byte_count` | `BIGINT` | No | `0` |
| `min_record_timestamp` | `TIMESTAMPTZ` | Yes | — |
| `max_record_timestamp` | `TIMESTAMPTZ` | Yes | — |
| `sha256` | `CHAR(64)` | Yes | — |
| `provider_etag` | `TEXT` | Yes | — |
| `verified_at` | `TIMESTAMPTZ` | Yes | — |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed status:

```text
pending
uploaded
verified
failed
expired
```

Foreign key:

```text
archive_manifest_id → operations.archive_manifests(id) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (archive_manifest_id, sequence_number)
UNIQUE (storage_uri)
sequence_number >= 0
URI/content type are nonblank and URI contains no credential/query token
row_count and byte_count >= 0
timestamp bounds are both null or min <= max
sha256 is null or valid
uploaded/verified requires checksum and positive byte count
verified requires verified_at
failed requires error_message
```

Indexes:

```text
(archive_manifest_id, sequence_number)
(status, created_at DESC)
(sha256) WHERE sha256 IS NOT NULL
```

Once the parent manifest is verified, objects are immutable and cannot be
deleted. Object mutation and manifest finalization must serialize on the same
manifest row.

---

# 13. `operations.backup_snapshots`

Inventory and verification evidence for provider-created backups.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `environment_name` | `VARCHAR(100)` | No | — |
| `provider` | `VARCHAR(50)` | No | — |
| `provider_snapshot_id` | `VARCHAR(255)` | No | — |
| `backup_type` | `VARCHAR(30)` | No | — |
| `status` | `VARCHAR(20)` | No | `'requested'` |
| `verification_status` | `VARCHAR(20)` | No | `'pending'` |
| `postgres_version` | `VARCHAR(50)` | No | — |
| `alembic_revision` | `VARCHAR(100)` | No | — |
| `database_identifier` | `VARCHAR(255)` | No | — |
| `recovery_point_at` | `TIMESTAMPTZ` | Yes | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `size_bytes` | `BIGINT` | Yes | — |
| `checksum_sha256` | `CHAR(64)` | Yes | — |
| `storage_uri` | `TEXT` | Yes | — |
| `encrypted` | `BOOLEAN` | No | `true` |
| `encryption_method` | `VARCHAR(50)` | Yes | — |
| `encryption_key_reference` | `TEXT` | Yes | — |
| `retention_until` | `TIMESTAMPTZ` | Yes | — |
| `verified_by` | `VARCHAR(255)` | Yes | — |
| `verified_at` | `TIMESTAMPTZ` | Yes | — |
| `metadata_json` | `JSONB` | No | `'{}'::jsonb` |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed backup type:

```text
full
incremental
logical
physical
provider_snapshot
point_in_time_marker
```

Allowed status:

```text
requested
running
succeeded
failed
expired
deleted
```

Allowed verification:

```text
pending
verified
failed
not_supported
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (provider, provider_snapshot_id)
identity/version fields nonblank
size is null or >= 0
checksum is null or valid
storage URI contains no query token or credential
jsonb_typeof(metadata_json) = 'object'
encrypted requires encryption method
key reference must not resemble a secret or connection string
succeeded requires recovery point, started time, and finished time
failed requires error_message
verified requires succeeded status, checksum, positive size, storage URI,
actor, and timestamp
finished_at >= started_at
retention_until is null or after recovery point
```

Indexes:

```text
(environment_name, recovery_point_at DESC)
(status, created_at DESC)
(verification_status, verified_at DESC)
(retention_until) WHERE retention_until IS NOT NULL
```

After verification, backup identity/evidence is immutable. Status may move only
from succeeded to expired and later deleted; the metadata row remains.

---

# 14. `operations.restore_drills`

One recovery exercise using one verified backup.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `backup_snapshot_id` | `UUID` | No | — |
| `environment_name` | `VARCHAR(100)` | No | — |
| `status` | `VARCHAR(20)` | No | `'pending'` |
| `target_alembic_revision` | `VARCHAR(100)` | No | — |
| `initiated_by` | `VARCHAR(255)` | No | — |
| `rto_target_seconds` | `INTEGER` | Yes | — |
| `rpo_target_seconds` | `INTEGER` | Yes | — |
| `measured_restore_seconds` | `INTEGER` | Yes | — |
| `measured_data_loss_seconds` | `INTEGER` | Yes | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `notes` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed status:

```text
pending
running
succeeded
failed
cancelled
```

Foreign key:

```text
backup_snapshot_id → operations.backup_snapshots(id) ON DELETE RESTRICT
```

Checks:

```text
identity/actor fields nonblank
target/measured seconds are null or >= 0
shared lifecycle timestamps apply
succeeded requires measured_restore_seconds
```

Starting a drill requires a succeeded, verified backup. Only
`finalize_restore_drill_v1` may mark success. Terminal drill identity,
measurements, and child checks are immutable.

Indexes:

```text
(backup_snapshot_id, created_at DESC)
(status, created_at DESC)
(environment_name, finished_at DESC)
```

---

# 15. `operations.restore_drill_checks`

Evidence from one restore drill.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `restore_drill_id` | `UUID` | No | — |
| `check_code` | `VARCHAR(100)` | No | — |
| `category` | `VARCHAR(30)` | No | — |
| `severity` | `VARCHAR(20)` | No | `'critical'` |
| `required` | `BOOLEAN` | No | `true` |
| `status` | `VARCHAR(20)` | No | `'pending'` |
| `expected_json` | `JSONB` | No | `'{}'::jsonb` |
| `actual_json` | `JSONB` | No | `'{}'::jsonb` |
| `message` | `TEXT` | Yes | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Allowed category:

```text
migration
schema
data
constraints
api
security
query
backup
archive
```

Allowed severity:

```text
info
warning
error
critical
```

Allowed status:

```text
pending
running
passed
failed
skipped
```

Foreign key:

```text
restore_drill_id → operations.restore_drills(id) ON DELETE RESTRICT
```

Constraints:

```text
PRIMARY KEY (id)
UNIQUE (restore_drill_id, check_code)
check code nonblank
JSON values are objects
passed/failed/skipped requires finished_at
failed requires message
required critical checks cannot be skipped
```

Mandatory successful-drill check codes:

```text
alembic_revision
schema_inventory
row_count_baseline
foreign_key_constraints
api_contract
security_grants_rls
sample_query_smoke
backup_checksum
```

Indexes:

```text
(restore_drill_id, status)
(category, severity, status)
```

---

# 16. `operations.maintenance_runs`

Evidence for an external maintenance operation; it executes no maintenance SQL.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `run_type` | `VARCHAR(30)` | No | — |
| `target_schema` | `VARCHAR(63)` | Yes | — |
| `target_table` | `VARCHAR(63)` | Yes | — |
| `status` | `VARCHAR(20)` | No | `'pending'` |
| `dry_run` | `BOOLEAN` | No | `false` |
| `requested_by` | `VARCHAR(255)` | No | — |
| `external_job_reference` | `TEXT` | Yes | — |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `rows_examined` | `BIGINT` | No | `0` |
| `rows_affected` | `BIGINT` | No | `0` |
| `objects_affected` | `INTEGER` | No | `0` |
| `metrics_json` | `JSONB` | No | `'{}'::jsonb` |
| `error_message` | `TEXT` | Yes | — |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Run types:

```text
vacuum
analyze
reindex
security_audit
health_check
retention
archive
backup
restore
partition_review
schema_validation
other
```

Statuses:

```text
pending
running
succeeded
partially_succeeded
failed
cancelled
```

Checks:

```text
PRIMARY KEY (id)
requested_by nonblank
target schema/table both null or both non-null
counters >= 0
metrics is object
external reference contains no credentials
failed requires error_message
shared lifecycle applies
```

Indexes:

```text
(run_type, created_at DESC)
(status, created_at DESC)
(target_schema, target_table, created_at DESC)
```

---

# 17. `operations.health_check_runs`

One operational health-suite execution.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `UUID` | No | `gen_random_uuid()` |
| `suite_version` | `VARCHAR(100)` | No | — |
| `environment_name` | `VARCHAR(100)` | No | — |
| `scope` | `VARCHAR(30)` | No | `'full'` |
| `status` | `VARCHAR(30)` | No | `'pending'` |
| `started_at` | `TIMESTAMPTZ` | Yes | — |
| `finished_at` | `TIMESTAMPTZ` | Yes | — |
| `passed_count` | `INTEGER` | No | `0` |
| `warning_count` | `INTEGER` | No | `0` |
| `failed_count` | `INTEGER` | No | `0` |
| `metrics_json` | `JSONB` | No | `'{}'::jsonb` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` |

Scopes:

```text
full
security
performance
freshness
backup
restore
quality
serving
migration
```

Statuses:

```text
pending
running
passed
passed_with_warnings
failed
cancelled
```

Checks:

```text
PRIMARY KEY (id)
suite/environment nonblank
counts >= 0
metrics is object
shared lifecycle applies
passed requires no warnings/failures
passed_with_warnings requires warnings and no failures
failed requires failed_count > 0
```

Indexes:

```text
(environment_name, created_at DESC)
(status, created_at DESC)
(scope, created_at DESC)
```

---

# 18. `operations.health_check_results`

One check result.

| Column | PostgreSQL type | Null | Default |
|---|---|---:|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | No | identity |
| `health_check_run_id` | `UUID` | No | — |
| `check_code` | `VARCHAR(100)` | No | — |
| `category` | `VARCHAR(30)` | No | — |
| `severity` | `VARCHAR(20)` | No | — |
| `status` | `VARCHAR(20)` | No | — |
| `object_schema` | `VARCHAR(63)` | Yes | — |
| `object_name` | `VARCHAR(255)` | Yes | — |
| `metric_value` | `NUMERIC(30,6)` | Yes | — |
| `metric_unit` | `VARCHAR(50)` | Yes | — |
| `threshold_json` | `JSONB` | No | `'{}'::jsonb` |
| `evidence_json` | `JSONB` | No | `'{}'::jsonb` |
| `message` | `TEXT` | Yes | — |
| `observed_at` | `TIMESTAMPTZ` | No | `now()` |
| `created_at` | `TIMESTAMPTZ` | No | `now()` |

Categories:

```text
security
performance
freshness
backup
restore
quality
serving
migration
storage
```

Severity:

```text
info
warning
error
critical
```

Status:

```text
passed
warning
failed
not_applicable
```

Foreign key:

```text
health_check_run_id → operations.health_check_runs(id) ON DELETE RESTRICT
```

Use a unique expression index for:

```text
health_check_run_id
check_code
COALESCE(object_schema, '')
COALESCE(object_name, '')
```

Additional checks:

```text
check code nonblank
JSON values are objects
warning status requires warning/error/critical severity
failed status requires error/critical severity and message
```

Indexes:

```text
(health_check_run_id, status)
(category, severity, status)
(observed_at DESC)
```

After parent finalization, results are immutable.

---

# 19. Trigger contracts

## `operations.enforce_run_lifecycle()`

Attach to retention runs, backup snapshots, restore drills, maintenance runs,
health-check runs, and archive manifests where relevant.

It must enforce status transitions, timestamp matrices, and finalizer-only
states.

Direct DML must not set:

```text
retention_runs.delete_authorized
archive_manifests.verified
backup_snapshots.verification_status = verified
restore_drills.succeeded
health_check_runs terminal calculated outcomes
```

Finalization functions set a transaction-local guard using `set_config`, and
the trigger validates the expected guard.

## `operations.protect_finalized_operational_record()`

Reject with SQLSTATE `23514`:

- deleting verified archive evidence;
- deleting verified backup evidence;
- mutating terminal restore evidence;
- mutating finalized health evidence;
- changing referenced operational identity;
- moving irreversible states backward.

## `operations.protect_policy_identity()`

Enforce the partition/retention policy rules above.

## `operations.protect_archive_object_after_verification()`

Lock the parent manifest before archive-object mutation. Concurrent mutation and
manifest finalization must serialize.

---

# 20. Callable function security

All six functions:

```text
SECURITY DEFINER
SET search_path = pg_catalog, operations
```

Use schema-qualified references and no dynamic SQL.

For exact signatures:

```sql
REVOKE ALL ON FUNCTION ... FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION ... TO service_role;
```

---

# 21. Function behavior

## `operations.assert_security_baseline_v1()`

```sql
operations.assert_security_baseline_v1()
RETURNS void
```

`STABLE`. Raise SQLSTATE `23514` when
`v_security_privilege_violations` contains rows; otherwise return normally.

## `operations.authorize_retention_delete_v1`

```sql
operations.authorize_retention_delete_v1(
    p_retention_run_id UUID,
    p_authorized_by TEXT
)
RETURNS operations.retention_runs
```

Lock run and policy. Reject blank actor, disabled policy, legal hold, dry-run,
wrong status, failures, zero candidates, item-count mismatch, missing/unverified
archive, row-count mismatch, or cross-manifest item evidence.

For archive-required policies, exactly one verified manifest and complete
archived item evidence are mandatory. Set parent/items to `delete_authorized`
atomically. Do not delete target data.

## `operations.finalize_archive_manifest_v1`

```sql
operations.finalize_archive_manifest_v1(
    p_archive_manifest_id UUID,
    p_verified_by TEXT
)
RETURNS operations.archive_manifests
```

Require written manifest, nonblank actor, at least one verified child object,
complete checksums, and exact object/row/byte/timestamp aggregates. When linked
to retention, manifest target must equal policy target. Mark verified atomically.

## `operations.finalize_backup_snapshot_v1`

```sql
operations.finalize_backup_snapshot_v1(
    p_backup_snapshot_id UUID,
    p_verified_by TEXT
)
RETURNS operations.backup_snapshots
```

Require succeeded backup, pending verification, recovery point, finished time,
positive size, checksum, storage URI, encryption method/key reference, and
nonblank actor. Verify revision against `public.alembic_version` unless metadata
documents a controlled older-revision backup. Mark verified atomically.

## `operations.finalize_restore_drill_v1`

```sql
operations.finalize_restore_drill_v1(
    p_restore_drill_id UUID
)
RETURNS operations.restore_drills
```

Require running drill, verified backup, all eight mandatory checks, all
required/critical checks passed, no required failure, measured restore time,
and matching revision evidence. Mark succeeded and finished atomically.

## `operations.finalize_health_check_run_v1`

```sql
operations.finalize_health_check_run_v1(
    p_health_check_run_id UUID
)
RETURNS operations.health_check_runs
```

Require running parent and at least one result. Calculate counts and terminal
status from child rows; do not trust caller-provided counters.

---

# 22. Security hardening

Execute:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC, anon, authenticated;
```

Revoke public/client schema, table, sequence, and function access from:

```text
system
ingestion
taxonomy
core
history
quality
analytics
serving
operations
```

Do not break the Migration 006 exact `api` function grants.

Keep:

```text
USAGE on api → anon, authenticated, service_role
EXECUTE on exact eight API `_v1` functions → those roles
```

Require API to remain function-only, `SECURITY DEFINER`, `STABLE`, fixed
`pg_catalog, api, serving` search path, schema-qualified, and without dynamic
SQL or PUBLIC execute.

Enable RLS on all 12 operations tables. Create no client policies. Grant
operations DML and sequence use only to `service_role`.

Apply default-privilege revocations for the migration owner in all private
schemas. For `api`, revoke default PUBLIC execution so future functions need
explicit grants. Document that default privileges are owner-specific.

---

# 23. `operations.v_security_privilege_violations`

Columns:

```text
violation_code TEXT
severity TEXT
object_type TEXT
object_schema TEXT
object_name TEXT
grantee TEXT
privilege_type TEXT
details JSONB
```

Detect:

1. public/client schema access on private schemas;
2. public/client table or sequence privilege in private schemas;
3. any relation in `api`;
4. unsafe API security-definer, volatility, or search-path properties;
5. PUBLIC execute on API;
6. missing anon/authenticated execute on expected API signatures;
7. operations table with RLS disabled;
8. client-visible policy on operations;
9. public/client execute on operations functions;
10. public/client CREATE on public schema.

Use catalogs and information schema; no dynamic SQL.

---

# 24. Performance indexes

Create seven additive BRIN indexes:

```text
history.job_observations(observed_at)
history.job_status_events(event_at)
history.job_change_events(detected_at)
history.job_repost_events(detected_at)
quality.data_quality_issues(detected_at)
analytics.fact_job_observations(loaded_at)
analytics.fact_salary_observations(loaded_at)
```

Use distinct names ending `_brin`, `USING BRIN`, and
`pages_per_range = 128` unless measured benchmarks justify another value.

Create four partial indexes:

```text
quality.data_quality_issues(detected_at DESC, issue_code)
WHERE status IN ('open','acknowledged')
  AND severity IN ('error','critical')

serving.job_search_documents(posted_at DESC, job_posting_id)
WHERE status = 'active'

analytics.refresh_runs(started_at, id)
WHERE status = 'running'

serving.refresh_runs(started_at, id)
WHERE status = 'running'
```

Do not remove existing indexes and do not partition tables.

---

# 25. Operational views

## `operations.v_unindexed_foreign_keys`

Find foreign keys lacking a valid/ready B-tree-compatible referencing index with
FK columns as the leading columns in the same order.

Return:

```text
table_schema
table_name
constraint_name
foreign_key_columns
referenced_schema
referenced_table
estimated_rows
```

This is advisory; PostgreSQL does not require FK indexes.

## `operations.v_table_storage_health`

Use PostgreSQL statistics/catalogs and return:

```text
table_schema
table_name
estimated_live_rows
estimated_dead_rows
dead_tuple_ratio
table_bytes
index_bytes
total_bytes
sequential_scans
index_scans
last_vacuum
last_autovacuum
last_analyze
last_autoanalyze
health_status
```

Statuses:

```text
healthy
review_dead_tuples
review_missing_analyze
review_scan_pattern
```

Do not treat all sequential scans as bad.

## `operations.v_data_freshness`

Components:

```text
history_observation
quality_validation
analytics_refresh
serving_refresh
```

Return last success, age, 86400-second default target, status
`fresh/stale/never_completed`, and details JSON.

## `operations.v_backup_restore_readiness`

One row per environment. Use latest verified recovery point and latest
successful restore drill.

V1 targets:

```text
backup age <= 24 hours
restore drill age <= 90 days
```

Return IDs, timestamps, ages, readiness booleans, and status.

## `operations.v_retention_readiness`

One row per policy with latest run/counters and status:

```text
disabled
legal_hold
never_run
ready
running
needs_review
failed
```

Do not execute policy predicates.

## `operations.v_release_readiness`

Exactly one row containing:

```text
database_revision
expected_revision = 20260728_0007
security_violation_count
open_critical_quality_issue_count
stale_freshness_component_count
stale_running_refresh_count
verified_backup_environment_count
ready_backup_environment_count
latest_health_check_status
release_ready
blockers_json
calculated_at
```

Block on revision mismatch, security violations, open critical quality issues,
stale pipeline components, refresh runs running over two hours, represented
backup environments that are not ready, or failed latest full health check.

No backup metadata means not production-ready, but CI may validate
schema/security without a real provider backup.

---

# 26. Retention workflow contract

External worker flow:

```text
1. read enabled policy
2. create retention run
3. identify candidates with code-level allowlisted SQL
4. insert run items
5. create archive manifest
6. upload archive objects outside PostgreSQL
7. record checksums and counts
8. finalize manifest
9. authorize deletion
10. delete only authorized keys in bounded external transactions
11. mark item evidence
12. finalize run
```

The worker must never concatenate policy metadata into arbitrary SQL. It must
recheck identity/timestamps and stop when a legal hold activates.

---

# 27. Backup/restore workflow contract

Backup:

```text
provider creates backup
worker records metadata
independent process verifies evidence
worker calls finalize_backup_snapshot_v1
```

Restore drill:

```text
create isolated environment
restore verified backup
run mandatory checks
record evidence
finalize drill
destroy isolated environment
```

Never test restore against production. Migration 007 does not call provider
APIs or shell commands.

---

# 28. SQLAlchemy

Add:

```text
src/it_labor_market_intelligence/database/v1_models/operations.py
```

Update package exports.

Models:

```text
PartitionPolicy
RetentionPolicy
RetentionRun
RetentionRunItem
ArchiveManifest
ArchiveObject
BackupSnapshot
RestoreDrill
RestoreDrillCheck
MaintenanceRun
HealthCheckRun
HealthCheckResult
```

Use `V1Base`, explicit schema, schema-qualified FKs, UUID, JSONB, and migration
parity.

Do not model views as writable ORM tables. Alembic remains authoritative for
catalog views, BRIN/partial/expression indexes, triggers, functions, grants,
RLS, default privileges, and seed rows.

---

# 29. Upgrade order

1. Create and secure `operations`.
2. Revoke client CREATE on `public`.
3. Create policy/retention tables.
4. Create archive tables.
5. Add deferred archive-object FK to retention items.
6. Create backup/restore tables.
7. Create maintenance/health tables.
8. Create operations-table indexes.
9. Create/attach lifecycle and protection triggers.
10. Seed advisory partition policies.
11. Create seven views.
12. Create six callable functions.
13. Enable RLS on 12 tables.
14. Harden internal schema grants and default privileges.
15. Grant service-role operations access.
16. Create seven BRIN and four partial indexes.
17. Call `operations.assert_security_baseline_v1()`.

Migration failure must be atomic.

---

# 30. Downgrade order

1. Revoke/drop six callable functions by exact signature.
2. Drop seven views.
3. Drop triggers, then internal trigger functions.
4. Drop eleven additive indexes.
5. Drop deferred archive-object FK.
6. Drop health tables.
7. Drop maintenance table.
8. Drop restore checks/drills.
9. Drop backup table.
10. Drop retention items.
11. Drop archive objects/manifests.
12. Drop retention runs/policies.
13. Drop partition policies.
14. Drop operations schema.

Do not restore insecure grants. Do not alter/drop Migration 001–006 objects or
data. Do not use `CASCADE`.

---

# 31. PostgreSQL integration tests

Create:

```text
tests/integration/database/test_database_v1_operations.py
```

Required coverage:

## Inventory and security

- exact 12 tables, 7 views, 6 functions;
- head revision 007;
- operations absent from api;
- security baseline passes;
- temporary unsafe grants/functions/RLS states appear as violations;
- assertion raises `23514`;
- Migration 006 API contracts and exact grants remain unchanged;
- anon/authenticated cannot use operations;
- service role can use authorized operations;
- PUBLIC cannot execute operations functions;
- default privileges are hardened.

## Partition policies

- six advisory rows;
- target table/key validation;
- interval/threshold checks;
- approval requirements;
- identity immutability;
- no existing relation is partitioned.

## Retention/archive

- policy window, approval, legal-hold, and identity rules;
- invalid URI/checksum rejection;
- manifest count and checksum finalization;
- immutable verified objects;
- dry-run/disabled/hold/missing evidence/count mismatch/failure rejection;
- successful authorization updates parent/items but deletes no target row;
- concurrent legal hold and authorization serialize;
- concurrent object mutation and manifest finalization serialize.

## Backup/restore

- backup lifecycle and evidence;
- secret-like references rejected;
- verification finalizer;
- verified identity immutable;
- unverified backup cannot start drill;
- all eight mandatory checks;
- failures/skips block success;
- target revision and measured timing;
- concurrent check mutation and drill finalization serialize.

## Health/maintenance/views

- lifecycle checks;
- finalizer calculates counts;
- finalized result immutability;
- security, FK, storage, freshness, readiness, retention, and release views;
- deterministic fixture behavior;
- no brittle byte-size/planner assertions.

## Performance indexes

- seven BRIN and four partial indexes exist;
- correct relation, method, validity, columns, and predicate;
- `EXPLAIN (FORMAT JSON)` smoke tests show eligibility without requiring one
  exact tiny-table plan.

## Downgrade/re-upgrade

Downgrade to `20260727_0006`:

- operations and additive indexes gone;
- Migration 001–006 schemas/data/API remain;
- insecure grants are not reopened.

Then re-upgrade and rerun the baseline.

All concurrency tests use separate connections and bounded lock/statement
timeouts.

---

# 32. CI

Keep local roles:

```text
anon
authenticated
service_role
```

Run:

```text
alembic upgrade head
alembic current
SELECT operations.assert_security_baseline_v1()
full pytest
Ruff
Black
MyPy
```

Include downgrade/re-upgrade and concurrency tests. Do not weaken Migration
001–006 tests.

---

# 33. Documentation

Create:

```text
docs/DATABASE_V1_OPERATIONS.md
docs/SECURITY_MODEL.md
docs/BACKUP_RESTORE_RUNBOOK.md
docs/RETENTION_ARCHIVE_RUNBOOK.md
docs/OPERATIONS_RUNBOOK.md
```

Update:

```text
README.md
docs/DATABASE_DESIGN.md
docs/DATA_SCHEMA.md
docs/DATA_IMPORT_RUNBOOK.md
docs/API_REFERENCE.md
docs/DATABASE_V1_SERVING_API.md
```

Document Database V1 completion, role/grant/RLS model, Supabase exposed-schema
checklist, baseline usage, partition deferral, retention authorization, legal
holds, archive evidence, backup metadata versus real backup, restore checks,
RTO/RPO, health/readiness, secret prohibitions, downgrade precautions, and
optional Migration 008.

---

# 34. Out of scope

Do not implement:

```text
cron/scheduler
provider backup API
pg_dump/restore execution
object-storage transfer
physical retention deletion
automatic archive export
in-place partition conversion
automatic VACUUM/REINDEX
monitoring vendor or alerts
secret storage
frontend operations dashboard
crawler/importer/analytics/serving worker changes
users/resumes/applications/recommendations
embeddings/vector search/LLM/forecasting
```

---

# 35. Acceptance checklist

- [ ] Direct child of Migration 006.
- [ ] Exactly 12 tables, 7 views, and 6 callable functions.
- [ ] Explicit DDL; no metadata create/drop; no CASCADE.
- [ ] Operations private, RLS enabled, service-role only.
- [ ] API security and contracts unchanged.
- [ ] Security baseline passes.
- [ ] Seven BRIN and four partial indexes.
- [ ] No physical partition conversion.
- [ ] Six advisory partition policies.
- [ ] No enabled destructive policy by default.
- [ ] Legal hold and archive evidence gate deletion authorization.
- [ ] Authorization performs no physical deletion.
- [ ] Verified archive/backup/restore evidence immutable.
- [ ] Eight mandatory restore checks.
- [ ] Health/readiness views work.
- [ ] Downgrade leaves Migration 001–006 intact and does not reopen privileges.
- [ ] PostgreSQL tests, concurrency tests, pytest, Ruff, Black, and MyPy pass.
- [ ] No out-of-scope worker/provider/application feature added.

---

# 36. Codex workflow

1. Read `AGENT_RULES.md`.
2. Read `DATABASE_V1_MIGRATION_007_SPEC.md`.
3. Read Migrations 001–006, V1 models, and integration tests.
4. Confirm branch `main`; pull latest `origin/main`.
5. Create focused branch.
6. Implement explicit DDL and operations models.
7. Add security, lifecycle, finalization, catalog-view, index, downgrade, and
   concurrency tests.
8. Add operational runbooks.
9. Run all checks.
10. Push and create a draft PR into `main`.
11. Do not merge.
12. Report revision, object counts, index count, security baseline, safeguards,
    tests, CI, unresolved operational risks, and out-of-scope confirmation.

---

# 37. Codex prompt

```text
Read AGENT_RULES.md and DATABASE_V1_MIGRATION_007_SPEC.md.

Confirm the current branch is main and pull the latest origin/main.

Create:
feat/database-v1-migration-007-operations-hardening

Implement Database V1 Migration 007 exactly as specified.

Create the private operations schema with 12 operational evidence tables,
7 catalog/readiness views, and 6 service-role-only finalization/assertion
functions.

Implement security hardening, RLS and exact grants, default-privilege
hardening, the security-baseline assertion, additive BRIN/partial indexes,
advisory partition policies, retention/archive authorization contracts,
backup metadata verification, restore-drill evidence, health checks, and
release-readiness views.

Use explicit Alembic DDL and schema-qualified SQLAlchemy models. Add
PostgreSQL integration tests for lifecycle integrity, grants/RLS, API security
regression, archive and retention authorization, backup/restore finalization,
catalog views, performance-index inventory, downgrade/re-upgrade, and real
two-connection concurrency behavior with bounded timeouts.

Do not physically partition existing tables. Do not implement a scheduler,
provider backup calls, pg_dump/restore execution, object-storage transfer,
physical retention deletion, automatic VACUUM/REINDEX, monitoring alerts,
frontend changes, crawler changes, analytics/serving workers, users, resumes,
recommendations, embeddings, semantic search, or LLM features.

Run:
- PostgreSQL migrations and downgrade/re-upgrade tests
- operations.assert_security_baseline_v1()
- full pytest
- Ruff
- Black
- MyPy

Push the branch and create a draft pull request into main. Do not merge.

Return the PR link, final commit, table/view/function counts, added index count,
security-baseline result, and final CI status.
```

---

# 38. Human review checklist

## Security

- [ ] Internal schemas inaccessible to public/client roles.
- [ ] API grants and exact contracts preserved.
- [ ] API remains function-only.
- [ ] All operations tables have RLS and no client policies.
- [ ] Finalizers service-role only.
- [ ] Default privileges documented as owner-specific.
- [ ] No secret-like fixture or metadata.

## Retention/archive

- [ ] Authorization never deletes.
- [ ] Legal hold is locked/rechecked.
- [ ] Required archive is verified with matching counts/checksums.
- [ ] Explicit worker allowlist required.
- [ ] No arbitrary SQL from metadata.
- [ ] Verified evidence immutable.

## Backup/restore

- [ ] Metadata is not mistaken for a real backup.
- [ ] Recovery point/checksum/encryption/revision required.
- [ ] Eight mandatory checks.
- [ ] Failed check blocks success.
- [ ] RTO/RPO nonnegative.
- [ ] Terminal evidence immutable.

## Performance/migration

- [ ] Index names do not collide.
- [ ] BRIN targets append-correlated timestamps.
- [ ] Partial predicates use real statuses.
- [ ] Existing indexes preserved.
- [ ] No partition conversion.
- [ ] Deferred FK and downgrade order safe.
- [ ] No CASCADE.
- [ ] Migration 001–006 survive downgrade.
- [ ] Downgrade does not restore insecure grants.

## Scope

- [ ] No scheduler/provider integration/deletion worker.
- [ ] No actual partition conversion.
- [ ] No application-feature expansion.
