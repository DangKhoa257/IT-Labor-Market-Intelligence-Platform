# Canonical Data Schema

**Phiên bản:** 0.5 (Database V1 Migration 006 compatibility). Mọi thay đổi bảng này phải cập nhật gold template và schema tests. Thời gian dùng ISO 8601 có timezone; tiền tệ dùng ISO 4217; `array<string>` được biểu diễn bằng JSON array khi trao đổi qua CSV. Bảng field bên dưới vẫn là exchange/gold contract tương thích pipeline hiện tại; relational storage chuẩn là `core`, `taxonomy`, `history`, `quality`, `analytics`, và `serving`. Migration 006 không thêm field exchange nên header gold template không đổi.

## Phân loại provenance

- **Direct:** lấy trực tiếp từ nội dung/metadata nguồn và giữ nguyên tối đa.
- **Normalized:** biến đổi deterministic từ direct value theo rule/taxonomy được version hóa.
- **Inferred:** không được nguồn nói trực tiếp; chỉ điền khi cột cho phép và rule có thể tái lập.
- **System:** sinh bởi hệ thống thu thập/xử lý, không lấy từ nội dung tuyển dụng.

`null` luôn có nghĩa là không có đủ bằng chứng/không áp dụng; không thay bằng `0`, `unknown`, chuỗi rỗng hoặc dự đoán. Với array optional, dùng null khi không có vùng dữ liệu để đọc và `[]` khi vùng dữ liệu tồn tại nhưng không tìm thấy giá trị hợp lệ.

## JobPosting canonical fields

