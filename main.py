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
from database import init_db, close_db_pool 

# --- CẤU HÌNH LOGGING (Không đổi) ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# --- HÀM DỌN DẸP (Không đổi) ---
async def post_shutdown_cleanup(application: Application):
    """
    Hàm dọn dẹp được gọi sau khi application đã dừng hoàn toàn.
    """
    logger.info("Bot is shutting down. Cleaning up background task and DB pool...")
    
    task = application.bot_data.get("watchlist_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # Lỗi này là bình thường khi hủy task
    
    await close_db_pool()
    
    logger.info("Cleanup complete.")


# --- HÀM MAIN ĐƯỢC CẤU TRÚC LẠI HOÀN TOÀN ---
async def main() -> None:
    """
    Khởi động bot và các tác vụ nền theo cách tương thích với asyncio.
    """
    await init_db()

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN không được tìm thấy!")
        return

    # 1. Xây dựng Application như cũ
    builder = Application.builder().token(TELEGRAM_TOKEN)
    builder.post_shutdown(post_shutdown_cleanup)
    application = builder.build()
    
    # 2. Đăng ký các handler như cũ
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_symbol))
    application.add_handler(CommandHandler("remove", remove_symbol))
    application.add_handler(CommandHandler("list", list_symbols))
    application.add_handler(CommandHandler("backtest", backtest_command))
    application.add_handler(CommandHandler("restart", restart_bot))
    
    # 3. Khởi chạy bộ quét tín hiệu như cũ
    signal_checker_task = asyncio.create_task(run_signal_checker(application.bot))
    application.bot_data["watchlist_task"] = signal_checker_task
    
    logger.info("Signal checker task created. Starting bot...")

    # 4. KHỞI CHẠY BOT THEO CÁCH MỚI (NON-BLOCKING)
    try:
        # Khởi tạo application (chuẩn bị handler, ...)
        await application.initialize()
        # Bắt đầu chạy updater để nhận tin nhắn (chạy nền)
        await application.updater.start_polling()
        # Bắt đầu xử lý các tin nhắn đã nhận (chạy nền)
        await application.start()
        
        logger.info("Bot is running successfully!")
        
        # Giữ cho chương trình chính chạy mãi mãi
        # cho đến khi có lỗi hoặc bị dừng (ví dụ: Ctrl+C)
        await asyncio.Event().wait()

    finally:
        logger.info("Stopping bot...")
        # Đảm bảo các tiến trình nền của bot được dừng an toàn
        if application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        
        # Lệnh shutdown sẽ kích hoạt hàm post_shutdown_cleanup của chúng ta
        await application.shutdown()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    logger.info("Bot is starting...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"An unhandled exception occurred at the top level: {e}", exc_info=True)