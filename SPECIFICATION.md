# SPECIFICATION: TELEGRAM ANTIGRAVITY BRIDGE

Tài liệu đặc tả kỹ thuật chi tiết về hệ thống kết nối, đồng bộ và điều khiển từ xa cho Antigravity AI Agent thông qua ứng dụng Telegram.

---

## 1. Yêu cầu Hệ thống (System Requirements)

*   **Ngôn ngữ lập trình:** Python 3.10+
*   **Thư viện bên thứ ba:** Không phụ thuộc (chỉ dùng thư viện chuẩn `urllib`, `json`, `os`, `re`, `time`, `threading`, `subprocess` để tối đa hóa hiệu năng và tránh lỗi cài đặt môi trường).
*   **Môi trường chạy:** Windows OS (tự động kết nối nâng cao) hoặc Fallback đa nền tảng (đọc file cấu hình tĩnh).
*   **Quyền hệ thống:** Đọc/Ghi dữ liệu trong thư mục ứng dụng và AppData của người dùng để truy cập log của IDE.

---

## 2. Đặc tả các Tính năng Core (Core Feature Specifications)

### A. Tự động Kết nối (Auto-Discovery Network)
*   **Cơ chế chính:** Quét danh sách tiến trình đang hoạt động qua PowerShell `Get-CimInstance Win32_Process` để phân tích dòng lệnh CommandLine của `language_server.exe`.
*   **Trích xuất dữ liệu:**
    *   `token`: Dãy UUID bảo mật CSRF (ví dụ: `--csrf-token 99766a9e...`).
    *   `port`: Cổng mạng HTTP mà server đang lắng nghe. Được quét từ CommandLine hoặc đọc ngược tệp log `language_server.log` của VS Code.
*   **Fallback:** Nếu không phát hiện được qua WMI (trên macOS/Linux), bot sẽ nạp cổng tĩnh từ biến môi trường hoặc cổng mặc định của hệ thống.

### B. Cơ chế Phân luồng On-Demand (On-Demand Topic Creation)
Để giải quyết triệt để lỗi tràn số lượng Topics trên các tài khoản Telegram Business hoặc Groups khi có quá nhiều phiên chat cũ trong lịch sử:
*   **Không tạo hàng loạt:** Khi bot khởi động, tuyệt đối không tự động tạo sẵn topic cho các cuộc trò chuyện.
*   **Đồng bộ theo luồng hoạt động:** Vòng lặp Watcher liên tục giám sát tệp nhật ký `transcript.jsonl` của toàn bộ các phiên chat hoạt động trong vòng 3 ngày qua (không giới hạn số lượng).
*   **Kích hoạt On-Demand:** Chỉ khi một phiên chat cụ thể phát sinh bước phản hồi mới từ Agent (`MODEL / PLANNER_RESPONSE`), bot mới tra cứu `topics_map.json`. Nếu chưa tồn tại `thread_id`, bot mới gọi API `createForumTopic` tạo một topic mới cho cuộc trò chuyện đó, đăng ký ID vào bộ nhớ và gửi tin nhắn đi.
*   **Bỏ qua tin nhắn lịch sử:** Khi phát hiện một cuộc trò chuyện mới có hoạt động, mốc đọc tin ban đầu được đặt bằng dòng cuối cùng của log để bỏ qua toàn bộ lịch sử tin cũ, tránh spam tin nhắn về Telegram khi khởi chạy lại bot.

### C. Khử nhiễu Sub-Agent (Sub-Agent filtering)
*   **Mục tiêu:** Chặn hoàn toàn việc tạo topic hoặc gửi tin nhắn rác về Telegram đối với các cuộc hội thoại được tạo tự động bởi các Sub-Agent (như luồng audit học liệu tự động, luồng fix lỗi tự động chạy song song).
*   **Logic nhận diện:** Hàm `is_subagent_conversation(first_message_content)` phân tích tin nhắn đầu tiên của phiên chat. Nếu nội dung chứa các từ khóa đặc trưng của sub-agent (ví dụ: `sau khi hoàn thành hãy nhắn tin AUDIT_COMPLETE/FIX_COMPLETE cho Agent mẹ`, `audit_subagent_prompt.txt`), phiên chat đó sẽ bị đánh dấu là sub-agent và bị loại bỏ hoàn toàn khỏi hàng đợi xử lý.

