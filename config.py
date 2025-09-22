# config.py
import os
from dotenv import load_dotenv

# Tải các biến môi trường từ file .env
load_dotenv()

# Lấy các giá trị từ file .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")        # ID của Group để test lệnh
CHANNEL_ID = os.getenv("CHANNEL_ID")  # ID của Channel để bắn tín hiệu

# Kiểm tra để đảm bảo các biến quan trọng đã được thiết lập
if not all([TELEGRAM_TOKEN, CHAT_ID, CHANNEL_ID]):
    raise ValueError("Vui lòng kiểm tra lại các biến TELEGRAM_TOKEN, CHAT_ID, CHANNEL_ID trong file .env!")

