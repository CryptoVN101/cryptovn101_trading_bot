# config.py
import os
from dotenv import load_dotenv

# Tải các biến môi trường từ file .env (chỉ dùng khi chạy local)
load_dotenv()

# Lấy giá trị token và các ID
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID") 
CHANNEL_ID = os.getenv("CHANNEL_ID") 

# Lấy URL của database từ biến môi trường
DATABASE_URL = os.getenv("DATABASE_URL")

# --- KIỂM TRA BIẾN MÔI TRƯỜNG MỘT CÁCH CHI TIẾT ---
missing_vars = []
if not TELEGRAM_TOKEN:
    missing_vars.append("TELEGRAM_TOKEN")
if not CHANNEL_ID:
    missing_vars.append("CHANNEL_ID")
if not DATABASE_URL:
    missing_vars.append("DATABASE_URL")

if missing_vars:
    # Báo lỗi chi tiết, chỉ rõ biến nào đang thiếu
    raise ValueError(f"LỖI: Thiếu các biến môi trường sau: {', '.join(missing_vars)}. Vui lòng thêm chúng trong tab 'Variables' trên Railway.")

