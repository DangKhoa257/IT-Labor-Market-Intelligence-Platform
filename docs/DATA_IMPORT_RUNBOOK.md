# Data Import Runbook

Start and verify PostgreSQL:

```powershell
docker compose up -d postgres
docker compose ps
```

Apply and verify Database V1 migrations 001 and 002:

```powershell
alembic upgrade head
alembic current
```

These migrations create ingestion lineage only. They intentionally do not create a canonical job
destination, so the legacy `import_dataset` command belongs to the prototype Phase 3 database and
must not be run against a clean V1-only database. After a later canonical V1 migration is approved,
pilot data can be reimported from the preserved processed artifact with the then-current importer.

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

Stop PostgreSQL with `docker compose down`. The named volume remains until explicitly removed.
