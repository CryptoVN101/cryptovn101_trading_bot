# backtester.py
import asyncio
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
from binance.async_client import AsyncClient

# Import hàm logic chung và các hằng số
from trading_logic import (
    calculate_stochastic,
    find_cvd_divergence_signals, # QUAN TRỌNG: Import hàm logic mới
    get_klines,
    TIMEFRAME_M15,
    TIMEFRAME_H1
)

# --- CẤU HÌNH BACKTEST ---
SYMBOLS_TO_TEST = ["EIGENUSDT", "BERAUSDT"] # Thêm các mã bạn muốn backtest
CANDLE_LIMIT = 1500

# --- HÀM IN TÍN HIỆU (Giữ nguyên) ---
def print_signal(signal_data):
    """In tín hiệu ra terminal với format hiển thị cả giá xác nhận."""
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    original_time = datetime.fromtimestamp(signal_data['timestamp'] / 1000, tz=pytz.utc).astimezone(vietnam_tz)
    confirmation_time = datetime.fromtimestamp(signal_data.get('confirmation_timestamp', signal_data['timestamp']) / 1000, tz=pytz.utc).astimezone(vietnam_tz)
    signal_type_text = "Tín hiệu đảo chiều BUY/LONG" if 'LONG' in signal_data['type'] else "Tín hiệu đảo chiều BÁN/SHORT"
    signal_emoji = "🟢" if 'LONG' in signal_data['type'] else "🔴"
    
    print("==================================================")
    print(f"🔥 TÍN HIỆU ĐƯỢC TÌM THẤY 🔥")
    print(f"    🪙 Token: {signal_data['symbol']}")
    print(f"    {signal_emoji} {signal_type_text}")
    print(f"    ⏰ Khung thời gian: {signal_data.get('timeframe', 'N/A')}")
    print(f"    🔍 Tỷ lệ Win: {signal_data.get('win_rate', 'N/A')}")
    print(f"    ---")
    print(f"    (Debug) Thời gian gốc: {original_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    (Debug) Thời gian xác nhận: {confirmation_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    (Debug) Giá tại gốc: {signal_data['price']:.4f}")
    print(f"    (Debug) Giá xác nhận: {signal_data.get('confirmation_price', 0):.4f}")
    print(f"    (Debug) Stoch M15: {signal_data.get('stoch_m15', 0):.2f} | Stoch H1: {signal_data.get('stoch_h1', 0):.2f}")
    print("==================================================")

# --- BỘ MÁY BACKTEST (Đơn giản hóa) ---
async def run_backtest_logic():
    all_final_signals = []

    for symbol in SYMBOLS_TO_TEST:
        print(f"--- [Backtest] Đang xử lý mã {symbol} ---")
        m15_data, h1_data = await asyncio.gather(
            get_klines(symbol, TIMEFRAME_M15, limit=CANDLE_LIMIT),
            get_klines(symbol, TIMEFRAME_H1, limit=CANDLE_LIMIT)
        )

        if m15_data.empty or h1_data.empty:
            print(f"--- [Backtest] Dữ liệu trống cho {symbol}, bỏ qua ---")
            continue

        # 1. GỌI HÀM LOGIC CHUNG ĐỂ TÌM TÍN HIỆU THÔ
        m15_signals = find_cvd_divergence_signals(m15_data.copy())
        if not m15_signals:
            continue
            
        print(f"--- [Backtest] Tìm thấy {len(m15_signals)} tín hiệu thô cho {symbol}. Bắt đầu lọc...")

        # 2. TÍNH TOÁN STOCH VÀ ÁP DỤNG BỘ LỌC
        m15_data['stoch_k'] = calculate_stochastic(m15_data)
        h1_data['stoch_k'] = calculate_stochastic(h1_data)
        
        m15_data.set_index('timestamp', inplace=True)
        h1_data.set_index('timestamp', inplace=True)
        
        for signal in m15_signals:
            try:
                stoch_m15_val = m15_data.loc[signal['timestamp'], 'stoch_k']
                stoch_h1_val = h1_data.loc[h1_data.index <= signal['timestamp'], 'stoch_k'].iloc[-1]
            except (KeyError, IndexError):
                continue

            base_signal = {**signal, 'symbol': symbol, 'stoch_m15': stoch_m15_val, 'stoch_h1': stoch_h1_val}
            final_signal = None
            if signal['type'] == 'LONG 📈' and stoch_m15_val < 20:
                if stoch_h1_val > 25: final_signal = {**base_signal, 'win_rate': '60%'}
                elif stoch_h1_val < 25: final_signal = {**base_signal, 'win_rate': '80%'}
            elif signal['type'] == 'SHORT 📉' and stoch_m15_val > 80:
                if stoch_h1_val < 75: final_signal = {**base_signal, 'win_rate': '60%'}
                elif stoch_h1_val > 75: final_signal = {**base_signal, 'win_rate': '80%'}
            
            if final_signal:
                all_final_signals.append(final_signal)
    
    return all_final_signals

# --- KHỐI CHẠY CHÍNH (Giữ nguyên) ---
async def main():
    print("--- Chạy Backtester ở chế độ Standalone ---")
    signals = await run_backtest_logic()
    if signals:
        for signal in signals:
            print_signal(signal)
    print(f"\n--- Hoàn tất Backtest. Đã tìm thấy tổng cộng {len(signals)} tín hiệu. ---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBacktest stopped by user.")