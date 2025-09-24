# main.py
import asyncio
import logging
import os
from telegram.ext import Application, CommandHandler
from config import TELEGRAM_TOKEN
from bot_handler import (
    add_symbol, 
    remove_symbol, 
    list_symbols, 
    start, 
    backtest_command
)
from trading_logic import run_signal_checker
from database import init_db

# --- CẤU HÌNH LOGGING NÂNG CAO ---

# 1. Cấu hình logger gốc (cho code của chúng ta)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
# 2. Tạo một logger riêng cho ứng dụng của chúng ta để dễ nhận biết
logger = logging.getLogger(__name__)

# 3. Tắt các log INFO không cần thiết từ các thư viện bên ngoài
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)


async def main() -> None:
    """Khởi động bot và bộ máy phân tích tín hiệu."""
    
    await init_db()

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN không được tìm thấy! Vui lòng kiểm tra biến môi trường.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Đăng ký các lệnh
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_symbol))
    application.add_handler(CommandHandler("remove", remove_symbol))
    application.add_handler(CommandHandler("list", list_symbols))
    application.add_handler(CommandHandler("backtest", backtest_command))
    
    # Tích hợp chạy song song
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Chạy bộ máy phân tích tín hiệu
    await run_signal_checker(application.bot)

    # Dừng bot
    await application.updater.stop()
    await application.stop()

if __name__ == "__main__":
    logger.info("Bot is starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")

