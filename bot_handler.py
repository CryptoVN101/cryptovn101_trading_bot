# bot_handler.py
import asyncio
import os
from datetime import datetime
import pytz
from telegram import Update, Bot
from telegram.ext import ContextTypes
from config import CHANNEL_ID
from backtester import run_backtest_logic

# --- QUẢN LÝ WATCHLIST ---
WATCHLIST_FILE = "watchlist.txt"

def get_watchlist():
    """Đọc danh sách các mã coin từ file watchlist.txt."""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, "r") as f:
        symbols = [line.strip().upper() for line in f if line.strip()]
    return symbols

def save_watchlist(symbols):
    """Lưu danh sách các mã coin vào file watchlist.txt."""
    with open(WATCHLIST_FILE, "w") as f:
        for symbol in sorted(symbols):
            f.write(f"{symbol}\n")

# --- CÁC HÀM XỬ LÝ LỆNH TỪ TELEGRAM ---

async def add_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Thêm một hoặc nhiều mã coin vào watchlist."""
    if not context.args:
        await update.message.reply_text("Vui lòng nhập ít nhất một mã coin. Ví dụ: /add BTCUSDT ETHUSDT")
        return

    watchlist = get_watchlist()
    added_symbols = []
    for symbol in context.args:
        symbol = symbol.upper()
        if symbol not in watchlist:
            watchlist.append(symbol)
            added_symbols.append(symbol)
    
    if added_symbols:
        save_watchlist(watchlist)
        await update.message.reply_text(f"Đã thêm thành công: {', '.join(added_symbols)}")
    else:
        await update.message.reply_text("Các mã coin này đã có trong danh sách.")

async def remove_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xóa một hoặc nhiều mã coin khỏi watchlist."""
    if not context.args:
        await update.message.reply_text("Vui lòng nhập ít nhất một mã coin để xóa. Ví dụ: /remove SOLUSDT")
        return

    watchlist = get_watchlist()
    removed_symbols, not_found_symbols = [], []
    for symbol in context.args:
        symbol = symbol.upper()
        if symbol in watchlist:
            watchlist.remove(symbol)
            removed_symbols.append(symbol)
        else:
            not_found_symbols.append(symbol)
            
    if removed_symbols:
        save_watchlist(watchlist)
        message = f"Đã xóa thành công: {', '.join(removed_symbols)}"
        if not_found_symbols:
            message += f"\nKhông tìm thấy: {', '.join(not_found_symbols)}"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("Không tìm thấy các mã coin này trong danh sách.")

async def list_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hiển thị danh sách các mã coin đang được theo dõi."""
    watchlist = get_watchlist()
    if not watchlist:
        message = "Danh sách theo dõi đang trống."
    else:
        message = "<b>Danh sách các mã coin đang được theo dõi:</b>\n\n"
        symbols_list = "\n".join([f"• <code>{symbol}</code>" for symbol in watchlist])
        message += symbols_list
    
    await update.message.reply_text(message, parse_mode='HTML')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gửi tin nhắn chào mừng."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Chào {user.mention_html()}, bot tín hiệu đã sẵn sàng! Dùng /backtest để mô phỏng tín hiệu."
    )

# --- HÀM GỬI TÍN HIỆU (CẬP NHẬT FORMAT) ---

async def send_formatted_signal(bot: Bot, signal_data: dict):
    """
    Định dạng và gửi tín hiệu cuối cùng lên channel.
    """
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    
    original_time = datetime.fromtimestamp(signal_data['timestamp'] / 1000, tz=pytz.utc).astimezone(vietnam_tz)
    confirmation_time = datetime.fromtimestamp(signal_data.get('confirmation_timestamp', signal_data['timestamp']) / 1000, tz=pytz.utc).astimezone(vietnam_tz)

    signal_type_text = "Tín hiệu đảo chiều BUY/LONG" if 'LONG' in signal_data['type'] else "Tín hiệu đảo chiều BÁN/SHORT"
    signal_emoji = "🟢" if 'LONG' in signal_data['type'] else "🔴"
        
    message = (
        f"<b>🔶 Token:</b> <code>{signal_data['symbol']}</code>\n\n"
        f"<b>{signal_emoji} {signal_type_text}</b>\n\n"
        f"<b>⏰ Khung thời gian:</b> {signal_data.get('timeframe', 'N/A')}\n\n"
        f"<b>✏️ Giá xác nhận:</b> <code>{signal_data.get('confirmation_price', 0):.2f}</code>\n\n"
        f"<b>🔍 Tỷ lệ Win:</b> {signal_data.get('win_rate', 'N/A')}\n\n"
        f"---------------------------------\n"
        f"<i>Thời gian gốc: {original_time.strftime('%H:%M:%S %d-%m-%Y')}</i>\n\n"
        f"<i>Thời gian xác nhận: {confirmation_time.strftime('%H:%M:%S %d-%m-%Y')}</i>"
    )

    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='HTML')
        print(f"✅ Đã gửi tín hiệu cho {signal_data['symbol']} lên channel.")
    except Exception as e:
        print(f"❌ Gửi tín hiệu cho {signal_data['symbol']} thất bại: {e}")

# --- LỆNH BACKTEST MỚI ---
async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Chạy backtest và gửi các tín hiệu tìm được lên channel."""
    await update.message.reply_text("⏳ Bắt đầu quá trình backtest... Việc này có thể mất vài phút. Vui lòng chờ.")
    
    try:
        # Chạy logic backtest được import từ file backtester.py
        found_signals = await run_backtest_logic()
        
        if not found_signals:
            await update.message.reply_text("✅ Backtest hoàn tất. Không tìm thấy tín hiệu nào trong khoảng dữ liệu vừa qua.")
            return

        await update.message.reply_text(f"🔥 Tìm thấy {len(found_signals)} tín hiệu! Bắt đầu gửi lên channel...")

        # Gửi lần lượt từng tín hiệu
        for signal in found_signals:
            await send_formatted_signal(context.bot, signal)
            await asyncio.sleep(1) # Tạm dừng 1 giây giữa các tin nhắn để tránh spam

        await update.message.reply_text("✅ Backtest hoàn tất. Tất cả tín hiệu đã được gửi lên channel.")

    except Exception as e:
        print(f"Lỗi nghiêm trọng trong quá trình backtest: {e}")
        await update.message.reply_text(f" Rất tiếc, đã có lỗi xảy ra trong quá trình backtest: {e}")

