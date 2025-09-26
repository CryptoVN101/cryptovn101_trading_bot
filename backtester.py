import asyncio
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance.async_client import AsyncClient
from trading_logic import (
    calculate_stochastic,
    TIMEFRAME_M15,
    TIMEFRAME_H1,
    FRACTAL_PERIODS,
    CVD_PERIOD
)

# --- CẤU HÌNH BACKTEST ---
SYMBOLS_TO_TEST = ["BERAUSDT"]  # Thêm các mã bạn muốn backtest
CANDLE_LIMIT = 1500

# --- HÀM IN TÍN HIỆU (CẬP NHẬT FORMAT) ---
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
    print(f"    (Debug) Giá tại gốc: {signal_data['price']:.2f}")
    print(f"    (Debug) Giá xác nhận: {signal_data.get('confirmation_price', 0):.4f}")
    print(f"    (Debug) Stoch M15: {signal_data.get('stoch_m15', 0):.2f} | Stoch H1: {signal_data.get('stoch_h1', 0):.2f}")
    print("==================================================")

# --- HÀM LẤY DỮ LIỆU (TẠM THỜI LẤY TỪ TRADING_LOGIC) ---
async def get_klines_wrapper(symbol, interval, limit=CANDLE_LIMIT):
    """Wrapper để gọi get_klines từ trading_logic với client được khởi tạo trong hàm."""
    from trading_logic import get_klines
    client = await AsyncClient.create()
    try:
        return await get_klines(symbol, interval, client, limit=limit)
    finally:
        if client and not client.session.closed:
            await client.close_connection()

# --- BỘ MÁY BACKTEST ---
async def run_backtest_logic():
    """
    Chạy logic backtest và trả về một danh sách các tín hiệu hợp lệ.
    """
    all_final_signals = []

    for symbol in SYMBOLS_TO_TEST:
        print(f"--- [Backtest] Đang xử lý mã {symbol} ---")
        m15_data, h1_data = await asyncio.gather(
            get_klines_wrapper(symbol, TIMEFRAME_M15),
            get_klines_wrapper(symbol, TIMEFRAME_H1)
        )

        if m15_data.empty or h1_data.empty:
            print(f"--- [Backtest] Dữ liệu trống cho {symbol}, bỏ qua ---")
            continue

        m15_data['stoch_k'] = calculate_stochastic(m15_data)
        h1_data['stoch_k'] = calculate_stochastic(h1_data)
        
        # Logic tìm phân kỳ
        if len(m15_data) < 50 + FRACTAL_PERIODS:
            print(f"--- [Backtest] Dữ liệu không đủ cho {symbol}, bỏ qua ---")
            continue

        price_range = m15_data['high'] - m15_data['low']
        m15_data['delta'] = np.where(price_range > 0, m15_data['volume'] * (2 * m15_data['close'] - m15_data['low'] - m15_data['high']) / price_range, 0)
        m15_data['delta'] = m15_data['delta'].fillna(0)
        m15_data['cvd'] = ta.ema(m15_data['delta'], length=CVD_PERIOD)
        m15_data['ema50'] = ta.ema(m15_data['close'], length=50)

        up_fractals, down_fractals = [], []
        n = FRACTAL_PERIODS
        for i in range(n, len(m15_data) - n):
            is_uptrend = m15_data['close'].iloc[i - n] > m15_data['ema50'].iloc[i - n]
            is_downtrend = m15_data['close'].iloc[i - n] < m15_data['ema50'].iloc[i - n]
            is_pivot_high = all(m15_data['high'].iloc[i] >= m15_data['high'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
            is_pivot_low = all(m15_data['low'].iloc[i] <= m15_data['low'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
            if is_pivot_high and is_uptrend: up_fractals.append(i)
            if is_pivot_low and is_downtrend: down_fractals.append(i)

        m15_signals = []
        for i in range(1, len(up_fractals)):
            prev_idx, last_idx = up_fractals[i-1], up_fractals[i]
            if (last_idx - prev_idx) < 30 and (m15_data['high'].iloc[last_idx] > m15_data['high'].iloc[prev_idx]) and (m15_data['cvd'].iloc[last_idx] < m15_data['cvd'].iloc[prev_idx]) and (m15_data['cvd'].iloc[last_idx] > 0 and m15_data['cvd'].iloc[prev_idx] > 0):
                m15_signals.append({'type': 'SHORT 📉', 'price': m15_data['close'].iloc[last_idx], 'timestamp': m15_data['timestamp'].iloc[last_idx], 'confirmation_timestamp': m15_data['timestamp'].iloc[last_idx + n], 'confirmation_price': m15_data['close'].iloc[last_idx + n], 'timeframe': 'M15'})
        for i in range(1, len(down_fractals)):
            prev_idx, last_idx = down_fractals[i-1], down_fractals[i]
            if (last_idx - prev_idx) < 30 and (m15_data['low'].iloc[last_idx] < m15_data['low'].iloc[prev_idx]) and (m15_data['cvd'].iloc[last_idx] > m15_data['cvd'].iloc[prev_idx]) and (m15_data['cvd'].iloc[last_idx] < 0 and m15_data['cvd'].iloc[prev_idx] < 0):
                m15_signals.append({'type': 'LONG 📈', 'price': m15_data['close'].iloc[last_idx], 'timestamp': m15_data['timestamp'].iloc[last_idx], 'confirmation_timestamp': m15_data['timestamp'].iloc[last_idx + n], 'confirmation_price': m15_data['close'].iloc[last_idx + n], 'timeframe': 'M15'})

        # Áp dụng điều kiện Stoch
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

async def main():
    """Hàm main để chạy backtester từ command line hoặc bot."""
    print("--- Chạy Backtester ở chế độ Standalone ---")
    signals = await run_backtest_logic()
    for signal in signals:
        print_signal(signal)
    print(f"\n--- Hoàn tất Backtest. Đã tìm thấy tổng cộng {len(signals)} tín hiệu. ---")

# --- KHỞI TẠO CLIENT CHO BACKTEST ---
async def run_backtest():
    """Khởi tạo client và chạy backtest."""
    client = await AsyncClient.create()
    try:
        await main()
    finally:
        if client and not client.session.closed:
            await client.close_connection()
            print("Đã đóng kết nối client.")

if __name__ == "__main__":
    try:
        asyncio.run(run_backtest())
    except KeyboardInterrupt:
        print("\nBacktest stopped by user.")