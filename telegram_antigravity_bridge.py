# -*- coding: utf-8 -*-
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import subprocess
import threading
import re

import sys
sys.stdout.reconfigure(encoding='utf-8')

# ==================== CẤU HÌNH HỆ THỐNG ====================
BOT_TOKEN = ""
CONVERSATION_ID = ""

DAEMON_DIR = r"C:\Users\user\.gemini\antigravity\daemon"
CONVERSATIONS_DIR = r"C:\Users\user\.gemini\antigravity\conversations"
BRAIN_DIR = r"C:\Users\user\.gemini\antigravity\brain"
AGENT_API_PATH = r"C:\Users\user\.gemini\antigravity\bin\agentapi.bat"

# Đường dẫn tệp cấu hình và tệp log động
LIBRARY_PATH = rf"{BRAIN_DIR}\0a2c9dc7-cfc0-4efe-a70c-43e854bd37f5\scratch\conversation_library.json"
TRANSCRIPT_PATH = rf"{BRAIN_DIR}\{CONVERSATION_ID}\.system_generated\logs\transcript.jsonl"
# ==========================================================

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
TOPICS_MAP_PATH = os.path.join(os.path.dirname(__file__), "topics_map.json")

topics_map = {}
TELEGRAPH_TOKEN = ""
afh_mode = "OFF"
interval_mode = "SLOW"
auto_switch = "OFF"

def load_env():
    """Nạp các biến môi trường từ tệp .env"""
    global BOT_TOKEN, chat_id, TELEGRAPH_TOKEN, afh_mode, interval_mode, auto_switch
    if not os.path.exists(ENV_PATH):
        print(f"[System Warning] Không tìm thấy file .env tại {ENV_PATH}")
        return
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key == "TELEGRAM_BOT_TOKEN":
                        BOT_TOKEN = val
                        print(f"[System] Đã nạp BOT_TOKEN: {BOT_TOKEN[:10]}...")
                    elif key == "TELEGRAM_CHAT_ID":
                        chat_id = val
                        print(f"[System] Đã nạp Chat ID: {chat_id}")
                    elif key == "TELEGRAPH_TOKEN":
                        TELEGRAPH_TOKEN = val
                        if TELEGRAPH_TOKEN:
                            print(f"[System] Đã nạp TELEGRAPH_TOKEN.")
                    elif key == "AFH_MODE":
                        afh_mode = val
                    elif key == "INTERVAL_MODE":
                        interval_mode = val
                    elif key == "AUTO_SWITCH":
                        auto_switch = val
        print("[System] Nạp file .env thành công.")
    except Exception as e:
        print(f"[System Error] Lỗi nạp cấu hình .env: {e}")

def save_env():
    """Lưu lại các thay đổi vào file .env (ví dụ khi cập nhật TELEGRAPH_TOKEN)"""
    global chat_id, TELEGRAPH_TOKEN
    if not os.path.exists(ENV_PATH):
        return
    try:
        lines = []
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("TELEGRAPH_TOKEN="):
                new_lines.append(f"TELEGRAPH_TOKEN={TELEGRAPH_TOKEN}\n")
            elif stripped.startswith("TELEGRAM_CHAT_ID="):
                new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
            else:
                new_lines.append(line)
                
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print("[System] Đã cập nhật file .env")
    except Exception as e:
        print(f"[System Error] Lỗi lưu cấu hình .env: {e}")

def load_topics_map():
    """Nạp topics map động từ file JSON riêng biệt"""
    global topics_map
    if os.path.exists(TOPICS_MAP_PATH):
        try:
            with open(TOPICS_MAP_PATH, "r", encoding="utf-8") as f:
                topics_map = json.load(f)
                print(f"[System] Đã nạp {len(topics_map)} topic từ topics_map.json")
        except Exception as e:
            print(f"[System Error] Lỗi nạp topics_map.json: {e}")
            topics_map = {}

def save_topics_map():
    """Lưu topics map động vào file JSON riêng biệt"""
    global topics_map
    try:
        with open(TOPICS_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(topics_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[System Error] Lỗi lưu topics_map.json: {e}")

def is_auto_switch_enabled():
    """Kiểm tra xem chế độ tự động switch hội thoại có đang bật hay không"""
    global auto_switch
    return auto_switch == "ON"

def escape_html(text):
    """Escape các ký tự HTML cơ bản để an toàn khi gửi tin nhắn với parse_mode='HTML'"""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")




# Biến trạng thái toàn cục
chat_id = None
conversation_last_steps = {}
active_ls_address = None
active_csrf_token = None
listed_ids = []  # Bộ nhớ đệm danh sách ID để switch theo số thứ tự (1, 2, 3...)

def get_telegram_url(method):
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

def make_telegram_request(method, data=None):
    url = get_telegram_url(method)
    try:
        if data:
            data_bytes = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=data_bytes, 
                headers={'Content-Type': 'application/json'}
            )
        else:
            req = urllib.request.Request(url)
            
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[Telegram Error] Lỗi kết nối API Telegram ({method}) - HTTP {e.code}: {e.reason}\nResponse Body: {error_body}")
        try:
            return json.loads(error_body)
        except Exception:
            return None
    except Exception as e:
        print(f"[Telegram Error] Không thể kết nối API Telegram ({method}): {e}")
        return None

def create_telegram_forum_topic(chat_id, name):
    """Tạo một topic mới trong Telegram Supergroup, hỗ trợ fallback an toàn"""
    print(f"[Telegram] Đang cố gắng tạo topic: '{name[:30]}...'")
    res = make_telegram_request("createForumTopic", {
        "chat_id": chat_id,
        "name": name[:120]  # Giới hạn an toàn của Telegram
    })
    if res and res.get("ok"):
        thread_id = res["result"]["message_thread_id"]
        print(f"[Telegram] Tạo topic thành công. Thread ID: {thread_id}")
        return thread_id
    else:
        print("[Telegram Warning] Không thể tạo topic. Có thể Chat ID là chat 1-1 thường hoặc bot không có quyền quản lý topic.")
        return None

def edit_telegram_forum_topic(chat_id, thread_id, new_name):
    """Gọi API editForumTopic của Telegram để đổi tên topic"""
    print(f"[Telegram] Đang đổi tên topic {thread_id} thành: '{new_name[:30]}...'")
    res = make_telegram_request("editForumTopic", {
        "chat_id": chat_id,
        "message_thread_id": thread_id,
        "name": new_name[:120]
    })
    return res and res.get("ok")

def get_or_create_telegraph_token():
    """Tự động đăng ký và lấy token Telegra.ph nếu chưa có"""
    global TELEGRAPH_TOKEN
    if TELEGRAPH_TOKEN:
        return TELEGRAPH_TOKEN
        
    url = "https://api.telegra.ph/createAccount?short_name=AntigravityBot&author_name=Antigravity"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode('utf-8'))
            if res and res.get("ok"):
                TELEGRAPH_TOKEN = res["result"]["access_token"]
                print(f"[Telegraph] Đăng ký tài khoản thành công! Token: {TELEGRAPH_TOKEN[:10]}...")
                save_env()
                return TELEGRAPH_TOKEN
    except Exception as e:
        print(f"[Telegraph Error] Không thể đăng ký tài khoản Telegra.ph: {e}")
    return None