| Field | Type | Req. | Class | Ý nghĩa | Nguồn | Chuẩn hóa | Null | Suy luận? |
|---|---|---:|---|---|---|---|---|---|
| `source` | string | R | System | Mã nguồn ổn định | Source registry/crawl run | lowercase slug | Không | Không |
| `source_job_id` | string | R | Direct | ID tin trong nguồn | URL/API/markup nguồn | trim; giữ leading zero | Không; nếu nguồn không cấp thì policy ID phải được duyệt | Không |
| `source_url` | string (URI) | R | Direct | URL bằng chứng chính | Discovery/fetch | absolute URL; bỏ fragment; query chỉ bỏ theo policy | Không | Không |
| `title_raw` | string | R | Direct | Chức danh nguyên văn | Nội dung nguồn | trim whitespace, không dịch | Không | Không |
| `title_normalized` | string | O | Normalized | Chức danh đã chuẩn hóa | `title_raw` | alias/rule được version hóa | Null nếu không đủ chắc chắn | Có, rule-based |
| `job_category` | enum string | O | Inferred | Nhóm nghề canonical | Title + description | Giá trị trong `JOB_TAXONOMY.md` | `Other/Unclassified` chỉ khi đã review/rule; null nếu chưa xử lý | Có |
| `company_name` | string | O | Direct | Tên công ty hiển thị | Nội dung nguồn | trim; lưu vào `company_name_raw`; trạng thái disclosure lưu riêng; không merge company chỉ theo normalized name | Null nếu ẩn/thiếu | Không trong field này |
| `company_industry` | string | O | Direct | Ngành công ty do nguồn nêu | Nội dung/metadata nguồn | trim; mapping taxonomy để phase sau | Null nếu thiếu | Không |
| `company_size` | string | O | Direct | Khoảng quy mô nhân sự | Nội dung/metadata nguồn | định dạng range chuẩn khi nguồn nêu rõ | Null nếu thiếu | Không |
| `location_raw` | string | O | Direct | Địa điểm nguyên văn | Nội dung nguồn | trim only | Null nếu remote/thiếu và không có text | Không |
| `city` | string | O | Normalized | Projection tỉnh/thành cho exchange cũ | `location_raw` | relational storage dùng nhiều `job_posting_locations`; field này chỉ điền khi có đúng một city rõ ràng | Null nếu remote-only, đa địa điểm hoặc mơ hồ | Có, rule-based |
| `work_mode` | enum: onsite, hybrid, remote | O | Inferred | Hình thức làm việc | Title/location/description | map alias Việt/Anh | Null nếu không nói rõ | Có |
| `employment_type` | enum: full_time, part_time, contract, internship, temporary, other | O | Normalized | Loại hợp đồng/công việc | Nội dung nguồn | map alias sang enum | Null nếu thiếu | Có, rule-based |
| `seniority` | enum: intern, fresher, junior, mid, senior, lead, manager, director, executive | O | Inferred | Cấp bậc vai trò | Title + yêu cầu kinh nghiệm/trách nhiệm | rule theo guideline/taxonomy version | Null nếu mơ hồ | Có |
| `experience_min_years` | number | O | Normalized | Số năm kinh nghiệm tối thiểu | Requirement text | tháng / 12; `0` chỉ khi nêu không yêu cầu | Null nếu không nêu | Có, chỉ parsing |
| `experience_max_years` | number | O | Normalized | Số năm kinh nghiệm tối đa | Requirement text | tháng / 12; phải >= min | Null nếu range mở/không nêu | Có, chỉ parsing |
| `salary_raw` | string | O | Direct | Lương nguyên văn | Nội dung nguồn | trim only | Null nếu không có vùng lương | Không |
| `salary_min` | number | O | Normalized | Projection cận dưới lương | `salary_raw` | storage dùng một hoặc nhiều `salary_offers`; không trộn kỳ, currency, tax basis | Null nếu thỏa thuận/range mở/parse thất bại | Có, chỉ parsing |
| `salary_max` | number | O | Normalized | Cận trên lương | `salary_raw` | numeric base unit; >= min | Null nếu thỏa thuận/range mở/parse thất bại | Có, chỉ parsing |
| `salary_currency` | string (ISO 4217) | O | Normalized | Đồng tiền được nêu | `salary_raw` | VND/USD/... theo ISO 4217 | Null nếu không xác định; không mặc định VND | Có, chỉ parsing |
| `salary_period` | enum: hour, day, month, year | O | Normalized | Kỳ trả lương | `salary_raw` | map unit sang enum | Null nếu không nêu; không mặc định month | Có, chỉ parsing |
| `salary_type` | enum: gross, net, negotiable, range, fixed, from, up_to, other | O | Normalized | Cách biểu diễn lương | `salary_raw` | deterministic parsing | Null nếu không xác định | Có, chỉ parsing |
| `salary_disclosed` | boolean | R | Normalized | Có giá trị/range lương công khai | Salary region/raw text | true chỉ khi có số tiền; “thỏa thuận” = false | Không | Có, deterministic |
| `skills_raw` | array<string> | O | Direct | Cụm kỹ năng nguyên văn | Skill section/description | giữ text, trim, dedupe exact | Null hoặc `[]` theo quy tắc array | Không |
| `skills_normalized` | array<string> | O | Normalized | Projection tên skill canonical | `skills_raw`/description | storage dùng taxonomy version + `job_posting_skills`, giữ requirement type | Null nếu chưa xử lý; `[]` nếu đã xử lý không có skill | Có, rule-based |
| `education_level` | string | O | Normalized | Trình độ học vấn tối thiểu | Requirement text | map seed enum khi taxonomy được duyệt | Null nếu thiếu/mơ hồ | Có, rule-based |
| `language_requirements` | array<string> | O | Normalized | Ngôn ngữ con người được yêu cầu | Requirement text | canonical language + level nếu nêu | Null/`[]` theo quy tắc array | Có, rule-based |
| `description_raw` | string | R | Direct | Mô tả tin nguyên văn/đã trích text | Nội dung nguồn | normalize line ending; không tóm tắt | Không | Không |
| `posted_at` | datetime | O | Direct | Thời điểm nguồn công bố | Nội dung/metadata nguồn | ISO 8601 timezone; ghi precision nếu model mở rộng | Null nếu thiếu/relative date không resolve được | Không |
| `expires_at` | datetime | O | Direct | Thời điểm hết hạn do nguồn nêu | Nội dung/metadata nguồn | ISO 8601 timezone | Null nếu thiếu | Không |
| `first_seen_at` | datetime | R | System | Lần đầu hệ thống quan sát identity | Successful crawl | ISO 8601 UTC | Không | Không |
| `last_seen_at` | datetime | R | System | Lần gần nhất quan sát thành công | Successful crawl | ISO 8601 UTC; >= first_seen | Không | Không |
| `collected_at` | datetime | R | System | Thời điểm thu evidence/snapshot này | Fetch clock | ISO 8601 UTC | Không | Không |
| `is_active` | boolean | R | System | Projection trạng thái lifecycle cũ | Quan sát thành công | map từ `current_status`; fetch lỗi không đủ để đóng tin | Không | Có, từ quan sát hệ thống |
| `content_hash` | string | R | System | Hash nội dung canonical để nhận biết đổi | Raw/normalized evidence bytes | lowercase SHA-256 hex; contract bytes phải version hóa | Không | Không |
| `extractor_version` | string | R | System | Phiên bản extractor tạo record | Build/runtime metadata | semantic version hoặc immutable build ID; độc lập với Alembic migration revision | Không | Không |
| `confidence_score` | number [0,1] | R | System | Confidence tổng hợp của normalized/inferred fields | Validation/extraction rules | clamp [0,1]; công thức version hóa | Không | Có, từ rule metrics |

