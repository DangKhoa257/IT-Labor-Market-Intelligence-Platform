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
  --source topdev
```

Re-running the command skips existing identities. Use `--replace-existing` to update their canonical fields and rebuild quality/skill relations. `--dry-run` rolls back all changes. `--batch-size` controls commit size.

Stop PostgreSQL with `docker compose down`. The named volume remains until explicitly removed.
