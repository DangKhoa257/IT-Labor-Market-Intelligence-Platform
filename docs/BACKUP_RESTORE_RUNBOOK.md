# Backup and restore evidence runbook

Migration 007 records backup and restore evidence only. It neither invokes a
provider nor executes `pg_dump`, `pg_restore`, or object-storage transfers.

Create a `backup_snapshots` row when an external backup completes. Record the
environment, recovery point, size, SHA-256 checksum, non-secret storage URI and
encryption reference, and Alembic revision. Finalize a valid succeeded backup
through `operations.finalize_backup_snapshot_v1(id, verified_by)`. Verified
backup identity and evidence are immutable.

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
