# backtester.py
import asyncio
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from trading_logic import (
    get_klines,
    calculate_stochastic,
    TIMEFRAME_M15,
    TIMEFRAME_H1,
    FRACTAL_PERIODS,
    CVD_PERIOD
)

# --- CẤU HÌNH BACKTEST ---
SYMBOLS_TO_TEST = ["BNBUSDT", "KMNOUSDT", "EIGENUSDT"]
CANDLE_LIMIT = 1500

# --- HÀM IN TÍN HIỆU ---
def print_signal(signal_data):
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
    print(f"    (Debug) Thời gian gốc: {original_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"    (Debug) Thời gian xác nhận: {confirmation_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"    (Debug) Giá tại gốc: {signal_data['price']:.2f}")
    print(f"    (Debug) Giá xác nhận: {signal_data.get('confirmation_price', 0.0):.4f}")
    print(f"    (Debug) Stoch M15: {signal_data.get('stoch_m15', 0):.2f} | Stoch H1: {signal_data.get('stoch_h1', 0):.2f}")
    print("==================================================")

# --- LOGIC BACKTEST TỐI ƯU HÓA ---

def find_all_divergences_optimized(df, timeframe):
    """
    Hàm tối ưu để tìm tất cả các tín hiệu phân kỳ trong một bộ dữ liệu lịch sử.
    """
    if len(df) < 50 + FRACTAL_PERIODS: return []

    # 1. Tính toán tất cả các chỉ báo MỘT LẦN
    price_range = df['high'] - df['low']
    df['delta'] = np.where(price_range > 0, df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range, 0)
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = ta.ema(df['delta'], length=CVD_PERIOD)
    df['ema50'] = ta.ema(df['close'], length=50)

    # 2. Tìm tất cả các điểm pivot hợp lệ MỘT LẦN
    up_fractals, down_fractals = [], []
    n = FRACTAL_PERIODS
    for i in range(n, len(df) - n):
        is_uptrend = df['close'].iloc[i - n] > df['ema50'].iloc[i - n]
        is_downtrend = df['close'].iloc[i - n] < df['ema50'].iloc[i - n]
        
        is_pivot_high = all(df['high'].iloc[i] >= df['high'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
        is_pivot_low = all(df['low'].iloc[i] <= df['low'].iloc[j] for j in range(i - n, i + n + 1) if j != i)

        if is_pivot_high and is_uptrend: up_fractals.append(i)
        if is_pivot_low and is_downtrend: down_fractals.append(i)

    signals = []
    
    # 3. Quét qua các pivot để tìm phân kỳ
    for i in range(1, len(up_fractals)):
        prev_idx, last_idx = up_fractals[i-1], up_fractals[i]
        if (last_idx - prev_idx) < 30 and (df['high'].iloc[last_idx] > df['high'].iloc[prev_idx]) and (df['cvd'].iloc[last_idx] < df['cvd'].iloc[prev_idx]) and (df['cvd'].iloc[last_idx] > 0 and df['cvd'].iloc[prev_idx] > 0):
            signals.append({'type': 'SHORT 📉', 'price': df['close'].iloc[last_idx], 'timestamp': df['timestamp'].iloc[last_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_idx + n], 'confirmation_price': df['close'].iloc[last_idx + n], 'timeframe': timeframe})

    for i in range(1, len(down_fractals)):
        prev_idx, last_idx = down_fractals[i-1], down_fractals[i]
        if (last_idx - prev_idx) < 30 and (df['low'].iloc[last_idx] < df['low'].iloc[prev_idx]) and (df['cvd'].iloc[last_idx] > df['cvd'].iloc[prev_idx]) and (df['cvd'].iloc[last_idx] < 0 and df['cvd'].iloc[prev_idx] < 0):
            signals.append({'type': 'LONG 📈', 'price': df['close'].iloc[last_idx], 'timestamp': df['timestamp'].iloc[last_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_idx + n], 'confirmation_price': df['close'].iloc[last_idx + n], 'timeframe': timeframe})
                
    return signals

async def run_backtest_logic():
    all_final_signals = []
    
    for symbol in SYMBOLS_TO_TEST:
        print(f"--- [Backtest] Đang xử lý mã {symbol} ---")
        m15_data_full, h1_data_full = await asyncio.gather(
            get_klines(symbol, TIMEFRAME_M15, limit=CANDLE_LIMIT),
            get_klines(symbol, TIMEFRAME_H1, limit=CANDLE_LIMIT)
        )
        if m15_data_full.empty or h1_data_full.empty: continue

        m15_data_full['stoch_k'] = calculate_stochastic(m15_data_full)
        h1_data_full['stoch_k'] = calculate_stochastic(h1_data_full)
        
        m15_data_full.set_index('timestamp', inplace=True)
        h1_data_full.set_index('timestamp', inplace=True)

        m15_signals = find_all_divergences_optimized(m15_data_full.copy().reset_index(), 'M15')
        
        for signal in m15_signals:
            try:
                stoch_m15_val = m15_data_full.loc[signal['confirmation_timestamp'], 'stoch_k']
                stoch_h1_val = h1_data_full.loc[h1_data_full.index <= signal['confirmation_timestamp'], 'stoch_k'].iloc[-1]
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
    
    return sorted(all_final_signals, key=lambda x: x['timestamp'])

async def main():
    print("--- Chạy Backtester ở chế độ Standalone ---")
    signals = await run_backtest_logic()
    for signal in signals:
        print_signal(signal)
    print(f"\n--- Hoàn tất Backtest. Đã tìm thấy tổng cộng {len(signals)} tín hiệu. ---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBacktest stopped by user.")

