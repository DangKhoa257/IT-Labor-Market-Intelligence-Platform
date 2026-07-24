# Job Taxonomy — Draft Seed

> Đây là taxonomy draft cho Phase 0. Nhãn, alias và ranh giới phải được điều chỉnh sau khi có gold dataset thật và đo inter-annotator agreement. Phân loại theo trách nhiệm chính, không chỉ theo từ khóa trong title.

| Category | Definition | Included titles | Common aliases | Exclusion rules | Ambiguous cases |
|---|---|---|---|---|---|
| Backend | Xây dựng service, API và business logic phía server | Backend Engineer, API Developer, Java/.NET Developer | Back-end, Server-side Engineer | Loại Data Engineer, DevOps và full-stack có frontend đáng kể | “Software Engineer” cần đọc trách nhiệm chính |
| Frontend | Xây dựng giao diện web chạy phía client | Frontend Engineer, Web UI Developer | Front-end, FE Developer, React/Vue/Angular Developer | Loại UI/UX designer và full-stack | “Web Developer” có thể là full-stack |
| Full-stack | Chịu trách nhiệm đáng kể cả frontend và backend | Full-stack Engineer, Full Stack Developer | Fullstack, Web Application Developer | Không gán chỉ vì biết thêm một framework phía còn lại | Tỷ trọng công việc không rõ thì ghi chú |
| Mobile | Xây dựng ứng dụng mobile native/cross-platform | Android Developer, iOS Engineer, Flutter Developer | Mobile App Developer, React Native Developer | Loại mobile QA và embedded firmware | “Application Developer” cần platform evidence |
| QA/Testing | Đảm bảo chất lượng, thiết kế/thực thi test | QA Engineer, Test Automation Engineer, Manual Tester | QC, SDET, Tester | Loại security testing và developer chỉ có test duty | SDET gần software engineering; xét mục tiêu vai trò |
| DevOps/Cloud/SRE | Hạ tầng cloud, delivery, reliability và operations automation | DevOps Engineer, Cloud Engineer, SRE, Platform Engineer | Site Reliability, Infrastructure Engineer | Loại sysadmin helpdesk và cloud security chuyên biệt | Platform Engineer có thể là backend platform |
| Cybersecurity | Bảo vệ hệ thống, phát hiện/ứng phó rủi ro và security governance | Security Engineer, SOC Analyst, Penetration Tester | InfoSec, AppSec, Blue Team | Loại generic network/sysadmin và QA | Cloud Security có thể giao DevOps; chọn nhiệm vụ chính |
| Data Analyst | Phân tích dữ liệu để trả lời câu hỏi kinh doanh | Data Analyst, Product Analyst, Marketing Analyst | Reporting Analyst | Loại BI thiên về semantic/report platform và Data Scientist | Business Analyst có SQL chưa đủ để gán Data Analyst |
| Business Intelligence | Xây dashboard, reporting model và BI platform | BI Developer, BI Analyst, Power BI Developer | Business Intelligence Engineer | Loại Data Analyst ad-hoc và Data Engineer pipeline-first | Analytics Engineer có thể BI hoặc Data Engineering |
| Data Engineer | Xây ingestion, transformation, orchestration và data platform | Data Engineer, ETL Developer, Analytics Engineer | Big Data Engineer, Data Platform Engineer | Loại backend service và analyst chỉ viết query | Analytics Engineer phụ thuộc trọng tâm modeling/platform |
| Data Scientist | Thống kê, thử nghiệm và mô hình hóa để tạo insight/prediction | Data Scientist, Decision Scientist | Applied Scientist (data-focused) | Loại ML Engineer production-first và analyst descriptive-only | Applied Scientist có thể AI/ML |
| AI/Machine Learning | Xây, triển khai và vận hành hệ thống ML/AI | ML Engineer, AI Engineer, NLP Engineer, Computer Vision Engineer | Machine Learning Engineer, MLOps Engineer | Loại Data Scientist không production và backend gọi API AI đơn giản | MLOps có thể DevOps; xét ownership model lifecycle |
| Embedded/IoT | Phần mềm gần phần cứng, firmware và thiết bị kết nối | Embedded Engineer, Firmware Developer, IoT Engineer | BSP Engineer, Embedded Software | Loại mobile app và generic C/C++ backend | IoT cloud role có thể backend/cloud |
| ERP | Triển khai, tùy biến và vận hành nền tảng ERP | SAP Consultant, ERP Developer, Dynamics 365 Consultant | Oracle ERP, Odoo Developer | Loại generic enterprise backend không làm ERP | Functional consultant có thể gần Business Analyst |
| Business Analyst | Khai phá yêu cầu, quy trình và cầu nối business–delivery | Business Analyst, System Analyst, IT BA | Requirements Analyst, Functional Analyst | Loại Data Analyst và Product Manager owning roadmap | Product BA/ERP consultant cần xét quyền quyết định |
| Product Management | Sở hữu product strategy, roadmap, discovery và outcome | Product Manager, Product Owner, Technical Product Manager | PM (chỉ khi có evidence), PO | Loại Project Manager và BA chỉ thu thập yêu cầu | Product Owner đôi khi là delivery role |
| Project Management | Lập kế hoạch và điều phối phạm vi, tiến độ, nguồn lực delivery | IT Project Manager, Scrum Master, Delivery Manager | Project Coordinator, Technical PM | Loại Product Manager và engineering manager people-first | Program/Delivery Manager có thể multi-project |
| UI/UX | Nghiên cứu và thiết kế trải nghiệm/giao diện | UX Designer, UI Designer, Product Designer, UX Researcher | UI/UX Designer, Interaction Designer | Loại frontend developer và graphic designer không làm product | Product Designer đôi khi có branding duty |
| IT Support/System Administration | Hỗ trợ người dùng, endpoint, network và vận hành hệ thống nội bộ | IT Support, Helpdesk, System Administrator, Network Administrator | Desktop Support, Sysadmin | Loại DevOps/SRE automation-first và security specialist | Infrastructure Engineer cần xét cloud/automation scope |
| Other/Unclassified | Vai trò IT không khớp hoặc thiếu bằng chứng để gán nhóm trên | Technical Writer, Solution Architect, Database Administrator | Unknown, Other | Không dùng như shortcut khi title đủ evidence | Multi-role không có vai trò chính; architect/DBA có thể cần category mới |

## Quy tắc gán nhãn

1. Đọc title và trách nhiệm; ưu tiên outcome/trách nhiệm chiếm phần lớn hơn stack được liệt kê.
2. Mỗi posting v0.1 nhận một `job_category`. Nếu nhiều vai trò, chọn vai trò chính được tuyển; nếu không xác định, dùng `Other/Unclassified` và ghi chú annotation.
3. Seniority không làm thay đổi category. Manager của một chuyên môn được gán theo chuyên môn nếu trách nhiệm chuyên môn rõ.
4. Alias chỉ là evidence khởi đầu; exclusion rule thắng một keyword match đơn lẻ.
5. Mọi case lặp lại không phù hợp phải được đưa vào taxonomy review, không sửa nhãn ad hoc.
