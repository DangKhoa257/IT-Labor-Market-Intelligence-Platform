# Architecture

**Phạm vi:** kiến trúc mục tiêu; Phase 0 chỉ tạo hợp đồng và tài liệu, chưa triển khai service.

## Luồng dữ liệu

```text
Source
  -> discovery
  -> fetch
  -> raw storage
  -> extraction
  -> normalization
  -> validation
  -> deduplication
  -> database
  -> analytics
  -> dashboard
```

`source_url`, `collected_at`, raw-object reference, `content_hash`, crawl-run ID và `extractor_version` đi cùng record để bảo toàn lineage.

## Các layer

1. **Data source layer** — registry của nguồn đã phê duyệt, owner, phạm vi, robots/ToS review, rate policy và trạng thái. Không có nguồn mặc định trong Phase 0.
2. **Crawler layer** — discovery, fetch, rate limiting, bounded retry và ghi `CrawlRun`/`CrawlError`. Không vượt CAPTCHA/login/paywall.
3. **Raw data layer** — lưu response/evidence bất biến theo content hash cùng fetch metadata; giới hạn truy cập và retention.
4. **Extraction layer** — parser theo nguồn chuyển evidence thành direct raw fields, không thực hiện business normalization.
5. **Normalization layer** — canonical rule dùng chung cho title/category, location, work mode, employment, seniority, experience, salary và skills.
6. **Validation layer** — kiểm required fields, type, enum, range, chronology và provenance; record lỗi được quarantine, không âm thầm sửa.
7. **Storage layer** — entities `Source`, `CrawlRun`, `JobPosting`, `JobSnapshot`, `Company`, `Skill`, `JobSkill`, `CrawlError`; database engine/migration chưa chốt.
8. **Analytics layer** — aggregate từ dữ liệu validated, giữ dimensions về nguồn/thời gian và cảnh báo coverage.
9. **API layer** — cung cấp query/read models, metadata freshness và quality; authentication/rate policy sẽ được thiết kế ở V1.
10. **Dashboard layer** — hiển thị xu hướng, filter và giới hạn dữ liệu; không dùng raw/unvalidated record.
11. **Benchmark layer** — gold labels, metric runner và regression gates độc lập với production extraction.

## Adapter riêng và canonical pipeline chung

```text
Source A adapter --\
Source B adapter ----> Canonical normalization -> validation -> dedup -> storage
Source N adapter --/
```

Mỗi adapter chỉ sở hữu selector/API mapping, pagination/discovery, fetch policy và extraction đặc thù của một nguồn. Adapter phát ra cùng extraction contract và phải có fixtures. Canonical pipeline không chứa selector/tên website; nó sở hữu taxonomy, null semantics, validation, hashing contract và dedup rules. Nhờ vậy thay đổi giao diện một website không làm thay đổi business schema.

## Ranh giới và tính bất biến

- Raw evidence là append-only; `JobSnapshot` mô tả trạng thái quan sát tại một thời điểm.
- `JobPosting` là identity ổn định theo `(source, source_job_id)`; cross-source duplicate là quan hệ/cluster, không xóa provenance.
- `content_hash` phát hiện nội dung thay đổi; rerun cùng evidence phải idempotent.
- Direct fields không bị ghi đè bởi suy luận. Normalized/inferred fields có thể tái tạo từ raw evidence và rule version.
- Trạng thái inactive chỉ được xác định theo policy quan sát đã chốt; một fetch lỗi không đồng nghĩa tin đã gỡ.

## Quyết định Phase 0

- Canonical field contract nằm trong `DATA_SCHEMA.md` và gold CSV header là bản kiểm tra máy đọc được.
- Kiến trúc tách source adapter khỏi pipeline dùng chung.
- Lưu snapshot để theo dõi thay đổi và giữ provenance thay vì chỉ giữ trạng thái mới nhất.
- Chưa chọn website, database, object storage, queue, scheduler, deployment platform hoặc LLM.
