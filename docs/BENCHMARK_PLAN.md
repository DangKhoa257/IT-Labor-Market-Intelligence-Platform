# Benchmark Plan

**Trạng thái:** đề xuất Phase 0. Ngưỡng MVP là target ban đầu, chưa phải kết quả đo. Chỉ công bố metric khi sample, version gold set và confidence interval (khi phù hợp) được ghi rõ.

## Dataset và protocol chung

- Gold set phải là tin thật từ các nguồn đã được duyệt, được lấy mẫu theo nguồn/thời gian/nhóm nghề; template không phải benchmark data.
- Tách development và held-out test set theo posting/duplicate cluster để tránh leakage.
- Hai annotator gán nhãn độc lập cho task chủ quan; adjudicator xử lý bất đồng và lưu lý do.
- Version hóa raw evidence, guideline, schema, taxonomy và pipeline commit. Báo cáo micro/macro hoặc theo nguồn khi mất cân bằng ảnh hưởng kết luận.

| Metric | Công thức | Dữ liệu đầu vào | Cách đo | Ngưỡng MVP đề xuất | Hạn chế |
|---|---|---|---|---:|---|
| Crawl success rate | successful fetches / eligible fetch attempts | CrawlRun, HTTP outcome, approved URL set | Loại URL bị policy chặn khỏi denominator; phân tầng theo source/status class | >= 95% | Website outage, URL chết và anti-bot có thể làm metric biến động; success không đảm bảo nội dung đúng |
| Required-field coverage | records đủ mọi required field / valid fetched records | Extracted records + schema validator | Đo tổng và coverage từng field; chuỗi rỗng tính là thiếu | >= 98% | Field có mặt có thể sai; required set dễ làm metric đẹp giả tạo |
| Field extraction accuracy | correct field labels / evaluated field labels | Gold field values + predictions | Exact/normalized match theo field; báo cáo từng field và weighted aggregate | >= 95% aggregate; không field cốt lõi < 90% | Exact match phạt khác biệt vô hại; aggregate che field yếu |
| Salary parsing accuracy | postings có toàn bộ salary tuple đúng / postings có salary evidence | Gold raw salary và min/max/currency/period/type/disclosed | Exact tuple match; thêm component accuracy để chẩn đoán | >= 90% exact tuple | Ít tin công khai lương; gross/net và period thường mơ hồ |
| Job classification accuracy | correct category / labeled postings | Gold category + predicted category | Accuracy, macro-F1 và confusion matrix trên held-out set | >= 85% accuracy và macro-F1 | Một nhãn không biểu diễn tốt tin đa vai trò; lệch class |
| Seniority classification accuracy | correct seniority / postings có gold seniority | Gold seniority + prediction | Accuracy, macro-F1; null/abstain được báo riêng | >= 85% accuracy trên labeled set | Seniority khác nhau theo công ty; guideline vẫn có tính chủ quan |
| Skill extraction precision | TP / (TP + FP) | Gold skill sets + predicted sets | Exact canonical skill match ở posting level; micro và macro | >= 90% | Gold annotation có thể bỏ sót skill ngầm; alias/taxonomy version ảnh hưởng |
| Skill extraction recall | TP / (TP + FN) | Như trên | Như trên; tính cả abstain như missing prediction | >= 80% | Description dài làm annotation không đầy đủ; canonical granularity khác nhau |
| Skill extraction F1 | 2PR / (P + R) | Precision và recall | Harmonic mean, bằng 0 khi P+R=0 | >= 85% | Một số duy nhất che trade-off và nhóm skill hiếm |
| Duplicate detection precision | predicted duplicate pairs đúng / mọi predicted duplicate pairs | Gold duplicate clusters + predicted clusters | Chuyển cluster thành pair, đo pairwise; audit false merge | >= 95% | Cluster lớn tạo nhiều pair và chi phối metric |
| Duplicate detection recall | gold duplicate pairs tìm thấy / mọi gold duplicate pairs | Như trên | Pairwise recall; báo thêm theo same-source/cross-source | >= 85% | Gold duplicate pair khó xác nhận khi nội dung đổi/ẩn công ty |
| Data freshness | median(`collected_at - posted_at`) và % <= SLA | Posting timestamps + collection timestamps | Chỉ record có posted_at; báo median, p90, theo source | median <= 24h, p90 <= 48h | `posted_at` thiếu/relative/được refresh có thể không phải lần đăng đầu |
| Traceability | records mở được source URL/raw evidence/crawl run/version / records sampled | Storage links + metadata | Lấy mẫu ngẫu nhiên và tự động kiểm tra referential integrity | 100% | URL nguồn có thể hết hạn; mở link không chứng minh raw evidence đầy đủ |
| Processing speed | valid records hoàn tất / elapsed pipeline seconds | Pipeline timestamps + record counts | Benchmark trên hardware/dataset cố định, warm-up tách riêng, báo p50/p95 latency | >= 10 records/s trên cấu hình tham chiếu | Phụ thuộc I/O/hardware; throughput không phản ánh crawl politeness |

## Quality gates và báo cáo

Một release không đạt nếu traceability dưới 100%, required-field coverage dưới ngưỡng, hoặc regression có ý nghĩa vượt tolerance đã chốt, dù aggregate khác đạt. Mỗi report phải ghi dataset version, số mẫu, phân bố nguồn/category, pipeline version, hardware cho speed test, metric numerator/denominator và danh sách known failures.

## Còn mở

Sample size, nguồn, sampling weights, SLA freshness, cấu hình phần cứng và tolerance regression chờ Deep Research/pilot. Sau pilot cần đo annotator agreement và hiệu chỉnh ngưỡng trước khi dùng làm release gate chính thức.
