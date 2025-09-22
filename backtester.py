# backtester.py
import asyncio
from datetime import datetime
import pytz
from trading_logic import (
    get_klines, 
    calculate_cvd_divergence, 
    calculate_stochastic,
    TIMEFRAME_M15,
    TIMEFRAME_H1
)
import pandas as pd

async def run_backtest(symbol='BTCUSDT', candles_to_check=1000):
    """
    Chạy backtest trên dữ liệu lịch sử để kiểm tra logic tín hiệu.
    """
    print(f"--- Bắt đầu Backtest cho mã {symbol} ---")
    print(f"Đang tải {candles_to_check} nến lịch sử M15 và H1...")

    try:
        m15_data_full, h1_data_full = await asyncio.gather(
            get_klines(symbol, TIMEFRAME_M15, limit=candles_to_check),
            get_klines(symbol, TIMEFRAME_H1, limit=candles_to_check)
        )
    except Exception as e:
        print(f"Lỗi khi tải dữ liệu ban đầu: {e}")
        return

    if m15_data_full.empty or h1_data_full.empty:
        print("Không thể tải dữ liệu. Vui lòng thử lại.")
        return

    print("Đã tải dữ liệu xong. Bắt đầu quét tín hiệu...")
    found_signals = 0
    last_signal_timestamp = None # BIẾN MỚI: Dùng để tránh tín hiệu trùng lặp

    for i in range(100, len(m15_data_full)):
        current_m15_data = m15_data_full.iloc[:i]
        current_timestamp = current_m15_data.iloc[-1]['timestamp']
        current_h1_data = h1_data_full[h1_data_full['timestamp'] <= current_timestamp]

        if current_h1_data.empty:
            continue
        
        cvd_signal = calculate_cvd_divergence(current_m15_data)
        if not cvd_signal:
            continue

        # SỬA LỖI: Chỉ xử lý nếu đây là một tín hiệu mới
        if cvd_signal['timestamp'] == last_signal_timestamp:
            continue

        stoch_m15 = calculate_stochastic(current_m15_data)
        stoch_h1 = calculate_stochastic(current_h1_data)

        if stoch_m15 is None or stoch_h1 is None:
            continue

        final_signal_message = None

        if cvd_signal['type'] == 'LONG 📈':
            if stoch_m15 < 25 and stoch_h1 > 25:
                final_signal_message = {**cvd_signal, 'win_rate': 'Trung bình'}
            elif stoch_m15 < 25 and stoch_h1 < 25:
                final_signal_message = {**cvd_signal, 'win_rate': 'Cao'}
        
        elif cvd_signal['type'] == 'SHORT 📉':
            if stoch_m15 > 75 and stoch_h1 < 75:
                final_signal_message = {**cvd_signal, 'win_rate': 'Trung bình'}
            elif stoch_m15 > 75 and stoch_h1 > 75:
                final_signal_message = {**cvd_signal, 'win_rate': 'Cao'}

        if final_signal_message:
            found_signals += 1
            last_signal_timestamp = final_signal_message.get('timestamp') # Cập nhật timestamp của tín hiệu cuối
            
            timestamp_ms = final_signal_message.get('timestamp')
            utc_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=pytz.utc)
            vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            vietnam_time = utc_time.astimezone(vietnam_tz)
            time_str = vietnam_time.strftime('%Y-%m-%d %H:%M:%S')

            print("\n==================================================")
            print("🔥 TÍN HIỆU ĐƯỢC TÌM THẤY 🔥")
            # CẬP NHẬT: Thêm tên mã coin
            print(f"    Mã Coin: {symbol}")
            print(f"    Thời gian: {time_str} (Giờ Việt Nam)")
            print(f"    Loại: {final_signal_message['type']}")
            print(f"    Giá: {final_signal_message['price']:.2f}")
            print(f"    Tỉ lệ: {final_signal_message['win_rate']}")
            print(f"    Stoch M15: {stoch_m15:.2f} | Stoch H1: {stoch_h1:.2f}")
            print("==================================================")

    if found_signals == 0:
        print(f"\n--- Hoàn tất Backtest cho {symbol}. Không tìm thấy tín hiệu nào. ---")
    else:
        print(f"\n--- Hoàn tất Backtest cho {symbol}. Đã tìm thấy tổng cộng {found_signals} tín hiệu. ---")


if __name__ == '__main__':
    # Bạn có thể đổi mã coin ở đây để test
    asyncio.run(run_backtest(symbol='ETHUSDT'))

