# Data Import Runbook

Start and verify PostgreSQL:

```powershell
docker compose up -d postgres
docker compose ps
```

Apply the schema and import the analysis-ready dataset:

```powershell
alembic upgrade head
python -m it_labor_market_intelligence.cli.import_dataset `
  --input datasets/processed/topdev_analysis_ready.jsonl `
  --source topdev `
  --duplicates-report reports/topdev_duplicates.json
```

Re-running the command skips existing identities and duplicate clusters. Use `--replace-existing` to update canonical fields and rebuild quality/skill relations. Duplicate report members are resolved by source and source job ID; unresolved members fail the import rather than silently producing partial clusters. `--dry-run` rolls back changes. `--batch-size` controls job commit size.

Stop PostgreSQL with `docker compose down`. The named volume remains until explicitly removed.
