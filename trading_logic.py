# trading_logic.py
import asyncio
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance import AsyncClient
from binance.exceptions import BinanceAPIException

# --- CẤU HÌNH ---
TIMEFRAME_M15 = AsyncClient.KLINE_INTERVAL_15MINUTE
TIMEFRAME_H1 = AsyncClient.KLINE_INTERVAL_1HOUR
FRACTAL_PERIODS = 4
CVD_PERIOD = 24
STOCH_K = 16
STOCH_SMOOTH_K = 16
STOCH_D = 8

# --- KẾT NỐI VÀ LẤY DỮ LIỆU ---

async def get_klines(symbol, interval, limit=300):
    """Lấy dữ liệu nến từ Binance, ưu tiên Futures và dự phòng Spot."""
    client = None
    try:
        client = await AsyncClient.create()
        klines = None
        try:
            klines = await client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except BinanceAPIException as e:
            if e.code == -1121:
                klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
            else:
                raise e
        
        if klines is None:
             raise ValueError("Could not retrieve klines from any market.")

        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        print(f"Lỗi khi lấy dữ liệu cho {symbol} trên khung {interval}: {e}")
        return pd.DataFrame()
    finally:
        if client:
            await client.close_connection()


# --- LOGIC TÍNH TOÁN CHỈ BÁO ---

