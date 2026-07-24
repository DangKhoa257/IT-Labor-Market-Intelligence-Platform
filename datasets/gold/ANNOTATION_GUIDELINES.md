# Gold Dataset Annotation Guidelines

Template CSV chỉ minh họa cấu trúc và không phải dữ liệu nghiên cứu. Gold labels thật chỉ được tạo từ raw evidence của nguồn đã phê duyệt; annotator phải giữ URL/evidence reference và không điền theo kiến thức bên ngoài khi guideline không cho phép.

## Quy trình chung

1. Đọc toàn bộ title, metadata và description của đúng snapshot.
2. Ghi direct fields trước, giữ nguyên text; sau đó gán normalized/inferred fields.
3. Dùng null khi thiếu evidence, không dùng chuỗi rỗng/0/`unknown` như nhãn thay thế.
4. Ghi chú mọi trường hợp mơ hồ, rule được áp dụng và bằng chứng ngắn (field/section, không sao chép dữ liệu nhạy cảm).

## Gán job category

Dùng definition và exclusion rules trong `docs/JOB_TAXONOMY.md`. Chọn trách nhiệm chính mà ứng viên được tuyển để thực hiện; stack đơn lẻ không quyết định category. Nếu không đủ evidence hoặc vai trò không thuộc seed, gán `Other/Unclassified` và ghi lý do. Không dùng seniority làm category.

## Gán seniority

Ưu tiên title rõ ràng, sau đó phạm vi trách nhiệm và yêu cầu kinh nghiệm. `intern` là thực tập; `fresher` là entry role không yêu cầu kinh nghiệm đáng kể; `junior`, `mid`, `senior`, `lead`, `manager`, `director`, `executive` theo quyền tự chủ/phạm vi đã nêu. Không tự động gán senior chỉ từ số năm. Nếu title và description xung đột, ghi cả evidence và để null cho tới adjudication.

## Trích xuất kinh nghiệm

- Range “2–4 năm” -> min `2`, max `4`; “từ 3 năm” -> min `3`, max null; “tối đa 2 năm” -> min null, max `2`.
- Tháng được chia 12, cho phép số thập phân. “Không yêu cầu kinh nghiệm” -> min `0`, max `0` khi thật sự rõ.
- Không cộng số năm của nhiều kỹ năng. Nếu nhiều yêu cầu khác nhau, dùng yêu cầu tổng quát cho vai trò và ghi chú các yêu cầu skill-specific.

## Salary thỏa thuận

“Thỏa thuận/competitive/negotiable” không có con số: giữ `salary_raw`, đặt `salary_disclosed=false`, min/max/currency/period null và `salary_type=negotiable`. Không mặc định currency hoặc period. Nếu có số và từ “negotiable”, vẫn ghi số/currency/period được nêu, `salary_disclosed=true`, đồng thời ghi chú ambiguity của type nếu cần adjudication.

## Gán skill

Ghi phrase nguyên văn vào `skills_raw`, map sang canonical name trong `docs/SKILL_TAXONOMY.md` sau khi kiểm tra ngữ cảnh/false-positive note. Chỉ gán skill mà posting yêu cầu hoặc ưu tiên cho ứng viên; không gán công nghệ chỉ xuất hiện trong tên sản phẩm, footer, log hoặc mô tả công ty. Dedupe canonical skill, giữ nhiều raw mentions khi cần evidence.

## Bài có nhiều vai trò

Nếu một posting tuyển nhiều title tách biệt, không tự chia record khi chưa có raw-record policy. Chọn role nổi trội chỉ khi nguồn thể hiện rõ một vị trí chính; ngược lại gán `Other/Unclassified`, ghi danh sách role trong annotation note và đưa vào adjudication. Không tạo duplicate synthetic rows để tăng mẫu.

## Bài đăng lại và trùng lặp

Giữ từng source posting/snapshot cùng provenance. Đánh dấu duplicate/repost trong lớp annotation riêng khi nội dung, công ty, vai trò và địa điểm đủ evidence; không sửa `source_job_id`. Thay đổi nhỏ ngày đăng hoặc format không làm hai tin trở thành khác nhau; thay đổi vai trò/trách nhiệm đáng kể cần adjudication.

## Trường hợp không chắc chắn

Không đoán. Để field optional là null, thêm note theo mẫu: `field | evidence | alternatives | reason | annotator`. Gắn cờ `needs_adjudication=true` trong công cụ annotation (khi có). Adjudicator ghi quyết định và guideline/rule version; case lặp lại phải cập nhật guideline/taxonomy.
