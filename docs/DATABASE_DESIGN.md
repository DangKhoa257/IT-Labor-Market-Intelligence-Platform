# Database Design

Phase 3 uses SQLAlchemy 2.x and PostgreSQL 16. `Source` plus `source_job_id` is the canonical job identity. Companies and skills are normalized dimensions; skills are connected through `JobSkill`, so names are not duplicated on `JobPosting`.

`JobSnapshot` retains structured historical payloads, `CrawlRun` records import totals, `DataQualityIssue` stores validation findings, and duplicate clusters retain every member. Nullable columns preserve the pipeline's null semantics. Timestamps use timezone-aware UTC values.

The initial migration is `20260724_0001_phase3_schema`. Configuration comes only from `DATABASE_URL`; SQLite support is restricted to isolated tests.

```powershell
alembic upgrade head
alembic downgrade -1
```
