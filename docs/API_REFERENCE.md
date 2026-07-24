# Read-Only API Reference

Start the application with `uvicorn apps.api.main:app --reload`. Swagger is available at `http://127.0.0.1:8000/docs` and OpenAPI JSON at `/openapi.json`.

The API exposes `/health` and the following `/api/v1` resources:

- `GET /jobs` and `GET /jobs/{job_id}`
- `GET /companies` and `GET /companies/{company_id}`
- `GET /skills`
- `GET /analytics/overview`
- `GET /analytics/categories`
- `GET /analytics/skills`
- `GET /analytics/salaries`
- `GET /analytics/locations`
- `GET /quality/summary`
- `GET /duplicates`

Jobs support pagination, keyword search, category, city, company, skill, employment type, work mode, status, disclosed salary, salary-range filters, and deterministic sorting by posted date, collected date, or salary. List responses omit descriptions. Detail responses provide at most a 500-character HTML-stripped preview.

Analytics are descriptive for the persisted sample. Currency groups are never combined.
