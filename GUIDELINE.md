# HƯỚNG DẪN CẤU HÌNH & VẬN HÀNH: TELEGRAM ANTIGRAVITY BRIDGE

Tài liệu hướng dẫn từng bước thiết lập, cấu hình bảo mật và vận hành hệ thống kết nối Telegram với Antigravity AI Agent local.

---

## 1. Chuẩn bị phía Telegram (Telegram Setup)

### Bước 1: Tạo Telegram Bot qua BotFather
1. Mở Telegram, tìm kiếm **`@BotFather`** và nhấn **Start**.
2. Gửi lệnh `/newbot` để khởi tạo bot mới.
3. Nhập tên hiển thị và username cho bot (phải kết thúc bằng chữ `_bot` hoặc `bot`, ví dụ: `MyAntigravityBridge_bot`).
4. BotFather sẽ trả về một chuỗi **HTTP API Access Token** (Bot Token). Lưu lại token này (sẽ dùng cấu hình vào `TELEGRAM_BOT_TOKEN`).

### Bước 2: Thiết lập Chat ID & Quyền ghi Topic
#### Lựa chọn A: Sử dụng Group Chat (Hỗ trợ nhiều thành viên)
1. Tạo một Group Chat mới trên Telegram và thêm Bot vừa tạo vào Group.
2. Thăng cấp cho Bot làm **Quản trị viên (Administrator)** và cấp quyền **Quản lý chủ đề (Manage Topics)**.
3. Kích hoạt tính năng **Topics (Chủ đề)** trong phần cài đặt của Group.
4. Lấy Chat ID của Group bằng cách gửi một tin nhắn bất kỳ vào nhóm, sau đó truy cập đường dẫn trình duyệt:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   Tìm trường `"chat":{"id": -XXXXXXXXXX}`. *Lưu ý: ID của nhóm luôn là số âm.*

#### Lựa chọn B: Sử dụng Chat cá nhân 1-1 hỗ trợ Topics (Dành cho Telegram Business)
1. Nếu tài khoản cá nhân của bạn có đăng ký **Telegram Business** và bật tính năng phân luồng chat (Topics/Threads) cá nhân.
2. Bắt đầu cuộc trò chuyện với Bot bằng cách nhấn **Start** (`/start`).
3. Lấy Chat ID cá nhân của bạn bằng cách truy cập:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   Tìm trường `"from":{"id": XXXXXXXXX}` (thường là số dương, ví dụ của bạn là `729753144`).

---

## 2. Thiết lập Môi trường Local (Local Configuration)

### Bước 1: Chuẩn bị tệp cấu hình `.env`
Sao chép tệp `.env.example` thành `.env` và điền đầy đủ các thông số:
```env
TELEGRAM_BOT_TOKEN=8672413154:AAFap1T27GrSN8XKOBt-HyUs... # Điền Bot Token từ BotFather
TELEGRAM_CHAT_ID=729753144                             # Điền Chat ID cá nhân hoặc nhóm
TELEGRAPH_TOKEN=                                       # Để trống (Bot sẽ tự tạo khi khởi chạy)
AFH_MODE=FALSE                                         # Chế độ Away From Home (TRUE/FALSE)
INTERVAL_MODE=FAST                                     # Nhịp quét log (FAST/MEDIUM/SLOW)
AUTO_SWITCH=TRUE                                       # Tự động đồng bộ bối cảnh theo IDE
```

### Bước 2: Thiết lập tệp ánh xạ `topics_map.json`
Khởi tạo tệp **`topics_map.json`** với cấu trúc rỗng `{}` ở lần chạy đầu tiên. Bot sẽ tự động cập nhật ID của các topic mới được tạo vào đây.

---

## 3. Cách vận hành & Chạy ngầm (Daemon Execution)

Hệ thống được viết hoàn toàn bằng thư viện chuẩn của Python, không yêu cầu cài đặt thêm thư viện ngoài (zero-dependencies).

### Cách 1: Chạy trực tiếp trên Terminal để kiểm tra (Debug Mode)
Chạy lệnh trực tiếp trong thư mục dự án:
```cmd
python telegram_antigravity_bridge.py
```
*Mẹo:* Quan sát các log in ra màn hình để xác nhận bot kết nối thành công tới Telegram API và Language Server local.

### Cách 2: Khởi chạy chạy ngầm (Background Daemon) trên Windows
Để chạy bot dưới dạng tiến trình ngầm không hiển thị cửa sổ Command Prompt và tự động ghi log ra tệp tin:

Chạy lệnh PowerShell sau từ thư mục chứa tệp script:
```powershell
Start-Process python -ArgumentList "-u telegram_antigravity_bridge.py" -RedirectStandardOutput "bridge.log" -RedirectStandardError "bridge.log" -WindowStyle Hidden
```
*Giải thích:*
*   `-u`: Chạy Python ở chế độ Unbuffered để ghi log trực tiếp xuống đĩa ngay khi có sự kiện, không bị giữ trong hàng đợi đệm.
*   `-RedirectStandardOutput` & `-RedirectStandardError`: Gộp toàn bộ log hoạt động và log lỗi vào tệp `bridge.log` để giám sát.
*   `-WindowStyle Hidden`: Ẩn hoàn toàn cửa sổ dòng lệnh để tránh vướng màn hình làm việc.

---

## 4. Giám sát & Quản lý (Monitoring)

*   **Xem Log thời gian thực (Windows PowerShell):**
    ```powershell
    Get-Content -Path "bridge.log" -Wait -Tail 20
    ```
*   **Dừng tiến trình chạy ngầm:**
    Tìm và tắt tiến trình python đang chạy file bridge:
    ```powershell
    Get-CimInstance Win32_Process -Filter "name='python.exe' and CommandLine like '%telegram_antigravity_bridge%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    ```

---

## 5. Các Lệnh Điều khiển qua Telegram (Telegram Commands)

Khi chat trực tiếp với Bot trên Telegram, bạn có thể sử dụng các lệnh sau:
*   `/help` : Hiển thị bảng hướng dẫn điều khiển.
*   `/list` : Liệt kê tất cả các phiên chat đang hoạt động trong IDE kèm số thứ tự.
*   `/switch <số_thứ_tự>` : Chuyển đổi tiêu điểm giám sát của IDE sang phiên chat chỉ định.
*   `/log <số_tin>` : Đọc nhanh `<số_tin>` tin nhắn gần nhất của phiên chat hiện tại.
*   `/autoswitch` : Bật/Tắt chế độ tự động bám theo phiên chat đang gõ trên IDE.
