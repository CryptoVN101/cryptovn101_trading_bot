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
# Railway sẽ tự động cung cấp biến này khi bạn thêm database
DATABASE_URL = os.getenv("DATABASE_URL")

# Kiểm tra các biến quan trọng
if not TELEGRAM_TOKEN or not CHANNEL_ID or not DATABASE_URL:
    raise ValueError("Vui lòng kiểm tra lại các biến môi trường cần thiết!")

