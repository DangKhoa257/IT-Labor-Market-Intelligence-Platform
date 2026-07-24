# Agent Rules

Các quy tắc này áp dụng cho mọi người và agent làm việc trong repository:

1. Không tự ý thay đổi kiến trúc hoặc mở rộng phase nếu chưa có quyết định được ghi nhận.
2. Không tự chọn nguồn crawl. Mỗi nguồn phải qua nghiên cứu robots.txt, điều khoản sử dụng và phê duyệt.
3. Không tạo số liệu giả dưới dạng kết quả nghiên cứu. Dữ liệu minh họa phải ghi rõ `EXAMPLE_NOT_REAL_DATA`.
4. Không bỏ qua robots.txt, điều khoản sử dụng hoặc hạn chế truy cập hợp pháp.
5. Không hướng dẫn hay triển khai cách vượt CAPTCHA, đăng nhập, paywall hoặc access control.
6. Không dùng LLM khi rule-based extraction đáp ứng được yêu cầu và có thể kiểm thử.
7. Không sửa cùng file với agent khác nếu chưa được phân công hoặc điều phối rõ ràng.
8. Mọi thay đổi canonical schema phải đồng thời cập nhật `docs/DATA_SCHEMA.md`, gold template và schema tests.
9. Mỗi extractor phải có test fixture đại diện và test cho lỗi đầu vào.
10. Mọi bản ghi dữ liệu phải giữ `source_url` và `collected_at` để truy vết.
11. Không ghi secret, token, cookie, dữ liệu đăng nhập hoặc dữ liệu cá nhân không cần thiết vào repository.
12. Mọi quyết định quan trọng về nguồn, schema, taxonomy, chất lượng và kiến trúc phải được ghi vào tài liệu.
13. Không trình bày dữ liệu ví dụ, fixture hoặc benchmark template như dữ liệu thị trường thật.
14. Phase 0 không triển khai crawler website thật, AI/LLM, database migration, API hay dashboard.
