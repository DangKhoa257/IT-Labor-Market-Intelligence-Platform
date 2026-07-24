# Skill Taxonomy — Draft Seed

Taxonomy này là seed nhỏ cho rule-based extraction và annotation Phase 0, không nhằm bao phủ hàng nghìn kỹ năng. Canonical name dùng trong `skills_normalized`; alias chỉ dùng matching, so khớp không phân biệt hoa thường khi phù hợp. Mỗi match phải xét ngữ cảnh và false-positive note.

| Canonical name | Aliases | Category | Trường hợp dễ false positive |
|---|---|---|---|
| Python | python3, py | Programming languages | “Python” có thể chỉ khóa học; `py` trong extension/văn xuôi |
| Java | Java SE, JDK | Programming languages | JavaScript không phải Java; tên đảo Java |
| JavaScript | JS, ECMAScript | Programming languages | JSON/JS trong tên file hoặc mã tracking |
| TypeScript | TS | Programming languages | `TS` có nhiều nghĩa ngoài kỹ thuật |
| C# | C Sharp, dotnet language | Programming languages | Ký hiệu C# trong văn bản lỗi encoding |
| Go | Golang | Programming languages | Từ tiếng Anh “go” không phải kỹ năng |
| .NET | ASP.NET Core, dotnet | Backend frameworks | “net” trong network/domain |
| Spring Boot | Spring, Spring Framework | Backend frameworks | Mùa “spring”; chỉ match Spring trong ngữ cảnh Java |
| Django | django framework | Backend frameworks | Tên riêng/dự án không nói kỹ năng |
| Node.js | NodeJS, Node JS | Backend frameworks | “node” trong graph/infrastructure |
| React | React.js, ReactJS | Frontend frameworks | Động từ tiếng Anh “react” |
| Angular | AngularJS, Angular 2+ | Frontend frameworks | Tính từ “angular”; AngularJS khác version lớn |
| Vue.js | Vue, VueJS | Frontend frameworks | Vue là tên sản phẩm/tên riêng |
| Flutter | Flutter SDK | Mobile | Động từ/tên sản phẩm không liên quan mobile |
| Android | Android SDK | Mobile | Chỉ nêu thiết bị người dùng, không phải yêu cầu kỹ năng |
| iOS | iOS SDK, SwiftUI | Mobile | Chỉ nêu app hỗ trợ iOS; SwiftUI cần map có chủ đích |
| PostgreSQL | Postgres, PGSQL | Databases | `PG` đơn lẻ không đủ evidence |
| MySQL | My SQL | Databases | Cụm từ tự nhiên “my SQL” |
| MongoDB | Mongo | Databases | Mongo là project/name khác |
| Redis | Redis cache | Databases | Tên service nội bộ trùng alias |
| Amazon Web Services | AWS | Cloud | AWS là acronym trong tổ chức khác |
| Microsoft Azure | Azure | Cloud | Màu azure/tên sản phẩm khác |
| Google Cloud | GCP, Google Cloud Platform | Cloud | Google APIs không đồng nghĩa GCP skill |
| Docker | containerization with Docker | DevOps | Chỉ ghi “Docker image provided” không phải yêu cầu |
| Kubernetes | K8s, Kube | DevOps | Tên cluster/project không phải kỹ năng ứng viên |
| Terraform | HashiCorp Terraform | DevOps | Tên game/project “terraform” |
| Apache Spark | Spark, PySpark | Data Engineering | “spark” là từ thường hoặc Apache Spark service only |
| Apache Kafka | Kafka | Data Engineering | Tác giả Kafka/tên project nội bộ |
| Apache Airflow | Airflow | Data Engineering | Luồng không khí trong mô tả phần cứng |
| Power BI | PowerBI | Data Analytics/BI | “power” và “BI” xuất hiện tách rời |
| Tableau | Tableau Desktop | Data Analytics/BI | Tableau theo nghĩa bảng/brand khác |
| Microsoft Excel | Excel, MS Excel | Data Analytics/BI | Động từ tiếng Anh “excel” |
| scikit-learn | sklearn, scikit learn | AI/ML | Import/package mention trong log, không phải requirement |
| PyTorch | torch | AI/ML | `torch` là từ thường hoặc package khác |
| TensorFlow | TF | AI/ML | `TF` acronym rất mơ hồ |
| Selenium | Selenium WebDriver | Testing | Nguyên tố selenium hoặc dependency incidental |
| Playwright | Microsoft Playwright | Testing | Nghề “playwright” trong văn cảnh phi IT |
| pytest | py.test | Testing | Tên file/config không thể hiện yêu cầu kỹ năng |
| OWASP | OWASP Top 10 | Cybersecurity | Link chính sách chung không phải skill requirement |
| SIEM | Security Information and Event Management | Cybersecurity | Acronym trùng trong domain khác |
| Linux | GNU/Linux, Ubuntu, RHEL | Operating systems | Server chạy Linux nhưng vai trò không yêu cầu thao tác Linux |
| Windows Server | Windows administration, Win Server | Operating systems | Chỉ hỗ trợ người dùng Windows |
| Git | GitHub workflow, GitLab workflow | Tools/platforms | GitHub/GitLab product mention không luôn đồng nghĩa Git proficiency |
| Jira | Atlassian Jira | Tools/platforms | Chỉ nêu nơi nhận ticket/onboarding |
| Communication | communication skills, giao tiếp | Soft skills | Boilerplate chung không mang tính phân biệt |
| Problem solving | problem-solving, giải quyết vấn đề | Soft skills | Boilerplate hoặc mô tả văn hóa công ty |
| Teamwork | collaboration, làm việc nhóm | Soft skills | Mô tả môi trường “team” không phải requirement |
| English | tiếng Anh, English language | Human languages | Tên tài liệu/sản phẩm bằng tiếng Anh; cần requirement context |
| Japanese | tiếng Nhật, Japanese, JLPT | Human languages | Khách hàng Nhật không tự động nghĩa là yêu cầu tiếng Nhật |
| Korean | tiếng Hàn, Korean, TOPIK | Human languages | Thị trường/khách hàng Hàn không tự động là skill |

## Quy tắc quản trị

- Một alias chỉ map tới một canonical skill trong cùng taxonomy version; alias mơ hồ cần context rule.
- Không suy ra skill chỉ từ chức danh công ty, URL, tracking tag hoặc mô tả sản phẩm.
- Lưu mention nguyên văn trong `skills_raw`; dedupe canonical name trong `skills_normalized`.
- Human language tách khỏi programming language. Cloud service cụ thể không tự động suy ra toàn bộ cloud platform.
- Thêm skill mới khi xuất hiện lặp lại trong mẫu thật và có definition/alias/false-positive test.