`R` = required, `O` = optional. Từ “suy luận” ở bảng bao gồm parsing/rule deterministic; LLM không thuộc Phase 0.

## Constraints xuyên trường

- Identity trong một nguồn là unique `(source, source_job_id)`; URL có thể đổi.
- `first_seen_at <= collected_at` và `first_seen_at <= last_seen_at`.
- Nếu cả hai có giá trị: `experience_min_years <= experience_max_years`, `salary_min <= salary_max`.
- `salary_disclosed=false` khi lương thiếu hoặc chỉ “thỏa thuận”; khi true phải có ít nhất một cận số, currency và period nếu nguồn cung cấp.
- `skills_normalized` chỉ chứa canonical names trong skill registry; alias không được ghi vào danh sách này.
- Mọi snapshot phải liên kết raw evidence, crawl run và canonical posting trong storage model dù các khóa liên kết chưa nằm trong exchange schema v0.1.

## Entity model

### Database V1 Migration 003 storage mapping

- Exchange identity `source` + `source_job_id` maps to unique source-scoped identity in `core.job_postings`; cross-source records remain separate.
- Company candidates, aliases, and domains live separately; normalized company names are indexed but are not unique and do not trigger an automatic merge.
- `location_raw` is retained on the posting while resolved locations are repeatable relations, including remote scope.
- Flat salary exchange fields are compatibility projections only. Relational salary offers remain separate by component, period, currency, tax basis, disclosure, and estimation state.
- Occupations and skills must use taxonomy versions of their own type, `taxonomy_type` is immutable after a version is inserted, and each parent must be in the child's version. Assignments retain confidence/method metadata.
- `description_raw` maps to the single currently retained description. Historical descriptions and job observations are not part of Migration 003.
- Every persisted posting retains `source_url`, first/last-seen timestamps, and optional identity-matched lineage to `ingestion.extracted_records`; deleting that record clears only the lineage ID.

### Database V1 Migration 004 history and quality mapping

- `history.job_observations` stores immutable canonical states whose posting, extracted-record, and optional crawl-run source identities must match; `core.job_postings.current_observation_id` can point only to the same job.
- Canonical hashes are not unique, so A → B → A is valid when each observation has distinct lineage. An unchanged recrawl updates only current-state `last_seen_at`.
- Observation descriptions, locations, salaries, skills, and occupations are complete immutable snapshots. Status, field-change, and repost events are also append-only.
- Historical salaries are self-contained and do not reference mutable current salary rows. Description text supports only one-way retention removal to redacted/expired.
- `quality.field_evidence` preserves immutable direct, normalized, inferred, unavailable, and unverified provenance while allowing controlled reviewer metadata. Quality issues retain mutable review/resolution state and deletion-restricted, source-consistent context.
- Duplicate candidates and clusters are advisory and never delete or merge source postings.

