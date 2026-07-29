# Backup and restore evidence runbook

Migration 007 records backup and restore evidence only. It neither invokes a
provider nor executes `pg_dump`, `pg_restore`, or object-storage transfers.

Create a `backup_snapshots` row when an external backup completes. Record the
environment, recovery point, size, SHA-256 checksum, non-secret storage URI and
encryption reference, and Alembic revision. Finalize a valid succeeded backup
through `operations.finalize_backup_snapshot_v1(id, verified_by)`. Verified
backup identity and evidence are immutable.

Backups must be encrypted. Store only a nonblank key reference, never a
connection string, query/fragment URI, password/token/secret assignment,
`sk-` key, JWT-like `eyJ` value, or PEM/private-key material. An older Alembic
revision is accepted only when metadata has the exact JSON boolean
`{"allow_older_revision": true}`.

The lifecycle is exact: `requested → running → succeeded → expired → deleted`,
with `failed` reachable from requested or running. Requested has no timestamps;
running has only `started_at`; succeeded/failed retain both timestamps. A
verified backup may expire and be deleted only through the successful path, and
all evidence other than `status` and `updated_at` remains immutable.

Create a restore drill from a verified backup, execute the external restore,
and record all eight mandatory checks: `alembic_revision`, `schema_inventory`,
`row_count_baseline`, `foreign_key_constraints`, `api_contract`,
`security_grants_rls`, `sample_query_smoke`, and `backup_checksum`. Record the
measured restore duration and revision evidence, then call
`operations.finalize_restore_drill_v1(id)`. Failed, skipped, missing, or
revision-mismatched required checks prevent success.

Treat RPO/RTO as evidence-backed targets: recovery-point timestamps measure RPO
and measured restore seconds measure RTO. Review
`operations.v_backup_restore_readiness` before release; it reports missing or
stale verified backups and restore drills. Do not claim a backup is restorable
until the associated drill has succeeded.
