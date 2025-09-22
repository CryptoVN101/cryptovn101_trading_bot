# bot_handler.py
import os
from datetime import datetime
import pytz
from telegram import Update, Bot
from telegram.ext import ContextTypes
from config import CHANNEL_ID

# --- QUẢN LÝ WATCHLIST ---
WATCHLIST_FILE = 'watchlist.txt'

def get_watchlist():
    """Đọc danh sách coin từ file."""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, 'r') as f:
        return [line.strip().upper() for line in f if line.strip()]

def save_watchlist(watchlist):
    """Lưu danh sách coin vào file."""
    with open(WATCHLIST_FILE, 'w') as f:
        for symbol in sorted(list(set(watchlist))): # Loại bỏ trùng lặp và sắp xếp
            f.write(symbol + '\n')

# --- CÁC HÀM XỬ LÝ LỆNH TỪ TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gửi tin nhắn chào mừng khi người dùng gõ lệnh /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Chào {user.mention_html()}, bot tín hiệu đã sẵn sàng!",
    )

async def add_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Thêm một hoặc nhiều mã coin vào watchlist."""
    if not context.args:
        await update.message.reply_text("Vui lòng nhập mã coin. Ví dụ: /add BTCUSDT ETHUSDT")
        return
    
    watchlist = get_watchlist()
    added = []
    for symbol in context.args:
        if symbol.upper() not in watchlist:
            watchlist.append(symbol.upper())
            added.append(symbol.upper())
    
    if added:
        save_watchlist(watchlist)
        await update.message.reply_text(f"Đã thêm: {', '.join(added)}")
    else:
        await update.message.reply_text("Các mã này đã có trong danh sách.")

async def remove_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xóa một hoặc nhiều mã coin khỏi watchlist."""
    if not context.args:
        await update.message.reply_text("Vui lòng nhập mã coin. Ví dụ: /remove BTCUSDT")
        return
        
    watchlist = get_watchlist()
    removed = []
    for symbol in context.args:
        if symbol.upper() in watchlist:
            watchlist.remove(symbol.upper())
            removed.append(symbol.upper())
    
    if removed:
        save_watchlist(watchlist)
        await update.message.reply_text(f"Đã xóa: {', '.join(removed)}")
    else:
        await update.message.reply_text("Không tìm thấy các mã này trong danh sách.")

async def list_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hiển thị danh sách các mã đang theo dõi."""
    watchlist = get_watchlist()
    if not watchlist:
        message = "Danh sách theo dõi đang trống."
    else:
        message = "*Danh sách các mã đang theo dõi:*\n"
        # Sửa lỗi MarkdownV2
        symbols_list = "\n".join([f"\\- `{s}`" for s in watchlist])
        message += symbols_list
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')


# --- CÁC HÀM GỬI TIN NHẮN TÍN HIỆU ---

async def send_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lệnh /signal để gửi tín hiệu thử nghiệm vào CHANNEL."""
    signal_message = "<b>🚀 TÍN HIỆU THỬ NGHIỆM CHANNEL 🚀</b>\n\n"
    signal_message += "<b>Cặp tiền:</b> ETH/USDT\n"
    signal_message += "<b>Lệnh:</b> 📈 LONG\n"
    signal_message += "<b>Giá vào:</b> $3,500"
    
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=signal_message, parse_mode='HTML')
        await update.message.reply_text("Đã gửi tín hiệu thử nghiệm vào channel!")
    except Exception as e:
        await update.message.reply_text(f"Gửi tín hiệu thất bại: {e}")

async def send_formatted_signal(bot: Bot, signal_data: dict):
    """Định dạng và gửi tín hiệu thật lên channel."""
    symbol = signal_data.get('symbol', 'N/A')
    signal_type = signal_data.get('type', 'N/A')
    price = signal_data.get('price', 0)
    win_rate = signal_data.get('win_rate', 'N/A')
    timestamp_ms = signal_data.get('timestamp')

    # CẬP NHẬT: Chuyển đổi timestamp sang giờ Việt Nam (UTC+7)
    try:
        utc_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=pytz.utc)
        vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        vietnam_time = utc_time.astimezone(vietnam_tz)
        time_str = vietnam_time.strftime('%H:%M:%S %d-%m-%Y')
    except Exception:
        time_str = "N/A"

    # Định dạng lại tin nhắn theo yêu cầu mới
    if 'LONG' in signal_type:
        signal_verb = 'BUY/LONG'
        emoji = '🔵'
    else:
        signal_verb = 'SELL/SHORT'
        emoji = '🔴'

    message = (
        f"{emoji} <b>Tín hiệu đảo chiều {signal_verb} - {symbol} - Khung M15</b>\n\n"
        f"<b>Giá kích hoạt:</b> ${price:,.2f}\n"
        f"<b>Tỉ lệ thắng:</b> {win_rate}\n"
        f"<b>Thời gian:</b> {time_str} (Giờ Việt Nam)"
    )
    
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='HTML')
        print(f"✅ Đã gửi tín hiệu {signal_type} cho {symbol} thành công!")
    except Exception as e:
        print(f"❌ Lỗi khi gửi tín hiệu cho {symbol}: {e}")

