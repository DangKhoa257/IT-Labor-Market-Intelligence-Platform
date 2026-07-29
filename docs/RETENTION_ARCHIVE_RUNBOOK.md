# Retention and archive evidence runbook

Retention policy records are authorization contracts, not deletion jobs. An
enabled policy requires an approver and timestamp; legal holds block deletion
authorization. Policy identity becomes immutable once a run references it.

For a candidate set, create a non-dry-run retention run, attach every item, and
record the external archive as a manifest and verified archive objects. Use
SHA-256 checksums, non-secret URIs, exact object/row/byte aggregates, and target
identity matching the policy. Finalize the manifest with
`operations.finalize_archive_manifest_v1`.

Only then call `operations.authorize_retention_delete_v1(run_id, actor)`. It
locks the run and policy, rejects holds, failures, count mismatches, missing or
unverified archive evidence, and invalid states, then marks the run/items
`delete_authorized`. It never deletes an application row. A separately reviewed
and audited physical-deletion implementation remains out of scope.

For archive-required policies, eligible records must be `archived` against the
single verified manifest; skipped records stay skipped. For no-archive policies,
eligible candidates are authorized directly and skipped records still remain
unchanged. Do not pre-set `delete_authorized`: PostgreSQL permits that state only
inside the trusted finalizer.

After authorization, the separately reviewed deletion worker may record only
`retention_run_items.status = 'deleted'` (and `updated_at`) while the parent run
is `delete_authorized` or `deleting`. The item's target key, timestamp, archive
lineage, checksum, error evidence, and creation time remain immutable. Once the
parent is terminal, every child mutation is rejected. After all authorized
items are recorded as deleted, move the parent through `deleting` to its
counter-consistent terminal outcome.

If deletion fails, the worker may instead record `delete_authorized → failed`
with a nonblank error message. This is equally evidence-preserving and final.
Before a run can complete, PostgreSQL locks every item and verifies the terminal
status and all parent counters against the actual deleted, skipped, and failed
item evidence; authorized or unfinished items prevent completion.

Use `operations.v_retention_readiness` to identify disabled, held, never-run,
running, failed, or ready policies. Verified archive evidence is immutable.
