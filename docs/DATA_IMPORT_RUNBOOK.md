# Data Import Runbook

## Boundary with Data Pipeline V1 ingestion

The TopDev ingestion worker produces traceable source evidence through
`ingestion.extracted_records`. It does not invoke the canonical importer and has no write path to
`core`, `history`, `quality`, `analytics`, `serving`, or `api`. Treat ingestion completion and
canonical import as separate operator-reviewed stages.

Use `python -m it_labor_market_intelligence.ingestion.cli inspect-run --run-id <uuid>` to review a
safe run summary before any future import decision. Source/bootstrap, fixture/live operation,
parser versions, retry recovery, raw storage decisions, direct-payload hashing, and sanitized error
handling are documented in [DATA_PIPELINE_V1_INGESTION.md](DATA_PIPELINE_V1_INGESTION.md) and
[TOPDEV_INGESTION_RUNBOOK.md](TOPDEV_INGESTION_RUNBOOK.md).

No scheduler connects these stages. No ingestion result automatically creates or updates canonical,
history, quality, analytics, serving, or API records.

Migration 007 records operational evidence separately from import execution. It does not alter
the importer, add a scheduler, or perform retention deletion; see the operations runbooks for
externally executed backup, restore, archive, retention, and health evidence.

Start and verify PostgreSQL:

```powershell
docker compose up -d postgres
docker compose ps
```

Apply and verify Database V1 migrations 001 through 007 and the security baseline:

```powershell
alembic upgrade head
alembic current
psql $env:DATABASE_URL -c "SELECT operations.assert_security_baseline_v1();"
```

Migration 003 creates a canonical current-state destination, Migration 004 adds immutable history
and quality-review storage, Migration 005 adds analytics storage and deterministic seed rows, and
Migration 006 adds rebuildable serving caches and a function-only RPC schema. Migration 007 adds
private operations evidence and does not add an importer or worker.
They do not include the normalization/application service, full observation writer, automatic
diffing, lifecycle scheduling, production analytics refresh scheduler, or deduplication algorithm.
The legacy `import_dataset` command belongs to the prototype Phase 3 database and must not be run
against the V1 schemas. Preserve pilot artifacts until a focused application service is approved.

For an existing prototype database, preserve required pilot artifacts and create a clean database;
the V1 chain does not automatically drop or transform prototype tables. The former prototype flow
was:

```powershell
python -m it_labor_market_intelligence.cli.import_dataset `
  --input datasets/processed/topdev_analysis_ready.jsonl `
  --source topdev `
  --duplicates-report reports/topdev_duplicates.json
```

In that prototype flow, re-running skips existing identities and duplicate clusters. Do not treat
it as a Database V1 ingestion command.

To remove only analytics while preserving Migrations 001–004:

```powershell
alembic downgrade 20260727_0004
alembic upgrade head
```

Stop PostgreSQL with `docker compose down`. The named volume remains until explicitly removed.
