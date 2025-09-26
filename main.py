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


async def post_shutdown_cleanup(application: Application):
    """
    Hàm dọn dẹp được gọi sau khi application đã dừng hoàn toàn.
    """
    logger.info("Bot is shutting down. Cleaning up background task...")
    task = application.bot_data.get("watchlist_task")
    if task and not task.done():
        task.cancel()
        # Đợi một chút để task thực sự bị hủy
        await asyncio.sleep(1) 
    logger.info("Cleanup complete.")


async def main() -> None:
    """
    Khởi động bot, đăng ký các handler và chạy bộ máy phân tích tín hiệu song song.
    """
    await init_db()

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN không được tìm thấy! Vui lòng kiểm tra file config.py hoặc biến môi trường.")
        return

    # --- SỬA LỖI QUAN TRỌNG TẠI ĐÂY ---
    # Chuyển .post_shutdown vào chuỗi builder
    builder = Application.builder().token(TELEGRAM_TOKEN)
    builder.post_shutdown(post_shutdown_cleanup)
    application = builder.build()
    
    # Đăng ký các lệnh
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_symbol))
    application.add_handler(CommandHandler("remove", remove_symbol))
    application.add_handler(CommandHandler("list", list_symbols))
    application.add_handler(CommandHandler("backtest", backtest_command))
    application.add_handler(CommandHandler("restart", restart_bot))
    
    # Khởi chạy bộ máy quét tín hiệu như một tác vụ nền
    signal_checker_task = asyncio.create_task(run_signal_checker(application.bot))
    application.bot_data["watchlist_task"] = signal_checker_task
    
    logger.info("Signal checker task created. Starting bot polling...")
    
    # Để application tự quản lý vòng đời của nó
    await application.run_polling()


if __name__ == "__main__":
    logger.info("Bot is starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")