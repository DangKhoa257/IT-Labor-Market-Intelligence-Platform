# Database V1 operations

Migration `20260728_0007` completes Database V1 with the private `operations`
schema. It records operational evidence; it does not schedule work, call a backup
provider, copy objects, delete retained data, or convert existing tables to
partitions.

The schema has twelve evidence tables: advisory partition policies; retention
policies, runs, and items; archive manifests and objects; backup snapshots;
restore drills and checks; maintenance runs; and health-check runs and results.
It also exposes seven internal catalog/readiness views and six service-role-only
finalizer/assertion functions. There is no public operations API.

All operations tables use RLS and are inaccessible to `anon` and
`authenticated`. `service_role` receives the narrowly required schema, table,
sequence, and exact-function permissions. `PUBLIC` has no operations access.
Run the baseline after every migration or role/grant change:

```sql
SELECT operations.assert_security_baseline_v1();
```

The assertion raises SQLSTATE `23514` when it sees unsafe schema, relation, or
function privileges, an exposed operations object, RLS disabled, an RLS policy,
or unsafe default privileges.

Partition policies are advisory only. Migration 007 seeds six plans for large
append-only tables and adds seven BRIN plus four partial indexes. It does not
physically partition a relation; an optional Migration 008 can implement a
separately approved plan.

Evidence is finalized through the supplied functions. Their row locks and
trigger guards make archive-object mutation versus manifest finalization,
restore-check mutation versus drill finalization, and retention authorization
versus legal holds safe under concurrent transactions. Use bounded lock and
statement timeouts in operational clients.

Downgrade to `20260727_0006` removes only Migration 007 objects and its eleven
additive indexes. It deliberately does not restore insecure historical grants.
