# main.py
import logging
import asyncio
import os
from telegram.ext import Application, CommandHandler
from config import TELEGRAM_TOKEN
from bot_handler import start, send_signal, add_symbol, remove_symbol, list_symbols
from trading_logic import run_signal_checker

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def ensure_watchlist_file():
    """Tạo file watchlist.txt nếu chưa tồn tại."""
    if not os.path.exists('watchlist.txt'):
        with open('watchlist.txt', 'w') as f:
            f.write("BTCUSDT\n") # Thêm một mã mặc định
        print("Created watchlist.txt file.")

async def main() -> None:
    """Khởi động bot và bộ máy phân tích tín hiệu."""
    ensure_watchlist_file()

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN không được tìm thấy! Vui lòng kiểm tra file .env.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Đăng ký các lệnh quản lý watchlist
    application.add_handler(CommandHandler("add", add_symbol))
    application.add_handler(CommandHandler("remove", remove_symbol))
    application.add_handler(CommandHandler("list", list_symbols))
    
    # Đăng ký các lệnh cũ
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("signal", send_signal))
    
    # Tích hợp chạy song song
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Chạy bộ máy phân tích tín hiệu với đối tượng bot
    await run_signal_checker(application.bot)

    await application.updater.stop()
    await application.stop()

if __name__ == "__main__":
    print("Bot is starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")

