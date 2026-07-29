# Database security model

Database V1 uses private schemas for system, ingestion, taxonomy, core, history,
quality, analytics, serving, and operations. Client roles cannot use those
schemas or read their relations. The `api` schema remains function-only and its
eight versioned, fixed-search-path SECURITY DEFINER functions are the only
client-facing database contract.

Migration 007 additionally revokes `CREATE` on `public` from PUBLIC, `anon`,
and `authenticated`; revokes unsafe client and PUBLIC access from internal
schemas; enables RLS with no policies on every operations table; and hardens
default privileges. `service_role` is the only role granted operations access,
including only the six exact operational function signatures.

Finalizer-only state transitions are not controlled by a user-settable custom
GUC. The six finalizers run under their trusted function-owner context;
ordinary lifecycle triggers compare that context to the `operations` schema
owner. `service_role` cannot reproduce it with `SET`, `set_config`, or direct
DML. The migration owner is administrative by design and must remain tightly
controlled.

Do not store credentials, access keys, or secret-like values in operations
metadata, storage URIs, encryption references, manifests, checks, or logs.
Use a secret manager and store a non-secret reference only. Verify the baseline
with `SELECT operations.assert_security_baseline_v1();` after a deployment,
role change, or Supabase exposed-schema change.

For Supabase deployments, expose only `api`; keep `operations` and all internal
schemas out of exposed schemas. Grant no direct relation access to browser roles.
