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

Use `operations.v_retention_readiness` to identify disabled, held, never-run,
running, failed, or ready policies. Verified archive evidence is immutable.
