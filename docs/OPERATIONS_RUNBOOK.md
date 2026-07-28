# Operations runbook

After deployment run Alembic, confirm the revision, and execute:

```sql
SELECT operations.assert_security_baseline_v1();
SELECT * FROM operations.v_release_readiness;
```

Review `v_security_privilege_violations`, `v_unindexed_foreign_keys`,
`v_table_storage_health`, and `v_data_freshness` as advisory catalog views.
Review backup/restore and retention readiness before approving a release.
Create a health-check run, append results, and finalize it through
`operations.finalize_health_check_run_v1`; the finalizer computes its counts
from immutable child evidence.

Maintenance records are evidence of manually run work. Migration 007 does not
schedule maintenance, send alerts, run VACUUM/REINDEX, or perform any backup,
restore, archival, transfer, or retention deletion action.

For rollback, use `alembic downgrade 20260727_0006` only after operational
evidence has been exported or is intentionally disposable. The downgrade removes
operations triggers before functions and schema, removes its additive indexes,
and leaves Migration 001–006 data and API contracts intact. It intentionally
does not reopen insecure privileges.
