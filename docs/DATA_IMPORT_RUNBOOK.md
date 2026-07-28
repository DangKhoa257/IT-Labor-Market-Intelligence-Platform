# Data Import Runbook

Start and verify PostgreSQL:

```powershell
docker compose up -d postgres
docker compose ps
```

Apply and verify Database V1 migrations 001 through 006:

```powershell
alembic upgrade head
alembic current
```

Migration 003 creates a canonical current-state destination, Migration 004 adds immutable history
and quality-review storage, Migration 005 adds analytics storage and deterministic seed rows, and
Migration 006 adds rebuildable serving caches and a function-only RPC schema.
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