### D. Tương thích Chat 1-1 Cá nhân (Private Chat Compatibility)
*   **Hỗ trợ đa chế độ:** Hệ thống tương thích hoàn toàn với cả Chat ID nhóm (Supergroup) và Chat ID cá nhân 1-1.
*   **Truyền cờ thread thông minh:** Cờ `message_thread_id` được truyền kèm trong mọi payload của các API gửi tin nhắn (bao gồm tin nhắn văn bản thông thường và tin nhắn chứa link Telegra.ph) nếu `thread_id` khác 0 và hợp lệ, cho phép hiển thị chính xác trong các luồng chat nhỏ của tài khoản Telegram Business.

### E. Đồng bộ hóa Xác thực & Phân quyền (Project ID & Token Authorization Binding)
Để giải quyết lỗi phân quyền `PermissionDenied` do lệch mã dự án giữa CLI nguồn và bối cảnh cuộc hội thoại trên Language Server standalone, hệ thống áp dụng cơ chế:
*   **Dò tìm Daemon động theo Dự án:** Hàm `discover_daemon_for_project(project_path)` quét các tệp daemon local (`ls_<hash>.json`) trong thư mục ứng dụng, đối chiếu đường dẫn dự án với CommandLine và tệp log của từng tiến trình để nạp đúng cổng mạng HTTP và CSRF Token của dự án đó.
*   **Bóc tách Project ID từ SQLite Database:** Bot mở trực tiếp cơ sở dữ liệu local `conversations/<conversation_id>.db` của cuộc hội thoại đích, truy vấn trường `data` dạng blob của bảng `trajectory_metadata_blob` để trích xuất mã UUID Project ID thực tế bằng biểu thức chính quy.
*   **Khử nhiễu bối cảnh thừa kế:** Trước khi chạy CLI, bot xóa sạch toàn bộ các biến môi trường có tiền tố `ANTIGRAVITY_` thừa kế từ terminal cha để tránh xung đột bối cảnh cũ, gán đè trực tiếp Project ID đích vào biến môi trường `ANTIGRAVITY_PROJECT_ID` để thông qua kiểm tra của Language Server local.

---

## 3. Đặc tả API tích hợp (Integration APIs)

### A. Telegram Bot API
Hệ thống gọi trực tiếp các phương thức REST API của Telegram qua phương thức POST (JSON payload):
1.  `getMe`: Xác thực token và lấy thông tin username của Bot.
2.  `getUpdates`: Lấy danh sách tin nhắn mới từ người dùng (sử dụng long-polling).
3.  `sendMessage`: Gửi tin nhắn văn bản (hỗ trợ parse_mode HTML/Markdown và chia nhỏ tin nhắn tự động dưới 2000 ký tự). Luôn giữ cờ `message_thread_id` cho cả link Telegra.ph và tin nhắn chia nhỏ.
4.  `createForumTopic`: Tạo topic mới trong nhóm hoặc tài khoản hỗ trợ.
5.  `editForumTopic`: Đổi tên topic khi tiêu đề cuộc hội thoại thay đổi.

### B. Telegraph API
Sử dụng để xuất bản các tài liệu dài hoặc các định dạng báo cáo phức tạp:
1.  `createAccount`: Tạo tài khoản tác giả tự động dựa trên tên Bot.
2.  `createPage`: Xuất bản tài liệu HTML. Dữ liệu Markdown từ Agent được làm sạch và chuyển đổi thành định dạng cấu trúc DOM Nodes tương thích với Telegraph API trước khi gửi đi.