def parse_inline(text):
    """Phân tích các định dạng inline Markdown và chuẩn hóa Unicode NFC để sửa lỗi font tiếng Việt"""
    import unicodedata
    if not text:
        return []
    
    # Chuẩn hóa Unicode NFC để tránh lỗi tách nguyên âm mang dấu của Telegraph
    text = unicodedata.normalize('NFC', text)
    
    # Regex nhận diện: [link](url), **in đậm**, *in nghiêng*, `inline code`
    pattern = re.compile(r'(\*\*.*?\*\*|\*.*?\*|`.*?`|\[.*?\]\(.*?\))')
    parts = pattern.split(text)
    
    children = []
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            children.append({"tag": "strong", "children": [part[2:-2]]})
        elif part.startswith("*") and part.endswith("*"):
            children.append({"tag": "em", "children": [part[1:-1]]})
        elif part.startswith("`") and part.endswith("`"):
            children.append({"tag": "code", "children": [part[1:-1]]})
        elif part.startswith("[") and "](" in part and part.endswith(")"):
            link_match = re.match(r'^\[(.*?)\]\((.*?)\)$', part)
            if link_match:
                lbl, url = link_match.groups()
                children.append({"tag": "a", "attrs": {"href": url}, "children": [lbl]})
            else:
                children.append(part)
        else:
            children.append(part)
    return children if children else [text]

def join_wrapped_lines(md_text):
    """Gộp các dòng bị ngắt dòng cứng (hard wrap) của câu hoặc link để hiển thị liền mạch trên Telegraph"""
    lines = md_text.split("\n")
    joined_lines = []
    
    for line in lines:
        if not joined_lines:
            joined_lines.append(line)
            continue
            
        prev_line = joined_lines[-1]
        stripped_prev = prev_line.strip()
        stripped_curr = line.strip()
        
        is_prev_special = (
            stripped_prev.startswith("#") or 
            stripped_prev.startswith("- ") or 
            stripped_prev.startswith("* ") or 
            stripped_prev.startswith("• ") or 
            stripped_prev.startswith("```") or 
            stripped_prev.startswith(">") or
            not stripped_prev
        )
        
        is_curr_special = (
            stripped_curr.startswith("#") or 
            stripped_curr.startswith("- ") or 
            stripped_curr.startswith("* ") or 
            stripped_curr.startswith("• ") or 
            stripped_curr.startswith("```") or 
            stripped_curr.startswith(">") or
            not stripped_curr
        )
        
        # Đếm các ngoặc tròn và vuông chưa đóng
        open_bracket = prev_line.count("[") - prev_line.count("]")
        open_paren = prev_line.count("(") - prev_line.count(")")
        
        link_broken = (open_bracket > 0) or (open_paren > 0)
        
        should_join = False
        if link_broken:
            should_join = True
        elif not is_prev_special and not is_curr_special:
            last_char = stripped_prev[-1] if stripped_prev else ""
            if last_char not in [".", "!", "?", ":", ";", "`", ")"]:
                should_join = True
                
        if should_join:
            need_space = True
            if link_broken:
                last_char = stripped_prev[-1] if stripped_prev else ""
                first_char = stripped_curr[0] if stripped_curr else ""
                if last_char in ["[", "(", "/", "-", "@", ":"] or first_char in ["]", ")", "/", "-", ".", "?", "="]:
                    need_space = False
            
            if need_space:
                joined_lines[-1] = prev_line + " " + line
            else:
                joined_lines[-1] = prev_line + line
        else:
            joined_lines.append(line)
            
    return "\n".join(joined_lines)

def markdown_to_telegraph_nodes(md_text):
    """Chuyển đổi văn bản Markdown cơ bản sang mảng Node của Telegra.ph API"""
    nodes = []
    lines = md_text.split("\n")
    
    in_code_block = False
    code_content = []
    
    for line in lines:
        stripped = line.strip()
        
        # 1. Xử lý code block
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                nodes.append({
                    "tag": "pre",
                    "children": [{"tag": "code", "children": ["\n".join(code_content)]}]
                })
                code_content = []
            else:
                in_code_block = True
            continue
            
        if in_code_block:
            code_content.append(line)
            continue
            
        # 2. Xử lý tiêu đề H1, H2, H3 -> h3, h4 (Telegraph hỗ trợ h3, h4)
        if stripped.startswith("# "):
            nodes.append({"tag": "h3", "children": parse_inline(stripped[2:])})
        elif stripped.startswith("## "):
            nodes.append({"tag": "h4", "children": parse_inline(stripped[3:])})
        elif stripped.startswith("### "):
            nodes.append({"tag": "h4", "children": parse_inline(stripped[4:])})
            
        # 3. Bullet list
        elif stripped.startswith("* ") or stripped.startswith("- "):
            nodes.append({"tag": "li", "children": parse_inline(stripped[2:])})
        elif stripped.startswith("• "):
            nodes.append({"tag": "li", "children": parse_inline(stripped[2:])})
            
        # 4. Dòng trống
        elif not stripped:
            continue
            
        # 5. Đoạn văn thường
        else:
            nodes.append({"tag": "p", "children": parse_inline(line)})
            
    return nodes

def publish_to_telegraph(title, md_content):
    """Tạo trang mới trên Telegra.ph và trả về link URL"""
    token = get_or_create_telegraph_token()
    if not token:
        return None
        
    nodes = markdown_to_telegraph_nodes(join_wrapped_lines(md_content))
    url = "https://api.telegra.ph/createPage"
    
    payload = {
        "access_token": token,
        "title": title[:120],
        "author_name": "Antigravity Bot",
        "content": json.dumps(nodes),
        "return_content": False
    }
    
    try:
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data_bytes, 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            res = json.loads(response.read().decode('utf-8'))
            if res and res.get("ok"):
                page_url = res["result"]["url"]
                print(f"[Telegraph] Đã xuất bản thành công: {page_url}")
                return page_url
            else:
                print(f"[Telegraph Error] API trả về lỗi: {res}")
    except Exception as e:
        print(f"[Telegraph Error] Lỗi gọi API createPage: {e}")
    return None

import socket

def is_port_open(host, port):
    """Kiểm tra xem cổng mạng có đang hoạt động hay không"""
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except Exception:
        return False

