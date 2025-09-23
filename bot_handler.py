# bot_handler.py
import asyncio
import os
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes
from telegram import Bot
from config import CHANNEL_ID
from backtester import run_backtest_logic

# --- QUẢN LÝ WATCHLIST ---
WATCHLIST_FILE = "watchlist.txt"

def get_watchlist():
    if not os.path.exists(WATCHLIST_FILE): return []
    with open(WATCHLIST_FILE, "r") as f:
        symbols = [line.strip().upper() for line in f if line.strip()]
    return symbols

def save_watchlist(symbols):
    with open(WATCHLIST_FILE, "w") as f:
        for symbol in sorted(symbols):
            f.write(f"{symbol}\n")

# --- CÁC HÀM XỬ LÝ LỆNH ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Chào {user.mention_html()}, bot tín hiệu đã sẵn sàng! Dùng /backtest để mô phỏng."
    )

async def add_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Ví dụ: /add BTCUSDT ETHUSDT")
        return
    watchlist = get_watchlist()
    added = [s.upper() for s in context.args if s.upper() not in watchlist]
    if added:
        save_watchlist(watchlist + added)
        await update.message.reply_text(f"Đã thêm: {', '.join(added)}")
    else:
        await update.message.reply_text("Các mã đã có trong danh sách.")

async def remove_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Ví dụ: /remove SOLUSDT")
        return
    watchlist = get_watchlist()
    removed, not_found = [], []
    for s in context.args:
        if s.upper() in watchlist:
            watchlist.remove(s.upper())
            removed.append(s.upper())
        else:
            not_found.append(s.upper())
    if removed:
        save_watchlist(watchlist)
        message = f"Đã xóa: {', '.join(removed)}"
        if not_found: message += f"\nKhông tìm thấy: {', '.join(not_found)}"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("Không tìm thấy các mã này.")

async def list_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    watchlist = get_watchlist()
    if not watchlist:
        message = "Danh sách theo dõi trống."
    else:
        message = "<b>Danh sách theo dõi:</b>\n\n" + "\n".join([f"• <code>{s}</code>" for s in watchlist])
    await update.message.reply_text(message, parse_mode='HTML')

# --- HÀM GỬI TÍN HIỆU ---
async def send_formatted_signal(bot: Bot, signal_data: dict):
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    original_time = datetime.fromtimestamp(signal_data['timestamp'] / 1000, tz=pytz.utc).astimezone(vietnam_tz)
    confirmation_time = datetime.fromtimestamp(signal_data['confirmation_timestamp'] / 1000, tz=pytz.utc).astimezone(vietnam_tz)

    signal_type_text = "Tín hiệu đảo chiều BUY/LONG" if 'LONG' in signal_data['type'] else "Tín hiệu đảo chiều SELL/SHORT"
    signal_emoji = "🟢" if 'LONG' in signal_data['type'] else "🔴"
        
    message = (
        f"<b>🔶 Token:</b> <code>{signal_data['symbol']}</code>\n"
        f"<b>{signal_emoji} {signal_type_text}</b>\n"
        f"<b>⏰ Khung thời gian:</b> {signal_data.get('timeframe', 'N/A')}\n"
        f"<b>💰 Giá xác nhận:</b> <code>{signal_data.get('confirmation_price', 0.0):.2f}</code>\n"
        f"<b>🔍 Tỷ lệ Win:</b> {signal_data.get('win_rate', 'N/A')}\n"
        f"---------------------------------\n"
        f"<i>Thời gian gốc: {original_time.strftime('%H:%M %d-%m-%Y')}</i>\n"
        f"<i>Thời gian xác nhận: {confirmation_time.strftime('%H:%M %d-%m-%Y')}</i>"
    )
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='HTML')
        print(f"✅ Đã gửi tín hiệu cho {signal_data['symbol']} lên channel.")
    except Exception as e:
        print(f"❌ Gửi tín hiệu thất bại: {e}")

# --- LỆNH BACKTEST ---
async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Bắt đầu backtest... Việc này có thể mất vài phút.")
    try:
        found_signals = await run_backtest_logic() 
        if not found_signals:
            await update.message.reply_text("✅ Hoàn tất. Không tìm thấy tín hiệu nào.")
            return
        await update.message.reply_text(f"🔥 Tìm thấy {len(found_signals)} tín hiệu! Bắt đầu gửi...")
        
        # SỬA LỖI: Chỉ lặp qua một biến `signal` duy nhất
        for signal in found_signals:
            await send_formatted_signal(context.bot, signal)
            await asyncio.sleep(1)
            
        await update.message.reply_text("✅ Backtest hoàn tất. Tất cả tín hiệu đã được gửi.")
    except Exception as e:
        print(f"Lỗi backtest: {e}")
        await update.message.reply_text(f" Rất tiếc, đã có lỗi: {e}")