### Database V1 Migration 005 analytics mapping

- Observation and salary facts map uniquely to immutable history rows; bridges map historical
  location, occupation, and skill children without changing their provenance.
- Dates and daily activity use UTC. Late observations can replace an affected old aggregate grain,
  and every calculation records its refresh run and calculation version.
- Source posting counts are not reduced by advisory duplicate clusters. Salary aggregates keep
  currency, period, and tax basis separate, while missing salary values remain SQL `NULL`.
- Only analytics location and occupation dimensions use the deterministic surrogate key `-1` for
  unknown. Those members have no operational UUID and do not change the exchange/gold contract.
- PostgreSQL rejects cross-wired observation/salary/bridge lineage and makes facts and bridges
  append-only. Taxonomy dimension versions and parents must match their operational entities;
  calendar attributes are deterministic and immutable; daily salary ranges cannot be inverted.
  Fact change flags/counts follow exact history-child definitions, and source-scoped refresh
  source/version lineage cannot be reassigned after reference.
- Creating an analytics job fact finalizes that observation's description/location/salary/skill/
  occupation snapshot against later inserts. Corrections create a new historical observation;
  status, change, and repost events remain unaffected.

### Database V1 Migration 006 serving and RPC mapping

- `serving.job_search_documents` and `serving.job_search_salary_offers` are rebuildable current
  projections with explicit history, canonical-pointer, source, salary, and refresh lineage.
- Weighted PostgreSQL full-text search and filters are exposed only through eight versioned
  `SECURITY DEFINER` functions in the function-only `api` schema.
- Stale documents are hidden whenever their observation does not equal the posting's current
  observation. `anon` and `authenticated` have no direct serving relation privileges.

### JobPosting

Identity logic lâu dài của một tin tại một nguồn. Khóa đề xuất: internal UUID; unique `(source_id, source_job_id)`. Giữ current canonical state, first/last seen và active; có nhiều `JobSnapshot`. Cross-source duplicates không bị hợp nhất vật lý ở Phase 0.

### JobSnapshot

Quan sát bất biến của `JobPosting` tại `collected_at`: raw evidence reference, HTTP/fetch metadata, content hash, extractor version và payload canonical tại thời điểm đó. Unique đề xuất `(job_posting_id, collected_at, content_hash)`.

### Company

Identity công ty chuẩn hóa độc lập với tên hiển thị. Gồm internal ID, canonical name, aliases và metadata đã xác minh. Việc entity resolution phải giữ confidence/provenance; không tự gộp chỉ theo tên gần giống.

### Skill

Registry gồm internal ID, canonical name, category, aliases, false-positive notes và taxonomy version. Canonical name phải unique trong phạm vi taxonomy version.

### JobSkill

Quan hệ many-to-many giữa `JobPosting`/snapshot và `Skill`, giữ raw mention, evidence span/source section, required/preferred nếu có, confidence và extraction rule version.

### Source

Registry của nguồn: stable slug, base URL, approval status, robots/ToS review references, owner, rate policy và timestamps. Chỉ nguồn approved mới được scheduler kích hoạt.

### CrawlRun

Một lần chạy có source, started/finished time, configuration/version, status và counters discovery/fetch/success/error. Dùng để audit và tính benchmark crawl.

### CrawlError

Lỗi có cấu trúc liên kết `CrawlRun`, URL/job ID nếu biết, stage, error category, retryable flag, sanitized message và timestamp. Không lưu secret hoặc response nhạy cảm trong error text.

## Chưa quyết định

Migration 006 quyết định private serving storage và function-only RPC contract từ current state,
immutable history và analytics. Production refresh scheduling, writer/diff automation, lifecycle
scheduling và deduplication algorithms vẫn cần task/migration riêng. Không suy diễn rằng
current-state row là lịch sử đầy đủ.