def discover_active_daemon():
    """Tự động quét cấu hình LS qua biến môi trường, tệp daemon, log tệp tin và tiến trình hệ điều hành"""
    global active_ls_address, active_csrf_token
    
    # 1. Ưu tiên biến môi trường (nếu chạy từ VS Code terminal tích hợp)
    env_address = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    env_token = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if env_address and env_token:
        host, port = env_address.split(":")
        if is_port_open(host, port):
            active_ls_address = env_address
            active_csrf_token = env_token
            print(f"[System] Sử dụng cấu hình từ biến môi trường: {active_ls_address}")
            return True

    # 2. Quét thư mục daemon
    if os.path.exists(DAEMON_DIR):
        json_files = []
        for f in os.listdir(DAEMON_DIR):
            if f.endswith(".json"):
                path = os.path.join(DAEMON_DIR, f)
                json_files.append((path, os.path.getmtime(path)))
        json_files.sort(key=lambda x: x[1], reverse=True)
        for path, _ in json_files:
            try:
                with open(path, "r") as file:
                    data = json.load(file)
                    port = data['httpPort']
                    token = data['csrfToken']
                    if is_port_open("localhost", port):
                        active_ls_address = f"localhost:{port}"
                        active_csrf_token = token
                        print(f"[System] Tự động phát hiện qua daemon file: Port={port}, Token={active_csrf_token[:8]}...")
                        return True
            except Exception:
                pass

    # 3. Quét dòng lệnh tiến trình Windows để lấy CSRF token
    found_token = None
    try:
        import subprocess
        # Chạy powershell ẩn để lấy CommandLine
        powershell_cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"name=\'language_server.exe\'\\" | Select-Object -ExpandProperty CommandLine"'
        proc = subprocess.run(powershell_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        output = proc.stdout.strip()
        if output:
            token_match = re.search(r"--csrf_token\s+([^\s]+)", output)
            if token_match:
                found_token = token_match.group(1).strip()
                print(f"[System] Quét tiến trình tìm thấy CSRF Token: {found_token[:8]}...")
    except Exception as e:
        print(f"[System Warning] Lỗi quét CommandLine tiến trình: {e}")

    # 4. Quét tệp log để tìm cổng mạng HTTP
    found_port = None
    log_dirs = [
        os.path.expandvars(r"%APPDATA%\antigravity\logs"),
        os.path.expandvars(r"%APPDATA%\antigravity-dev\logs"),
        os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity\logs")
    ]
    for log_dir in log_dirs:
        log_path = os.path.join(log_dir, "language_server.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    match = re.search(r"listening on.*port at (\d+) for HTTP\b", line, re.IGNORECASE)
                    if match:
                        found_port = match.group(1)
                        print(f"[System] Tìm thấy cổng HTTP từ file log {os.path.basename(log_path)}: {found_port}")
                        break
                if found_port:
                    break
            except Exception:
                pass

    if found_token and found_port:
        if is_port_open("localhost", found_port):
            active_ls_address = f"localhost:{found_port}"
            active_csrf_token = found_token
            print(f"[System] Tự động kết nối thành công qua Process/Log: {active_ls_address}")
            return True

    # 5. Cổng dự phòng tĩnh cuối cùng
    fallback_port = 55210
    fallback_token = "38792493-79e1-4f15-abef-005ad5e55123"
    if is_port_open("localhost", fallback_port):
        active_ls_address = f"localhost:{fallback_port}"
        active_csrf_token = fallback_token
        print(f"[System] Sử dụng cổng dự phòng tĩnh mặc định: {active_ls_address}")
        return True
        
    print("[Error] Không tìm thấy bất kỳ cổng Language Server nào đang hoạt động!")
    return False

def discover_active_conversation(target_cid=None, target_topic=None):
    """Tự động quét các cuộc hội thoại chính trên đĩa, đồng bộ hóa và cập nhật tên Telegram Forum Topics"""
    global chat_id, topics_map
    if not chat_id:
        return False
        
    updated = False
    
    if target_cid and target_topic:
        # Chế độ On-demand: chỉ đồng bộ 1 hội thoại cụ thể
        items = [(target_cid, target_topic)]
    else:
        lib = load_conversation_library()
        items = lib.items()
    
    for cid, topic in items:
        thread_info = topics_map.get(cid)
        
        # 1. Trường hợp chưa tạo topic
        if thread_info is None:
            thread_id = create_telegram_forum_topic(chat_id, topic)
            if thread_id is not None:
                topics_map[cid] = {
                    "thread_id": thread_id,
                    "title": topic
                }
                updated = True
                
                welcome_msg = (
                    f"📂 <b>Chào mừng bạn đến với hội thoại mới!</b>\n"
                    f"• ID: <code>{cid}</code>\n"
                    f"• Chủ đề: <b>{escape_html(topic)}</b>\n\n"
                    f"<i>Mọi tin nhắn của bạn trong topic này sẽ được gửi trực tiếp cho Agent của hội thoại này.</i>"
                )
                payload = {
                    "chat_id": chat_id,
                    "text": welcome_msg,
                    "parse_mode": "HTML"
                }
                if thread_id != 0:
                    payload["message_thread_id"] = thread_id
                make_telegram_request("sendMessage", payload)
            else:
                # Đăng ký thất bại (fallback chat 1-1 cá nhân)
                topics_map[cid] = {
                    "thread_id": 0,
                    "title": topic
                }
                updated = True
        else:
            # Chuẩn hóa nếu cấu hình cũ lưu dạng integer đơn giản
            if isinstance(thread_info, int):
                thread_info = {"thread_id": thread_info, "title": ""}
                topics_map[cid] = thread_info
                updated = True
                
            thread_id = thread_info.get("thread_id")
            old_title = thread_info.get("title", "")
            
            # 2. Trường hợp tiêu đề thay đổi (ví dụ từ fallback thô sang tiêu đề Markdown đẹp)
            if thread_id is not None and topic != old_title:
                if edit_telegram_forum_topic(chat_id, thread_id, topic):
                    topics_map[cid]["title"] = topic
                    updated = True
                    
                    rename_msg = f"⚙️ <b>Hội thoại đã được đổi tên:</b>\n• Tên mới: <b>{escape_html(topic)}</b>"
                    payload = {
                        "chat_id": chat_id,
                        "text": rename_msg,
                        "parse_mode": "HTML"
                    }
                    if thread_id != 0:
                        payload["message_thread_id"] = thread_id
                    make_telegram_request("sendMessage", payload)
                
    if updated:
        save_topics_map()
        return True
    return False

def switch_conversation_context(new_id, silent=False):
    """Chuyển đổi bối cảnh cuộc hội thoại đang theo dõi"""
    global CONVERSATION_ID, TRANSCRIPT_PATH, topics_map
    CONVERSATION_ID = new_id
    TRANSCRIPT_PATH = rf"{BRAIN_DIR}\{CONVERSATION_ID}\.system_generated\logs\transcript.jsonl"
    
    # Cập nhật hoặc khởi tạo mốc đọc log cho hội thoại này
    update_log_anchor_for_conversation(new_id)
    
    # Load thư viện để lấy chủ đề hiển thị
    lib = load_conversation_library()
    topic = lib.get(new_id, "Không có tiêu đề")
    topic_safe = escape_html(topic)
    
    msg = f"🔄 <b>Đã chuyển sang hội thoại:</b>\n• ID: <code>{CONVERSATION_ID}</code>\n• Chủ đề: <b>{topic_safe}</b>"
    print(f"[System] Switch context: {CONVERSATION_ID} ({topic})")
    
    # Tra cứu thread_id tương ứng
    tid = topics_map.get(new_id)
    thread_id = tid.get("thread_id") if isinstance(tid, dict) else tid
    
    if not silent and chat_id:
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }
        if thread_id is not None and thread_id != 0:
            payload["message_thread_id"] = thread_id
            
        make_telegram_request("sendMessage", payload)

def clean_topic_title(content):
    """Làm sạch nội dung tin nhắn đầu tiên để dùng làm tiêu đề topic Telegram"""
    if not content:
        return "Cuộc hội thoại chưa đặt tên"
        
    # 1. Trích xuất nội dung bên trong <USER_REQUEST>...</USER_REQUEST> nếu có
    user_req_match = re.search(r'<USER_REQUEST>(.*?)</USER_REQUEST>', content, re.DOTALL)
    if user_req_match:
        content = user_req_match.group(1).strip()
    else:
        # Nếu không có thẻ đóng, ta loại bỏ thẻ mở <USER_REQUEST>
        content = re.sub(r'<USER_REQUEST>', '', content)
        content = re.sub(r'</USER_REQUEST>', '', content)
        
    # 2. Loại bỏ các thẻ XML/HTML khác
    content = re.sub(r'<[^>]+>', '', content)
    
    # 3. Loại bỏ các đoạn văn boilerplate hệ thống phổ biến ở đầu
    content = re.sub(r'(?i)Sprint-centric:.*', '', content)
    content = re.sub(r'(?i)Cần phân loại.*', '', content)
    content = re.sub(r'(?i)Nhiệm vụ của bạn là.*', '', content)
    
    # 4. Làm sạch khoảng trắng thừa
    content = content.replace('\n', ' ').strip()
    content = re.sub(r'\s+', ' ', content)
    
    # 5. Cắt ngắn và định dạng
    if len(content) > 60:
        return content[:60] + "..."
    elif content:
        return content
    return "Cuộc hội thoại chưa đặt tên"

def is_subagent_conversation(content):
    """Kiểm tra xem nội dung cuộc hội thoại có phải do sub-agent tự động tạo ra hay không"""
    if not content:
        return False
    content_lower = content.lower()
    indicators = [
        "audit_subagent_prompt",
        "fix_subagent_prompt",
        "audit_complete",
        "fix_complete",
        "cho agent mẹ",
        "cho agent cha",
        "cho agent mổ",
        "cho agent 1",
        "hãy thực hiện kiểm định chất lượng",
        "hãy thực hiện tối ưu hóa",
        "hãy thực hiện số hóa ảnh chụp",
        "hãy thực hiện sửa đổi học liệu",
        "quá trình kiểm định chất lượng học liệu"
    ]
    for ind in indicators:
        if ind in content_lower:
            return True
    return False

def extract_markdown_title(cid):
    """Quét các file markdown trong thư mục brain để lấy tiêu đề H1 chính thức"""
    folder_path = os.path.join(BRAIN_DIR, cid)
    if not os.path.exists(folder_path):
        return None
        
    target_files = ["implementation_plan.md", "walkthrough.md", "task.md"]
    for file_name in target_files:
        file_path = os.path.join(folder_path, file_name)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("# "):
                            title = line[2:].strip()
                            title = re.sub(r'^\[Goal Description\]\s*', '', title)
                            title = re.sub(r'^WALKTHROUGH:\s*', '', title, flags=re.IGNORECASE)
                            title = re.sub(r'^Kế hoạch triển khai:\s*', '', title, flags=re.IGNORECASE)
                            if title:
                                return title
            except Exception:
                pass
    return None

def load_conversation_library():
    """Tải hoặc tự động biên dịch thư viện hội thoại từ thư mục brain, giới hạn tối đa 3 cuộc hội thoại gần đây nhất"""
    library = {}
    if os.path.exists(LIBRARY_PATH):
        try:
            with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
                library = json.load(f)
        except Exception:
            pass
            
    updated = False
    valid_sessions = [] # Lưu các tuple: (cid, mtime, log_path, first_content)
    
    if os.path.exists(BRAIN_DIR):
        for cid in os.listdir(BRAIN_DIR):
            sys_gen_path = os.path.join(BRAIN_DIR, cid, ".system_generated")
            if os.path.isdir(sys_gen_path):
                log_path = os.path.join(sys_gen_path, "logs", "transcript.jsonl")
                if os.path.exists(log_path):
                    try:
                        mtime = os.path.getmtime(log_path)
                        # Chỉ lấy các cuộc hội thoại hoạt động trong vòng 3 ngày qua
                        if time.time() - mtime > 259200: # 3 ngày
                            continue
                            
                        # Đọc dòng đầu tiên để check sub-agent
                        first_content = ""
                        is_sub = False
                        with open(log_path, "r", encoding="utf-8") as lf:
                            first_line = lf.readline()
                            if first_line:
                                data = json.loads(first_line.strip())
                                if data.get("source") == "USER_EXPLICIT":
                                    first_content = data.get("content", "")
                                    if is_subagent_conversation(first_content):
                                        is_sub = True
                        
                        if not is_sub:
                            valid_sessions.append((cid, mtime, log_path, first_content))
                    except Exception:
                        pass
                        
        # Sắp xếp các cuộc hội thoại hợp lệ theo thời gian sửa đổi log giảm dần (mới nhất lên đầu)
        valid_sessions.sort(key=lambda x: x[1], reverse=True)
        
        # Tạo thư viện mới chứa toàn bộ các phiên chat hoạt động trong 3 ngày qua (không giới hạn số lượng)
        new_library = {}
        for cid, mtime, log_path, first_content in valid_sessions:
            # 1. Ưu tiên lấy tiêu đề từ Spec/Plan/Walkthrough Markdown
            md_title = extract_markdown_title(cid)
            if md_title:
                new_library[cid] = md_title
            # 2. Lấy tiêu đề cũ trong library hiện tại nếu có
            elif cid in library:
                new_library[cid] = library[cid]
            # 3. Fallback phân tích transcript
            elif first_content:
                new_library[cid] = clean_topic_title(first_content)
            else:
                new_library[cid] = "Cuộc hội thoại chưa đặt tên"
                
        # So sánh xem library có thay đổi không
        if library != new_library:
            library = new_library
            updated = True
            
    if updated or not os.path.exists(LIBRARY_PATH):
        try:
            os.makedirs(os.path.dirname(LIBRARY_PATH), exist_ok=True)
            with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
                json.dump(library, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
    return library

def detect_project_cwd(conversation_id):
    """Quét transcript.jsonl để dò tìm thư mục dự án tương ứng làm CWD nhằm khớp Project ID"""
    transcript_path = rf"{BRAIN_DIR}\{conversation_id}\.system_generated\logs\transcript.jsonl"
    if os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                content = f.read(150000) # Đọc 150KB đầu tiên để quét nhanh
                # Chuẩn hóa tất cả các dấu gạch chéo ngược kép thành gạch chéo xuôi để dễ parse JSON escape
                normalized = content.replace("\\\\", "/").replace("\\", "/")
                matches = re.findall(r'commandcenter/([^/\"]+)', normalized)
                if matches:
                    project_name = matches[0].strip()
                    project_path = rf"C:\commandcenter\{project_name}"
                    if os.path.exists(project_path):
                        print(f"[System] Dò tìm thấy dự án tương ứng cho `{conversation_id[:8]}`: {project_path}")
                        return project_path
        except Exception as e:
            print(f"[System Warning] Lỗi dò tìm dự án cho `{conversation_id[:8]}`: {e}")
            
    # Mặc định fallback
    return r"C:\commandcenter"

def extract_project_id_from_db(conversation_id):
    """Đọc bảng trajectory_metadata_blob của cuộc hội thoại để trích xuất Project ID thực tế bằng Regex UUID"""
    db_path = rf"C:\Users\user\.gemini\antigravity\conversations\{conversation_id}.db"
    if not os.path.exists(db_path):
        return None
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Chỉ truy vấn dữ liệu cấu hình blob của workspace
        cur.execute("SELECT data FROM trajectory_metadata_blob LIMIT 1")
        row = cur.fetchone()
        conn.close()
        
        if row and row[0]:
            blob = row[0]
            # Tìm tất cả các UUID dạng ascii (độ dài 36 ký tự) trong blob này
            uuids = re.findall(b'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', blob)
            uuid_strs = [u.decode('ascii') for u in uuids]
            if uuid_strs:
                # UUID cuối cùng trong blob cấu hình luôn luôn là Project ID mục tiêu
                project_id = uuid_strs[-1]
                return project_id
    except Exception as e:
        print(f"[System Warning] Lỗi trích xuất Project ID từ DB: {e}")
    return None

def discover_daemon_for_project(project_path):
    """Quét các file json trong thư mục daemon để tìm đúng Port và Token tương ứng với dự án"""
    daemon_dir = r"C:\Users\user\.gemini\antigravity\daemon"
    if not os.path.exists(daemon_dir):
        return None, None
        
    norm_path = project_path.lower().replace("\\", "/").strip()
    
    for filename in os.listdir(daemon_dir):
        if filename.startswith("ls_") and filename.endswith(".json"):
            filepath = os.path.join(daemon_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    info = json.load(f)
                pid = info.get("pid")
                port = info.get("httpPort")
                token = info.get("csrfToken")
                
                if pid and port and token:
                    # Kiểm tra CommandLine của PID này bằng PowerShell
                    cmd = f'Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" | ForEach-Object {{ $_.CommandLine }}'
                    result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
                    cmd_line = result.stdout or ""
                    
                    # Kiểm tra thêm tệp log ls_<hash>.log tương ứng
                    log_path = filepath.replace(".json", ".log")
                    log_content = ""
                    if os.path.exists(log_path):
                        with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                            log_content = lf.read(50000) # Đọc 50KB đầu tiên
                            
                    norm_cmd = cmd_line.lower().replace("\\", "/")
                    norm_log = log_content.lower().replace("\\", "/")
                    
                    # Nếu tìm thấy dấu vết thư mục dự án trong CommandLine hoặc log của Language Server
                    if norm_path in norm_cmd or norm_path in norm_log:
                        print(f"[System] Dò tìm thấy daemon chuẩn cho dự án {project_path}: Port={port}, Token={token}")
                        return f"localhost:{port}", token
            except Exception as e:
                print(f"[System Warning] Lỗi quét daemon file {filename}: {e}")
                
    return None, None

def push_message_to_agent(message_text, conversation_id):
    """Gửi tin nhắn vào Antigravity cho một cuộc hội thoại cụ thể"""
    global active_ls_address, active_csrf_token
    
    cwd_path = detect_project_cwd(conversation_id)
    target_address, target_token = discover_daemon_for_project(cwd_path)
    
    for attempt in range(2):
        ls_address = target_address or active_ls_address
        csrf_token = target_token or active_csrf_token
        
        if not ls_address or not csrf_token:
            if not discover_active_daemon():
                print("[Agent Error] Chưa kết nối được Language Server!")
                return False
            # Quét lại sau khi discover_active_daemon
            ls_address = target_address or active_ls_address
            csrf_token = target_token or active_csrf_token
                
        print(f"[Agent] Đẩy lệnh vào `{conversation_id[:8]}` (Lần {attempt+1}): '{message_text[:30]}...'")
        try:
            env = os.environ.copy()
            # Xóa sạch toàn bộ các biến môi trường bắt đầu bằng ANTIGRAVITY_ để tránh rò rỉ bối cảnh
            for key in list(env.keys()):
                if key.startswith("ANTIGRAVITY_"):
                    del env[key]
                    
            env["ANTIGRAVITY_LS_ADDRESS"] = ls_address
            env["ANTIGRAVITY_CSRF_TOKEN"] = csrf_token
            
            # Trích xuất Project ID mục tiêu từ SQLite DB của cuộc hội thoại và gán đè trực tiếp
            target_project_id = extract_project_id_from_db(conversation_id)
            if target_project_id:
                print(f"[System] Trích xuất thành công Project ID mục tiêu cho `{conversation_id[:8]}`: {target_project_id}")
                env["ANTIGRAVITY_PROJECT_ID"] = target_project_id
            
            cwd_path = detect_project_cwd(conversation_id)
            result = subprocess.run(
                [AGENT_API_PATH, "send-message", conversation_id, message_text],
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=True,
                env=env,
                cwd=cwd_path
            )
            if result.returncode == 0:
                update_log_anchor_for_conversation(conversation_id)
                return True
            else:
                err_msg = result.stderr or result.stdout or ""
                print(f"[Agent API Error] Lỗi thực thi: {err_msg}")
                # Nếu lỗi kết nối (rpc/unavailable/refused) hoặc unauthenticated, reset cấu hình để quét lại ở lượt thử sau
                if any(x in err_msg.lower() for x in ["rpc error", "unavailable", "refused", "unauthenticated"]):
                    active_ls_address = None
                    active_csrf_token = None
                    print("[System] Phát hiện lỗi kết nối hoặc xác thực. Đang tiến hành quét lại cổng mạng cho lượt thử tiếp theo...")
                else:
                    return False
        except Exception as e:
            print(f"[Agent Error] Lỗi gọi subprocess: {e}")
            active_ls_address = None
            active_csrf_token = None
            
    return False

def update_log_anchor_for_conversation(conversation_id):
    """Cập nhật mốc đọc log cho một cuộc hội thoại cụ thể dựa trên transcript.jsonl của nó"""
    global conversation_last_steps
    transcript_path = rf"{BRAIN_DIR}\{conversation_id}\.system_generated\logs\transcript.jsonl"
    if os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_line = json.loads(lines[-1].strip())
                    idx = last_line.get("step_index", -1)
                    conversation_last_steps[conversation_id] = idx
                    print(f"[System] Đã cập nhật mốc log cho `{conversation_id[:8]}` (Step Index: {idx})")
        except Exception:
            pass

def initialize_conversation_markers():
    """Khởi tạo mốc log ban đầu cho tất cả các cuộc hội thoại trong topics_map"""
    global conversation_last_steps
    for cid in list(topics_map.keys()):
        transcript_path = rf"{BRAIN_DIR}\{cid}\.system_generated\logs\transcript.jsonl"
        if os.path.exists(transcript_path):
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_line = json.loads(lines[-1].strip())
                        conversation_last_steps[cid] = last_line.get("step_index", -1)
            except Exception:
                conversation_last_steps[cid] = -1
        else:
            conversation_last_steps[cid] = -1
    print(f"[System] Đã khởi tạo mốc log cho {len(conversation_last_steps)} hội thoại.")

def clean_markdown_for_telegram(text):
    """Bộ lọc dọn dẹp Markdown tương thích với Telegram"""
    lines = []
    for line in text.split('\n'):
        # 1. Chuyển tiêu đề (# Header) thành in đậm
        header_match = re.match(r'^\s*#{1,6}\s+(.+)$', line)
        if header_match:
            line = f"*{header_match.group(1)}*"
            
        # 2. Chuyển gạch đầu dòng (* hoặc -) thành chấm tròn (•)
        bullet_match = re.match(r'^(\s*)([\*\-])\s+(.+)$', line)
        if bullet_match:
            line = f"{bullet_match.group(1)}• {bullet_match.group(3)}"
            
        lines.append(line)
        
    cleaned_text = '\n'.join(lines)
    cleaned_text = cleaned_text.replace('**', '*')
    return cleaned_text

def send_split_message_to_thread(chat_id, thread_id, text, parse_mode="Markdown", limit=2000, conversation_id=None):
    """Chia nhỏ tin nhắn thành các đoạn dưới giới hạn ký tự và gửi liên tiếp vào topic chỉ định"""
    if not text:
        return True
        
    def make_payload(chunk_text, mode=None):
        payload = {
            "chat_id": chat_id,
            "text": chunk_text
        }
        if thread_id is not None and thread_id != 0:
            payload["message_thread_id"] = thread_id
        if mode:
            payload["parse_mode"] = mode
        return payload
        
    def check_result(res):
        if res and not res.get("ok"):
            desc = res.get("description", "").lower()
            if "thread not found" in desc:
                print(f"[System Warning] Phát hiện thread_id {thread_id} bị xóa trên Telegram.")
                if conversation_id and conversation_id in topics_map:
                    print(f"[System] Đang tự động xóa thread hỏng {thread_id} của `{conversation_id[:8]}` để tái tạo...")
                    del topics_map[conversation_id]
                    save_topics_map()
            return False
        return True
        
    if len(text) <= limit:
        res = make_telegram_request("sendMessage", make_payload(text, parse_mode))
        if check_result(res):
            return True
        # Fallback gửi text thô
        res = make_telegram_request("sendMessage", make_payload(text))
        check_result(res)
        return True
        
    # Chia nhỏ tin nhắn theo dòng để tránh cắt đứt câu
    lines = text.split("\n")
    current_chunk = []
    current_length = 0
    
    for line in lines:
        if len(line) > limit:
            if current_chunk:
                chunk_text = "\n".join(current_chunk)
                res = make_telegram_request("sendMessage", make_payload(chunk_text, parse_mode))
                if not check_result(res):
                    res = make_telegram_request("sendMessage", make_payload(chunk_text))
                    check_result(res)
                current_chunk = []
                current_length = 0
                
            sub_lines = [line[i:i+limit] for i in range(0, len(line), limit)]
            for sub_line in sub_lines:
                res = make_telegram_request("sendMessage", make_payload(sub_line))
                check_result(res)
            continue
            
        if current_length + len(line) + 1 > limit:
            chunk_text = "\n".join(current_chunk)
            res = make_telegram_request("sendMessage", make_payload(chunk_text, parse_mode))
            if not check_result(res):
                res = make_telegram_request("sendMessage", make_payload(chunk_text))
                check_result(res)
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
            
    # Gửi chunk còn lại
    if current_chunk:
        chunk_text = "\n".join(current_chunk)
        res = make_telegram_request("sendMessage", make_payload(chunk_text, parse_mode))
        if not check_result(res):
            res = make_telegram_request("sendMessage", make_payload(chunk_text))
            check_result(res)
            
    return True

def watch_transcript_loop():
    global chat_id, topics_map, conversation_last_steps
    print("[System] Bắt đầu khởi chạy luồng theo dõi phản hồi đa hội thoại...")
    
    while True:
        if chat_id:
            active_conversations = load_conversation_library()
            # Quét qua tất cả các cuộc hội thoại chính có trong thư viện active
            for cid in list(active_conversations.keys()):
                thread_info = topics_map.get(cid)
                # Trích xuất thread_id thực tế từ dict hoặc int
                thread_id = thread_info.get("thread_id") if isinstance(thread_info, dict) else thread_info
                
                transcript_path = rf"{BRAIN_DIR}\{cid}\.system_generated\logs\transcript.jsonl"
                if os.path.exists(transcript_path):
                    try:
                        with open(transcript_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            if not lines:
                                continue
                            
                            # Lấy mốc index cũ của cuộc hội thoại này hoặc đặt mốc ban đầu bằng dòng cuối cùng để bỏ qua tin quá khứ
                            if cid not in conversation_last_steps:
                                try:
                                    last_line = json.loads(lines[-1].strip())
                                    conversation_last_steps[cid] = last_line.get("step_index", -1)
                                except Exception:
                                    conversation_last_steps[cid] = -1
                                continue
                                
                            last_idx = conversation_last_steps.get(cid, -1)
                            
                            for line in reversed(lines):
                                line_str = line.strip()
                                if not line_str:
                                    continue
                                try:
                                    data = json.loads(line_str)
                                except Exception:
                                    continue
                                idx = data.get("step_index", -1)
                                if idx > last_idx and data.get("source") == "MODEL" and data.get("type") == "PLANNER_RESPONSE":
                                    ai_response = data.get("content", "")
                                    conversation_last_steps[cid] = idx  # Cập nhật mốc log mới
                                    
                                    # Lấy tiêu đề hội thoại
                                    title = active_conversations.get(cid, "Tài liệu Antigravity")
                                    
                                    # Chế độ On-demand: Tạo topic nếu chưa được đăng ký trong map
                                    if thread_id is None:
                                        discover_active_conversation(cid, title)
                                        thread_info = topics_map.get(cid)
                                        thread_id = thread_info.get("thread_id") if isinstance(thread_info, dict) else thread_info
                                        if thread_id is None:
                                            thread_id = 0
                                            
                                    print(f"[Agent Response] Phát hiện câu trả lời mới trong `{cid[:8]}` (Step: {idx}). Gửi về Telegram Thread {thread_id}...")
                                    
                                    formatted_text = clean_markdown_for_telegram(ai_response)
                                    
                                    # Lấy tiêu đề hội thoại
                                    lib = load_conversation_library()
                                    title = lib.get(cid, "Tài liệu Antigravity")
                                    
                                    # Tự động xuất bản Telegra.ph nếu tin nhắn dài hoặc là tài liệu Spec/Plan/Walkthrough
                                    if len(ai_response) > 1500 or any(x in ai_response for x in ["# Kế hoạch triển khai", "# WALKTHROUGH", "# Specification"]):
                                        print(f"[Watcher] Tin nhắn dài ({len(ai_response)} ký tự). Tiến hành xuất bản Telegra.ph...")
                                        telegraph_url = publish_to_telegraph(title, ai_response)
                                        if telegraph_url:
                                            teaser = formatted_text[:300] + "..." if len(formatted_text) > 300 else formatted_text
                                            teaser_safe = escape_html(teaser)
                                            msg = (
                                                f"📋 <b>Tài liệu thiết kế đã sẵn sàng!</b>\n"
                                                f"• Hội thoại: <b>{escape_html(title)}</b>\n"
                                                f"• Tóm tắt sơ bộ:\n<blockquote>{teaser_safe}</blockquote>\n\n"
                                                f"🔗 <a href=\"{telegraph_url}\"><b>Nhấp vào đây để xem chi tiết đầy đủ (Instant View)</b></a>"
                                            )
                                            payload = {
                                                "chat_id": chat_id,
                                                "text": msg,
                                                "parse_mode": "HTML"
                                            }
                                            if thread_id is not None:
                                                payload["message_thread_id"] = thread_id
                                            make_telegram_request("sendMessage", payload)
                                        else:
                                            # Fallback gửi text thô nếu Telegraph lỗi
                                            send_split_message_to_thread(chat_id, thread_id, formatted_text, parse_mode="Markdown", conversation_id=cid)
                                    else:
                                        send_split_message_to_thread(chat_id, thread_id, formatted_text, parse_mode="Markdown", conversation_id=cid)
                                    break
                    except Exception as e:
                        print(f"[Watcher Error] Lỗi đọc log cho `{cid[:8]}`: {e}")
        time.sleep(1)

# ==================== ĐIỀU PHỐI LỆNH TELEGRAM BOT ====================

def handle_telegram_command(text, sender_chat_id, thread_id=None):
    global chat_id, listed_ids, CONVERSATION_ID, topics_map
    chat_id = sender_chat_id
    
    def send_cmd_response(msg_text, parse_mode="HTML"):
        payload = {"chat_id": chat_id, "text": msg_text}
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        if parse_mode:
            payload["parse_mode"] = parse_mode
        make_telegram_request("sendMessage", payload)

    # 1. Lệnh /help
    if text.startswith("/help"):
        help_msg = (
            "📚 <b>Hướng dẫn điều khiển Antigravity Bot:</b>\n\n"
            "• <code>/list</code> : Hiển thị thư viện các phiên chat (ID và Chủ đề)\n"
            "• <code>/switch &lt;số_thứ_tự hoặc ID&gt;</code> : Chuyển hướng chat sang phiên đích\n"
            "• <code>/log &lt;số_tin&gt;</code> : Đọc lại &lt;số_tin&gt; tin nhắn gần đây của phiên hiện hành\n"
            "• <code>/autoswitch &lt;on/off&gt;</code> : Bật/Tắt tự động bám theo hội thoại hoạt động trên IDE (hoặc gõ <code>/autoswitch</code> để chuyển đổi nhanh)\n"
            "• <b>Chat thông thường</b> : Đẩy trực tiếp văn bản vào Agent. (Khi dùng Topics, tin nhắn sẽ tự động gửi vào Agent của topic đó)."
        )
        send_cmd_response(help_msg, "HTML")
        return True

    # 2. Lệnh /list
    elif text.startswith("/list"):
        lib = load_conversation_library()
        if not lib:
            send_cmd_response("📂 Thư viện hội thoại trống.", None)
            return True
            
        listed_ids = list(lib.keys())
        listed_ids.sort(
            key=lambda cid: os.path.getmtime(os.path.join(CONVERSATIONS_DIR, f"{cid}.db")) 
            if os.path.exists(os.path.join(CONVERSATIONS_DIR, f"{cid}.db")) else 0,
            reverse=True
        )
        
        total_conversations = len(listed_ids)
        listed_ids = listed_ids[:5]
        
        list_lines = [f"📂 <b>Danh sách hội thoại (Mới nhất, hiển thị 5/{total_conversations}):</b>"]
        for idx, cid in enumerate(listed_ids, 1):
            is_active = (cid == CONVERSATION_ID)
            # Nếu đang chạy trong topic, check xem cid này có khớp với topic hiện tại không
            if thread_id is not None:
                is_active = (topics_map.get(cid) == thread_id)
                
            marker = "🟢 (Hiện tại) " if is_active else "• "
            topic = lib[cid]
            topic_safe = escape_html(topic)
            list_lines.append(f"{idx}. {marker}<code>{cid[:8]}...</code> : <b>{topic_safe}</b>")
            
        list_lines.append("\n💡 Gõ <code>/switch &lt;số&gt;</code> hoặc <code>/switch &lt;ID&gt;</code> để chuyển hướng chat!")
        send_cmd_response("\n".join(list_lines), "HTML")
        return True

    # 3. Lệnh /switch
    elif text.startswith("/switch"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_cmd_response("⚠️ Cú pháp: <code>/switch &lt;số_thứ_tự&gt;</code> hoặc <code>/switch &lt;ID&gt;</code>", "HTML")
            return True
            
        target = parts[1].strip()
        target_id = None
        
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(listed_ids):
                target_id = listed_ids[idx]
            else:
                send_cmd_response("⚠️ Số thứ tự ngoài danh sách. Vui lòng gõ `/list` trước.", None)
                return True
        else:
            lib = load_conversation_library()
            if target in lib:
                target_id = target
            else:
                for cid in lib:
                    if cid.startswith(target):
                        target_id = cid
                        break
                        
        if target_id:
            switch_conversation_context(target_id)
        else:
            send_cmd_response("⚠️ Không tìm thấy hội thoại khớp với yêu cầu.", None)
        return True

    # 4. Lệnh /log
    elif text.startswith("/log"):
        parts = text.split(maxsplit=1)
        count = 5
        if len(parts) >= 2 and parts[1].isdigit():
            count = int(parts[1])
            
        # Xác định cuộc hội thoại cần log dựa trên topic hiện tại hoặc fallback
        target_cid = CONVERSATION_ID
        if thread_id is not None:
            for cid, tid in topics_map.items():
                if tid == thread_id:
                    target_cid = cid
                    break
                    
        transcript_path = rf"{BRAIN_DIR}\{target_cid}\.system_generated\logs\transcript.jsonl"
        if not os.path.exists(transcript_path):
            send_cmd_response("⚠️ Không tìm thấy tệp nhật ký của hội thoại này.", None)
            return True
            
        try:
            chat_logs = []
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            valid_steps = []
            for line in lines:
                data = json.loads(line.strip())
                source = data.get("source")
                content = data.get("content")
                if source in ("USER_EXPLICIT", "MODEL", "SYSTEM") and content:
                    valid_steps.append((source, content))
                    
            target_steps = valid_steps[-count:]
            for src, content in target_steps:
                content_clean = content.strip()
                if len(content_clean) > 800:
                    content_clean = content_clean[:800] + "\n...[Rút gọn]..."
                
                if src == "USER_EXPLICIT":
                    chat_logs.append(f"👤 *Bạn:* {content_clean}")
                elif src == "MODEL":
                    chat_logs.append(f"🤖 *AI:* {clean_markdown_for_telegram(content_clean)}")
                else:
                    chat_logs.append(f"⚙️ *Hệ thống:* _ {content_clean} _")
                    
            if chat_logs:
                log_header = f"📋 *Lịch sử {len(chat_logs)} tin nhắn gần nhất:*\n\n"
                send_cmd_response(log_header + "\n\n──────────────────\n\n".join(chat_logs), "Markdown")
            else:
                send_cmd_response("📋 Lịch sử hội thoại chưa có tin nhắn nào.", None)
        except Exception as e:
            send_cmd_response(f"⚠️ Lỗi đọc nhật ký: {e}", None)
        return True
        
    # 5. Lệnh /autoswitch
    elif text.startswith("/autoswitch"):
        parts = text.split(maxsplit=1)
        current_status = "ON"
        
        config_data = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    current_status = config_data.get("auto_switch", "ON")
            except Exception:
                pass
                
        new_status = None
        if len(parts) >= 2:
            arg = parts[1].strip().lower()
            if arg in ("on", "true", "1"):
                new_status = "ON"
            elif arg in ("off", "false", "0"):
                new_status = "OFF"
        
        if new_status is None:
            new_status = "OFF" if current_status == "ON" else "ON"
            
        config_data["auto_switch"] = new_status
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            status_text = "🟢 <b>ĐÃ BẬT</b>" if new_status == "ON" else "🔴 <b>ĐÃ TẮT</b>"
            response_msg = (
                f"⚙️ <b>Cấu hình Auto-Switch:</b>\n"
                f"• Trạng thái hiện tại: {status_text}\n\n"
                f"<i>Bot sẽ { 'TỰ ĐỘNG' if new_status == 'ON' else 'KHÔNG' } đuổi theo hội thoại hoạt động gần nhất trên IDE.</i>"
            )
        except Exception as e:
            response_msg = f"⚠️ Lỗi cập nhật cấu hình: {e}"
            
        send_cmd_response(response_msg, "HTML")
        return True

    return False

def run_telegram_bot():
    global chat_id, topics_map, CONVERSATION_ID
    print("[Telegram] Khởi động Telegram Long Polling với bộ giải mã lệnh...")
    offset = 0
    
    me = make_telegram_request("getMe")
    if me and me.get("ok"):
        print(f"[Telegram] Kết nối thành công! Bot username: @{me['result']['username']}")
    else:
        print("[Telegram Error] Kết nối thất bại. Token sai hoặc mạng lỗi!")
        return
        
    while True:
        updates = make_telegram_request("getUpdates", {"offset": offset, "timeout": 30})
        if updates and updates.get("ok"):
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "").strip()
                sender_chat_id = message.get("chat", {}).get("id")
                thread_id = message.get("message_thread_id")
                
                if text and sender_chat_id:
                    chat_id = sender_chat_id
                    
                    # 1. Thử xử lý tin nhắn như một Lệnh (/help, /list, /switch, /log)
                    if handle_telegram_command(text, chat_id, thread_id):
                        continue
                        
                    # 2. Xác định cuộc hội thoại đích (conversation_id) dựa trên thread_id
                    target_cid = None
                    if thread_id is not None:
                        for cid, thread_info in topics_map.items():
                            curr_tid = thread_info.get("thread_id") if isinstance(thread_info, dict) else thread_info
                            if curr_tid == thread_id:
                                target_cid = cid
                                break
                    
                    # Fallback về bối cảnh mặc định nếu không chạy trong topic
                    if not target_cid:
                        target_cid = CONVERSATION_ID
                        
                    # 3. Đẩy tin nhắn vào Agent của hội thoại đích
                    push_message_to_agent(text, target_cid)
        time.sleep(1)

if __name__ == "__main__":
    # 0. Nạp cấu hình Telegram Token động
    load_env()
    load_topics_map()
    
    # 1. Phát hiện cấu hình kết nối active
    discover_active_daemon()
    
    # 2. Tìm cuộc hội thoại hoạt động gần nhất để làm mặc định ban đầu (không tạo topic)
    lib = load_conversation_library()
    if lib:
        CONVERSATION_ID = list(lib.keys())[0]
        
    # 3. Khởi tạo mốc log cho toàn bộ các cuộc hội thoại
    initialize_conversation_markers()
    
    # 4. Khởi chạy luồng theo dõi log gửi tin nhắn phản hồi đa hội thoại
    watcher_thread = threading.Thread(target=watch_transcript_loop, daemon=True)
    watcher_thread.start()
    
    # 5. Chạy Bot Telegram chính thức
    run_telegram_bot()
