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
    backtest_command
)
from trading_logic import run_signal_checker
from database import init_db # Import hàm khởi tạo DB

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main() -> None:
    """Khởi động bot và bộ máy phân tích tín hiệu."""
    
    # Khởi tạo database trước khi làm mọi thứ khác
    await init_db()

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
    print("Bot is starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")

