# main.py

import asyncio
import logging
from telegram.ext import Application, CommandHandler
from config import TELEGRAM_TOKEN
from bot_handler import (
    add_symbol, 
    remove_symbol, 
    list_symbols, 
    start, 
    backtest_command,
    restart_bot
)
from trading_logic import run_signal_checker
from database import init_db

# --- CẤU HÌNH LOGGING NÂNG CAO ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def main() -> None:
    """
    Khởi động bot, đăng ký các handler và chạy bộ máy phân tích tín hiệu song song.
    """
    await init_db()

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN không được tìm thấy! Vui lòng kiểm tra file config.py hoặc biến môi trường.")
        return

    # Tạo Application instance. Đây là nơi duy nhất tạo ra nó.
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Đăng ký các lệnh
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_symbol))
    application.add_handler(CommandHandler("remove", remove_symbol))
    application.add_handler(CommandHandler("list", list_symbols))
    application.add_handler(CommandHandler("backtest", backtest_command))
    application.add_handler(CommandHandler("restart", restart_bot))
    
    # -- SỬA LỖI QUAN TRỌNG --
    # 1. Khởi chạy bộ máy quét tín hiệu như một tác vụ nền (background task).
    # 2. Lưu trữ task này vào context của application để các handler có thể truy cập và quản lý nó.
    #    Đây là cách làm đúng thay vì dùng biến `global`.
    signal_checker_task = asyncio.create_task(run_signal_checker(application.bot))
    application.bot_data["watchlist_task"] = signal_checker_task
    
    logger.info("Signal checker task has been created and is running in the background.")

    # Chạy bot polling. Hàm này sẽ chạy cho đến khi bạn nhấn Ctrl+C
    try:
        logger.info("Bot polling started...")
        await application.run_polling()
    finally:
        # Dọn dẹp task khi bot dừng
        logger.info("Stopping signal checker task...")
        task = application.bot_data.get("watchlist_task")
        if task and not task.done():
            task.cancel()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    logger.info("Bot is starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")