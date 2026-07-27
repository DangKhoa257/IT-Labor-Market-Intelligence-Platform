# Vietnam IT Labor Market Intelligence Platform

Nền tảng dữ liệu end-to-end nhằm biến các tin tuyển dụng IT công khai tại Việt Nam thành dữ liệu có thể truy vết, so sánh và phân tích. Dự án giải quyết tình trạng dữ liệu phân tán, cách gọi chức danh/kỹ năng không thống nhất, lương khó so sánh và tin trùng giữa nhiều nguồn.

## Mục tiêu sản phẩm

- Thu thập hợp pháp tin tuyển dụng công khai và lưu bằng chứng nguồn.
- Chuẩn hóa nghề nghiệp, kỹ năng, lương, kinh nghiệm, địa điểm và hình thức làm việc.
- Theo dõi vòng đời tin, phát hiện trùng lặp và đo chất lượng dữ liệu.
- Cung cấp dữ liệu cho phân tích thị trường, API và dashboard ở các phase sau.

## Kiến trúc tổng quan

`Source -> discovery -> fetch -> raw storage -> extraction -> normalization -> validation -> deduplication -> database -> analytics -> API/dashboard`

Adapter theo từng website chỉ xử lý discovery/fetch/extraction đặc thù. Canonical pipeline dùng chung chịu trách nhiệm chuẩn hóa, kiểm tra, khử trùng và lưu trữ. Xem [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Cấu trúc repository

```text
apps/                 API và dashboard (chưa triển khai)
crawler/              Source adapters, extractors và pipelines (chưa có nguồn thật)
data_processing/      Chuẩn hóa, lương, kỹ năng và deduplication
analytics/            Phân tích thị trường
database/             Thiết kế lưu trữ; Phase 0 chưa có migration
benchmarks/            Đánh giá chất lượng
datasets/             Raw, processed và gold data
docs/                 Đặc tả sản phẩm, schema, taxonomy, kiến trúc, benchmark
tests/                Unit, integration và fixtures
```

## Phạm vi MVP

MVP sẽ thu thập các nguồn đã được phê duyệt, lưu raw evidence, tạo bản ghi theo canonical schema, chuẩn hóa các trường chính, phát hiện trùng, theo dõi trạng thái tin và cung cấp các chỉ số nền tảng. Phase 0 hiện tại chỉ xây nền móng tài liệu, schema, gold template và test; chưa crawl dữ liệu thật.

## Roadmap và trạng thái

- V0 / Phase 0 — foundation: tài liệu, schema, taxonomy draft, benchmark plan, annotation template và tooling. **Hiện tại.**
- V1 — MVP data pipeline: adapter cho nguồn đã duyệt, lưu raw data, extraction/normalization, database và quality checks.
- V2 — sản phẩm phân tích: mở rộng nguồn, lifecycle/deduplication nâng cao, API, analytics và dashboard.

> Cảnh báo: nguồn crawl chưa được chốt. Không thêm adapter hoặc thu thập website thật cho đến khi nghiên cứu nguồn, robots.txt, điều khoản sử dụng và phê duyệt tuân thủ hoàn tất.

## Thiết lập development environment

Yêu cầu Python 3.12.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m black --check .
python -m mypy .
```

Sao chép `.env.example` thành `.env` cho cấu hình local và không commit secret.

## Local validation status

Validation was run locally with Python 3.12.10:

- pytest: passed
- Ruff: passed
- Black: passed
- MyPy: blocked locally by Windows Application Control while importing `librt.base64`; this is an environment restriction, not a confirmed project code error.
# IT Labor Market Intelligence Platform

## Offline data pipeline

The source-agnostic Phase 2 pipeline enriches canonical JSONL records, validates quality, reports duplicate candidates, and creates descriptive offline analytics. See [DATA_QUALITY_PIPELINE.md](docs/DATA_QUALITY_PIPELINE.md) for the command and generated artifacts.

## PostgreSQL and read-only API

```powershell
docker compose up -d postgres
alembic upgrade head
alembic current
uvicorn apps.api.main:app --reload
```

Migrations 001–004 create the private Database V1 system, ingestion-lineage, taxonomy, canonical
current-state, immutable history, and data-quality layers. The current API still uses the Phase 3
prototype ORM, and no full observation writer or canonical importer is included. See
[DATABASE_V1_FOUNDATION.md](docs/DATABASE_V1_FOUNDATION.md),
[DATABASE_V1_CORE.md](docs/DATABASE_V1_CORE.md), and
[DATABASE_V1_HISTORY_QUALITY.md](docs/DATABASE_V1_HISTORY_QUALITY.md). Use
`alembic downgrade 20260726_0003` to remove only Migration 004 and `docker compose down` to stop
PostgreSQL.

Run checks with `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .`. See [DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md), [API_REFERENCE.md](docs/API_REFERENCE.md), and [DATA_IMPORT_RUNBOOK.md](docs/DATA_IMPORT_RUNBOOK.md).
