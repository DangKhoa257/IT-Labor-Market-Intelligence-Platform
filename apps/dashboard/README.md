# IT Labor Market Intelligence Platform — Frontend Dashboard

A production-grade React analytics dashboard for visualizing, exploring, and inspecting Vietnamese IT labor market intelligence data collected by the platform.

## Audit Summary

- **Existing State**: Prior to Phase 4, `apps/dashboard/` was uninitialized (contained only a `.gitkeep`).
- **Backend Stack**: Read-only FastAPI service running on Python 3.12, serving SQLAlchemy/PostgreSQL (or local SQLite) database entities across 13 endpoints.
- **Data Reality**: Pilot dataset contains **19 jobs**, **9 companies**, **16 skills**, and **3 duplicate clusters**. Descriptive metrics reflect persisted pilot observations only.
- **CORS vs Proxy**: FastAPI does not currently attach CORS headers. Development uses Vite proxy (`/api` & `/health` -> `http://127.0.0.1:8000`) to avoid cross-origin issues without backend mutations.

## Technology Stack

- **Framework**: React 19 & TypeScript (Strict Mode)
- **Build Tool**: Vite 8 (with `@vitejs/plugin-react` & `@tailwindcss/vite`)
- **Styling**: Tailwind CSS v4 (Inter font, subtle borders, editorial light theme)
- **Routing**: React Router v7 (`react-router-dom`)
- **Data Fetching & State**: TanStack Query v5 (`@tanstack/react-query`)
- **Visualizations**: Recharts v3
- **Icons**: Lucide React

## Folder Structure

```text
apps/dashboard/
├── src/
│   ├── api/             # Typed API client, query key factory
│   │   ├── client.ts
│   │   └── queryKeys.ts
│   ├── components/      # Shared UI components (StatCard, ChartCard, DataTable, etc.)
│   │   ├── ApiOfflineBanner.tsx
│   │   ├── Badge.tsx
│   │   ├── ChartCard.tsx
│   │   ├── DataTable.tsx
│   │   ├── EmptyState.tsx
│   │   ├── ErrorState.tsx
│   │   ├── LimitationsPanel.tsx
│   │   ├── LoadingSkeleton.tsx
│   │   ├── PageHeader.tsx
│   │   ├── Pagination.tsx
│   │   ├── SearchInput.tsx
│   │   ├── StatCard.tsx
│   │   └── StatusBadge.tsx
│   ├── hooks/           # TanStack Query hooks (useJobs, useSkills, etc.)
│   │   └── useApi.ts
│   ├── layouts/         # AppShell layout with responsive sidebar & header
│   │   └── AppShell.tsx
│   ├── pages/           # 10 Route pages (Overview, Jobs, JobDetail, etc.)
│   │   ├── CompaniesPage.tsx
│   │   ├── CompanyDetailPage.tsx
│   │   ├── DuplicatesPage.tsx
│   │   ├── JobDetailPage.tsx
│   │   ├── JobsPage.tsx
│   │   ├── LocationsPage.tsx
│   │   ├── OverviewPage.tsx
│   │   ├── QualityPage.tsx
│   │   ├── SalariesPage.tsx
│   │   └── SkillsPage.tsx
│   ├── types/           # Pydantic-matched API TypeScript definitions
│   │   └── api.ts
│   ├── utils/           # Currency, date, and text formatters
│   │   └── format.ts
│   ├── App.tsx
│   ├── index.css
│   └── main.tsx
├── public/
├── .env.example
├── .env
├── eslint.config.js
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Environment Variables

Defined in `.env` and `.env.example`:

```env
# Leave empty when using Vite dev server proxy (recommended for local dev):
VITE_API_BASE_URL=

# Set explicitly when connecting to a remote or standalone backend without proxy:
# VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Backend Startup

Before launching the dashboard, start the backend FastAPI server:

```powershell
$env:DATABASE_URL="sqlite+pysqlite:///./phase3_local.db"
python -m uvicorn apps.api.main:app --reload
```

Backend will run at `http://127.0.0.1:8000`.

## Frontend Startup & Scripts

From `apps/dashboard/`:

```bash
# Install dependencies
npm install --legacy-peer-deps

# Development server (http://localhost:5173)
npm run dev

# Production build
npm run build

# Code linting
npm run lint

# TypeScript verification
npm run typecheck
```

## API Integration & Proxy

The dashboard communicates with the backend via `src/api/client.ts`. In development, Vite's dev server proxies API calls:
- `/health` -> `http://127.0.0.1:8000/health`
- `/api/*` -> `http://127.0.0.1:8000/api/*`

This eliminates browser CORS issues without modifying backend source code.

## Known Data Limitations

1. **Pilot Sample Notice**: Current dataset contains **19 jobs** from TopDev. Figures describe the persisted sample and are not representative of national market totals.
2. **Currency Isolation**: VND and USD salaries are processed separately and never converted via exchange rates.
3. **Advisory Deduplication**: Duplicate clusters (3 total) are advisory suggestions; records remain intact in the database.

## Troubleshooting

- **API Offline Banner**: App shows a top banner if `/health` fails. Ensure FastAPI backend is running.
- **Port Conflicts**: Vite defaults to port `5173`. Change port in `vite.config.ts` if needed.
