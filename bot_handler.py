import asyncio
import os
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes, Application
from telegram import Bot
from config import CHANNEL_ID
from backtester import run_backtest_logic
from database import (
    get_watchlist_from_db, 
    add_symbols_to_db, 
    remove_symbols_from_db
)
from trading_logic import run_signal_checker

# Cấu hình logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Khởi tạo bot
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Thay bằng token của bạn
application = Application.builder().token(BOT_TOKEN).build()
bot = Bot(BOT_TOKEN)

# Hàm reload watchlist và restart WebSocket
async def reload_signal_checker(bot_instance):  # Thay context bằng bot_instance
    logger.info("Bắt đầu reload watchlist...")
    global watchlist_task
    if 'watchlist_task' in globals() and not watchlist_task.done():
        watchlist_task.cancel()
    watchlist_task = asyncio.create_task(run_signal_checker(bot_instance))
    logger.info("WebSocket đã được khởi động lại với watchlist mới.")

# Handler cho /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Chào {user.mention_html()}, bot tín hiệu đã sẵn sàng!"
    )

# Handler cho /add
async def add_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Ví dụ: /add BTCUSDT ETHUSDT")
        return
    
    current_watchlist = await get_watchlist_from_db()
    symbols_to_add = [s.upper() for s in context.args if s.upper() not in current_watchlist]
    
    if symbols_to_add:
        await add_symbols_to_db(symbols_to_add)
        await update.message.reply_text(f"Đã thêm thành công: {', '.join(symbols_to_add)}")
        await reload_signal_checker(context.bot)  # Sử dụng context.bot
    else:
        await update.message.reply_text("Các mã coin này đã có trong danh sách.")

# Handler cho /remove
async def remove_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Ví dụ: /remove SOLUSDT")
        return

    current_watchlist = await get_watchlist_from_db()
    symbols_to_remove = [s.upper() for s in context.args if s.upper() in current_watchlist]
    not_found_symbols = [s.upper() for s in context.args if s.upper() not in current_watchlist]

    if symbols_to_remove:
        await remove_symbols_from_db(symbols_to_remove)
        message = f"Đã xóa thành công: {', '.join(symbols_to_remove)}"
        if not_found_symbols:
            message += f"\nKhông tìm thấy: {', '.join(not_found_symbols)}"
        await update.message.reply_text(message)
        await reload_signal_checker(context.bot)  # Sử dụng context.bot
    else:
        await update.message.reply_text("Không tìm thấy các mã coin này trong danh sách.")

# Handler cho /list
async def list_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    watchlist = await get_watchlist_from_db()
    if not watchlist:
        message = "Danh sách theo dõi đang trống."
    else:
        message = "<b>Danh sách theo dõi:</b>\n\n" + "\n".join([f"• <code>{s}</code>" for s in watchlist])
    await update.message.reply_text(message, parse_mode='HTML')

# Handler cho /restart
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Đang khởi động lại bot...")
    global watchlist_task
    if 'watchlist_task' in globals() and not watchlist_task.done():
        watchlist_task.cancel()
    watchlist_task = asyncio.create_task(run_signal_checker(context.bot))
    await update.message.reply_text("Bot đã được khởi động lại.")

# Hàm gửi tín hiệu
async def send_formatted_signal(bot: Bot, signal_data: dict):
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    original_time = datetime.fromtimestamp(signal_data['timestamp'] / 1000, tz=pytz.utc).astimezone(vietnam_tz)
    confirmation_time = datetime.fromtimestamp(signal_data['confirmation_timestamp'] / 1000, tz=pytz.utc).astimezone(vietnam_tz)

    signal_type_text = "Tín hiệu đảo chiều BUY/LONG" if 'LONG' in signal_data['type'] else "Tín hiệu đảo chiều BÁN/SHORT"
    signal_emoji = "🟢" if 'LONG' in signal_data['type'] else "🔴"  # Sửa lỗi thiếu emoji
    
    stoch_m15 = signal_data.get('stoch_m15', 0.0)
    stoch_h1 = signal_data.get('stoch_h1', 0.0)
        
    message = (
        f"<b>🔶 Token:</b> <code>{signal_data['symbol']}</code>\n"
        f"<b>{signal_emoji} {signal_type_text}</b>\n"
        f"<b>⏰ Khung thời gian:</b> {signal_data.get('timeframe', 'N/A')}\n"
        f"<b>💰 Giá xác nhận:</b> <code>{signal_data.get('confirmation_price', 0.0):.4f}</code>\n"
        f"<b>🔍 Tỷ lệ Win:</b> {signal_data.get('win_rate', 'N/A')}\n"
        f"---------------------------------\n"
        f"<i>Thời gian gốc: {original_time.strftime('%H:%M %d-%m-%Y')}</i>\n"
        f"<i>Thời gian xác nhận: {confirmation_time.strftime('%H:%M %d-%m-%Y')}</i>\n"
        f"<i>Stoch (M15/H1): {stoch_m15:.2f} / {stoch_h1:.2f}</i>"
    )
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='HTML')
        logger.info(f"✅ Đã gửi tín hiệu cho {signal_data['symbol']} lên channel.")
    except Exception as e:
        logger.error(f"❌ Gửi tín hiệu thất bại: {e}")

# Handler cho /backtest
async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Bắt đầu backtest...")
    try:
        found_signals = await run_backtest_logic()
        if not found_signals:
            await update.message.reply_text("✅ Hoàn tất. Không tìm thấy tín hiệu nào.")
            return
        await update.message.reply_text(f"🔥 Tìm thấy {len(found_signals)} tín hiệu! Bắt đầu gửi...")
        for signal in found_signals:
            await send_formatted_signal(context.bot, signal)
            await asyncio.sleep(1)
        await update.message.reply_text("✅ Backtest hoàn tất.")
    except Exception as e:
        logger.error(f"Lỗi backtest: {e}")
        await update.message.reply_text(f"Rất tiếc, đã có lỗi: {e}")

# Đăng ký các handler
def main():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_symbol))
    application.add_handler(CommandHandler("remove", remove_symbol))
    application.add_handler(CommandHandler("list", list_symbols))
    application.add_handler(CommandHandler("restart", restart_bot))
    application.add_handler(CommandHandler("backtest", backtest_command))

    # Khởi chạy bot và trading_logic
    global watchlist_task
    watchlist_task = asyncio.create_task(run_signal_checker(bot))
    application.run_polling()

if __name__ == "__main__":
    from telegram.ext import CommandHandler
    main()

# Export các hàm cần thiết
__all__ = ['get_watchlist_from_db', 'send_formatted_signal', 'run_signal_checker', 'reload_signal_checker']