def calculate_cvd_divergence(df):
    """
    [PHIÊN BẢN 7.0 - FINAL]
    Mô phỏng chính xác logic từ Pine Script, đặc biệt là cách lấy giá trị
    với độ trễ [n] sau khi tìm thấy pivot.
    """
    if len(df) < 50 + FRACTAL_PERIODS: return None

    n = FRACTAL_PERIODS
    # --- Bước 1: Tính toán các chỉ báo cơ bản ---
    price_range = df['high'] - df['low']
    df['delta'] = np.where(price_range > 0, df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range, 0)
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = ta.ema(df['delta'], length=CVD_PERIOD)
    df['ema50'] = ta.ema(df['close'], length=50)

    # --- Bước 2: Tìm tất cả các điểm pivot hợp lệ (đã lọc theo xu hướng) ---
    up_fractals = []
    down_fractals = []
    for i in range(n, len(df) - n):
        is_uptrend = df['close'].iloc[i - n] > df['ema50'].iloc[i - n]
        is_downtrend = df['close'].iloc[i - n] < df['ema50'].iloc[i - n]
        
        # Logic tìm pivot chính xác
        is_pivot_high = df['high'].iloc[i] == df['high'].iloc[i-n:i+n+1].max()
        is_pivot_low = df['low'].iloc[i] == df['low'].iloc[i-n:i+n+1].min()

        if is_pivot_high and is_uptrend: up_fractals.append(i)
        if is_pivot_low and is_downtrend: down_fractals.append(i)

    # --- Bước 3: Kiểm tra phân kỳ ---
    current_bar_index = len(df) - 1
    
    # Sử dụng một biến để lưu trữ tín hiệu, tránh trả về sớm
    signal = None

    # Kiểm tra Phân kỳ giảm (Bearish)
    if len(up_fractals) >= 2:
        # Tìm 2 pivot cuối cùng từ danh sách
        last_pivot_idx, prev_pivot_idx = up_fractals[-1], up_fractals[-2]
        
        # Áp dụng độ trễ [n] để lấy giá trị cần so sánh
        last_val_idx = last_pivot_idx - n
        prev_val_idx = prev_pivot_idx - n
        
        if (current_bar_index - last_pivot_idx) < 30 :
            High_Last_Price = df['high'].iloc[last_val_idx]
            High_Per_Price = df['high'].iloc[prev_val_idx]
            High_Last_Hist = df['cvd'].iloc[last_val_idx]
            High_Per_Hist = df['cvd'].iloc[prev_val_idx]

            if (High_Last_Price > High_Per_Price) and (High_Last_Hist < High_Per_Hist) and \
               (High_Last_Hist > 0 and High_Per_Hist > 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'SHORT 📉', 
                          'price': df['close'].iloc[last_pivot_idx], 
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n],
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}

    # Kiểm tra Phân kỳ tăng (Bullish)
    if len(down_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = down_fractals[-1], down_fractals[-2]

        # Áp dụng độ trễ [n]
        last_val_idx = last_pivot_idx - n
        prev_val_idx = prev_pivot_idx - n

        if (current_bar_index - last_pivot_idx) < 30:
            Low_Last_Price = df['low'].iloc[last_val_idx]
            Low_Per_Price = df['low'].iloc[prev_val_idx]
            Low_Last_Hist = df['cvd'].iloc[last_val_idx]
            Low_Per_Hist = df['cvd'].iloc[prev_val_idx]

            if (Low_Last_Price < Low_Per_Price) and (Low_Last_Hist > Low_Per_Hist) and \
               (Low_Last_Hist < 0 and Low_Per_Hist < 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'LONG 📈', 
                          'price': df['close'].iloc[last_pivot_idx], 
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n],
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    
    return signal

def calculate_stochastic(df):
    if df.empty: return None
    # Thêm .reset_index() để đảm bảo Stoch được tính trên index tuần tự
    df_reset = df.reset_index(drop=True)
    stoch = df_reset.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        # Gán lại index cũ để có thể tra cứu bằng timestamp
        stoch.index = df.index
        return stoch[f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    return None

# --- BỘ MÁY QUÉT TÍN HIỆU ---

async def run_signal_checker(bot):
    print("🚀 Signal checker is running...")
    from bot_handler import get_watchlist, send_formatted_signal 
    
    while True:
        now = datetime.now(pytz.utc)
        next_run_minute = (now.minute // 15 + 1) * 15
        if next_run_minute >= 60:
            next_run_time = now.replace(minute=0, second=5, microsecond=0) + timedelta(hours=1)
        else:
            next_run_time = now.replace(minute=next_run_minute, second=5, microsecond=0)
        
        sleep_duration = (next_run_time - now).total_seconds()
        
        if sleep_duration > 0:
            print(f"Next scan at {next_run_time.astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}. Sleeping for {sleep_duration:.0f} seconds.")
            await asyncio.sleep(sleep_duration)

        print(f"\n--- Waking up at {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')} to scan signals ---")
        watchlist = get_watchlist()
        if not watchlist:
            print("Watchlist is empty. Will check again on the next cycle.")
            continue
            
        for symbol in watchlist:
            # THÊM LOG MỚI
            print(f"   -> Scanning {symbol}...")
            try:
                m15_data, h1_data = await asyncio.gather(
                    get_klines(symbol, TIMEFRAME_M15),
                    get_klines(symbol, TIMEFRAME_H1)
                )

                if m15_data.empty or h1_data.empty: continue

                # Đặt timestamp làm index để tra cứu
                m15_data.set_index('timestamp', inplace=True)
                h1_data.set_index('timestamp', inplace=True)

                cvd_signal_m15 = calculate_cvd_divergence(m15_data.copy().reset_index())
                if not cvd_signal_m15: continue

                stoch_m15_series = calculate_stochastic(m15_data)
                stoch_h1_series = calculate_stochastic(h1_data)
                if stoch_m15_series is None or stoch_h1_series is None: continue
                
                # Lấy giá trị stoch tại thời điểm xác nhận
                confirmation_ts = cvd_signal_m15['confirmation_timestamp']
                
                try:
                    stoch_m15 = stoch_m15_series.loc[confirmation_ts]
                    stoch_h1_latest_before = stoch_h1_series[h1_data.index <= confirmation_ts]
                    stoch_h1 = stoch_h1_latest_before.iloc[-1] if not stoch_h1_latest_before.empty else None
                except KeyError:
                    # Bỏ qua nếu không tìm thấy chính xác timestamp (có thể do API lag)
                    continue

                if stoch_h1 is None: continue

                final_signal_message = None
                base_signal = {**cvd_signal_m15, 'symbol': symbol, 'timeframe': 'M15'}
                if cvd_signal_m15['type'] == 'LONG 📈':
                    if stoch_m15 < 20 and stoch_h1 > 25: 
                        final_signal_message = {**base_signal, 'win_rate': '60%'}
                    elif stoch_m15 < 20 and stoch_h1 < 25: 
                        final_signal_message = {**base_signal, 'win_rate': '80%'}
                elif cvd_signal_m15['type'] == 'SHORT 📉':
                    if stoch_m15 > 80 and stoch_h1 < 75: 
                        final_signal_message = {**base_signal, 'win_rate': '60%'}
                    elif stoch_m15 > 80 and stoch_h1 > 75: 
                        final_signal_message = {**base_signal, 'win_rate': '80%'}

                if final_signal_message:
                    await send_formatted_signal(bot, final_signal_message)

            except Exception as e:
                print(f"Lỗi không xác định khi xử lý mã {symbol}: {e}")
            await asyncio.sleep(3)

