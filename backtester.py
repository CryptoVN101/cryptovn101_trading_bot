# backtester.py
import asyncio
from datetime import datetime
import pytz
import pandas as pd
from trading_logic import (
    get_klines,
    calculate_stochastic,
    calculate_cvd_divergence, # SỬ DỤNG CÙNG MỘT HÀM
    TIMEFRAME_M15,
    TIMEFRAME_H1
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

# --- BỘ MÁY BACKTEST MÔ PHỎNG REAL-TIME ---
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

        last_signal_ts = 0
        
        # Mô phỏng vòng lặp của bot real-time
        for i in range(300, len(m15_data_full)):
            df_slice_m15 = m15_data_full.iloc[:i]
            
            # SỬ DỤNG CHUNG HÀM TÍNH TOÁN
            cvd_signal = calculate_cvd_divergence(df_slice_m15.copy().reset_index())
            
            if cvd_signal and cvd_signal['timestamp'] != last_signal_ts:
                try:
                    stoch_m15_val = m15_data_full.loc[cvd_signal['confirmation_timestamp'], 'stoch_k']
                    stoch_h1_val = h1_data_full.loc[h1_data_full.index <= cvd_signal['confirmation_timestamp'], 'stoch_k'].iloc[-1]
                except (KeyError, IndexError):
                    continue

                base_signal = {**cvd_signal, 'symbol': symbol, 'timeframe': 'M15', 'stoch_m15': stoch_m15_val, 'stoch_h1': stoch_h1_val}
                final_signal = None
                
                if cvd_signal['type'] == 'LONG 📈' and stoch_m15_val < 20:
                    if stoch_h1_val > 25: final_signal = {**base_signal, 'win_rate': '60%'}
                    elif stoch_h1_val < 25: final_signal = {**base_signal, 'win_rate': '80%'}
                elif cvd_signal['type'] == 'SHORT 📉' and stoch_m15_val > 80:
                    if stoch_h1_val < 75: final_signal = {**base_signal, 'win_rate': '60%'}
                    elif stoch_h1_val > 75: final_signal = {**base_signal, 'win_rate': '80%'}
                
                if final_signal:
                    all_final_signals.append(final_signal)
                    last_signal_ts = cvd_signal['timestamp'] # Ghi nhớ tín hiệu đã tìm thấy
    
    return all_final_signals

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

