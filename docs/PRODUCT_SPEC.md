# Product Specification

**Trạng thái:** Phase 0 foundation — chưa xác nhận nguồn crawl và chưa có dữ liệu thị trường thật.

## Product vision

Xây dựng nguồn dữ liệu đáng tin cậy, có thể truy vết về thị trường lao động IT Việt Nam để người dùng hiểu nhu cầu nghề nghiệp, kỹ năng, lương và biến động tuyển dụng mà không phụ thuộc vào cách trình bày riêng của từng website.

## Người dùng mục tiêu

- Người tìm việc và sinh viên cần hiểu kỹ năng, vai trò và mức lương thị trường.
- Nhà tuyển dụng và đội workforce planning cần benchmark nhu cầu tuyển dụng.
- Trường học, đơn vị đào tạo và nhà hoạch định chính sách cần nhận diện khoảng cách kỹ năng.
- Nhà phân tích và đội sản phẩm cần dữ liệu chuẩn hóa, có provenance.

## Vấn đề cần giải quyết

Dữ liệu tuyển dụng phân tán, biến đổi theo thời gian, trùng lặp và dùng thuật ngữ không thống nhất. Lương thường thiếu hoặc khác kỳ trả/currency; kỹ năng lẫn trong văn bản; cùng một tin có thể xuất hiện trên nhiều nguồn. Các phân tích hiện thiếu phép đo chất lượng và bằng chứng nguồn.

## Câu hỏi phân tích

- Nhóm nghề, seniority và kỹ năng nào có nhu cầu cao theo thời gian và địa điểm?
- Kỹ năng nào thường xuất hiện cùng nhau và khác nhau giữa các nhóm nghề?
- Phân bố lương đã công khai thay đổi thế nào theo nghề, seniority và work mode?
- Bao nhiêu tin là mới, thay đổi, hết hạn hoặc đăng lại?
- Mức độ bao phủ, độ mới và độ chính xác của từng nguồn/pipeline là bao nhiêu?

## Phạm vi MVP

- Thu thập từ danh sách nguồn công khai đã được phê duyệt sau nghiên cứu.
- Lưu raw evidence và metadata thu thập, không ghi đè lịch sử snapshot.
- Trích xuất, chuẩn hóa và kiểm tra canonical job-posting schema.
- Phân loại nghề/seniority, chuẩn hóa kỹ năng, kinh nghiệm, lương, địa điểm.
- Khử trùng trong và giữa nguồn; theo dõi first/last seen và trạng thái active.
- Tính chỉ số chất lượng, phân tích nền tảng và cung cấp qua API/dashboard tối thiểu.

## Ngoài phạm vi

- Dữ liệu private, yêu cầu đăng nhập, paywall, CAPTCHA hoặc vượt access control.
- Tự động nộp hồ sơ, chấm điểm ứng viên hoặc quyết định tuyển dụng.
- Tuyên bố đại diện toàn bộ thị trường khi độ bao phủ chưa được chứng minh.
- Phase 0: crawler thật, AI/LLM, migration database, API và dashboard.

## Yêu cầu chức năng

1. Mỗi source adapter hỗ trợ discovery/fetch theo chính sách nguồn và lưu lỗi có cấu trúc.
2. Mỗi lần fetch thành công lưu raw evidence bất biến cùng URL, thời điểm và content hash.
3. Extractor tạo record theo `DATA_SCHEMA.md` và ghi phiên bản extractor.
4. Pipeline chuẩn hóa taxonomy, lương, kinh nghiệm, địa điểm và kỹ năng theo rule có test.
5. Validator phân biệt required/optional, direct/normalized/inferred/system và ghi confidence.
6. Deduplication nhóm bản đăng tương ứng nhưng vẫn bảo toàn record/snapshot nguồn.
7. Lifecycle xác định first seen, last seen và active theo chính sách đã công bố.
8. Analytics/API/dashboard chỉ dùng dữ liệu đã qua validation và hiển thị phạm vi/độ mới.
9. Benchmark có thể tái chạy trên gold dataset được version hóa.

## Yêu cầu phi chức năng

- **Traceability:** mọi record truy ngược được source URL, raw evidence, crawl run và extractor version.
- **Reproducibility:** rule, taxonomy, schema và gold labels được version hóa.
- **Reliability:** retry có giới hạn, idempotent ingestion và lỗi từng item không làm mất toàn bộ run.
- **Security/privacy:** không commit secret; giảm thiểu PII; quyền truy cập theo môi trường.
- **Maintainability:** adapter tách khỏi canonical pipeline; thay đổi schema có test và tài liệu.
- **Observability:** log có cấu trúc và đo throughput, lỗi, coverage, freshness.

## Yêu cầu chất lượng dữ liệu

- `source`, `source_job_id`, `source_url`, `title_raw`, `description_raw`, `collected_at`, `content_hash`, `extractor_version` phải hiện diện.
- Không biến giá trị thiếu thành 0, chuỗi rỗng hoặc nhãn suy đoán; dùng null theo schema.
- Giá trị suy luận phải nằm trong trường cho phép, có rule tái lập và phản ánh qua confidence.
- Thời gian dùng ISO 8601 có timezone; currency dùng ISO 4217; array không chứa alias trùng.
- Raw text được giữ nguyên để audit; normalized field không thay thế bằng chứng gốc.

## Đạo đức và tuân thủ

Chỉ xử lý dữ liệu tuyển dụng công khai sau khi xem xét robots.txt, điều khoản sử dụng, tính hợp pháp và tác động lên hệ thống nguồn. Không vượt kiểm soát truy cập, không thu thập dữ liệu nhạy cảm không cần thiết, áp dụng rate limit, quy trình gỡ dữ liệu và ghi rõ giới hạn đại diện. Kết quả là tín hiệu quan sát từ nguồn được chọn, không phải thống kê chính thức của toàn thị trường.

## Acceptance criteria MVP

- Nguồn và chính sách crawl được phê duyệt, có owner và evidence tuân thủ.
- Pipeline tạo record hợp lệ theo schema, giữ raw evidence và provenance.
- Benchmark đạt ngưỡng MVP trong `BENCHMARK_PLAN.md` trên gold set độc lập.
- Duplicate/lifecycle có audit trail; rerun không tạo record logic ngoài ý muốn.
- Dashboard/API nêu rõ thời điểm cập nhật, nguồn, coverage và giới hạn dữ liệu.
- Test, lint, type check và tài liệu vận hành chạy được trong CI.

## Roadmap

- **V0 — Foundation:** đặc tả, schema, taxonomy draft, kiến trúc, benchmark, annotation guideline và test nền.
- **V1 — MVP:** nguồn đã duyệt, ingestion/raw storage, canonical processing, database, benchmark và analytics/API/dashboard tối thiểu.
- **V2 — Scale & insight:** mở rộng nguồn có kiểm soát, lifecycle/dedup nâng cao, taxonomy tinh chỉnh, phân tích xu hướng và monitoring chất lượng.

## Giả định chưa xác minh

- Chưa biết nguồn nào cho phép thu thập tự động và trường nào hiện diện ổn định.
- Chưa xác minh mức đại diện theo ngành, địa phương, seniority hoặc quy mô công ty.
- Chưa chốt hạ tầng database/object storage, lịch crawl và SLA freshness.
- Chưa xác minh taxonomy/alias với dữ liệu thật và annotator agreement.
- Chưa chốt cách quy đổi lương, tỷ giá, xử lý thuế/gross/net và tin không nêu kỳ trả.
- Ngưỡng benchmark hiện là đề xuất, cần hiệu chỉnh sau pilot và gold dataset thật.
