# trading_logic.py
import asyncio
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance import AsyncClient

# --- CẤU HÌNH CHO CHỈ BÁO ---
TIMEFRAME_M15 = AsyncClient.KLINE_INTERVAL_15MINUTE
TIMEFRAME_H1 = AsyncClient.KLINE_INTERVAL_1HOUR
FRACTAL_PERIODS = 4
CVD_PERIOD = 21

# Cấu hình Stochastic
STOCH_K = 16
STOCH_D = 16
STOCH_SMOOTH_K = 8

# --- KẾT NỐI VÀ LẤY DỮ LIỆU ---

async def get_klines(symbol, interval, limit=200):
    """Lấy dữ liệu nến từ Binance."""
    client = None
    try:
        client = await AsyncClient.create()
        klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
        
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
    """Tính toán và phát hiện phân kỳ CVD."""
    if len(df) < CVD_PERIOD: return None

    price_range = df['high'] - df['low']
    df['delta'] = np.where(
        price_range > 0,
        df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range,
        0
    )
    
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = df['delta'].rolling(window=CVD_PERIOD).sum()
    
    df['pivot_high'] = df['high'].rolling(window=2*FRACTAL_PERIODS+1, center=True).max() == df['high']
    df['pivot_low'] = df['low'].rolling(window=2*FRACTAL_PERIODS+1, center=True).min() == df['low']
    
    pivot_highs = df[df['pivot_high']]
    pivot_lows = df[df['pivot_low']]
    
    signal = None

    if len(pivot_highs) >= 2:
        last_pivot = pivot_highs.iloc[-1]
        prev_pivot = pivot_highs.iloc[-2]
        price_higher_high = last_pivot['high'] > prev_pivot['high']
        cvd_lower_high = last_pivot['cvd'] < prev_pivot['cvd']
        if price_higher_high and cvd_lower_high:
            signal = {'type': 'SHORT 📉', 'price': last_pivot['close'], 'timestamp': last_pivot['timestamp']}

    if len(pivot_lows) >= 2:
        last_pivot = pivot_lows.iloc[-1]
        prev_pivot = pivot_lows.iloc[-2]
        price_lower_low = last_pivot['low'] < prev_pivot['low']
        cvd_higher_low = last_pivot['cvd'] > prev_pivot['cvd']
        if price_lower_low and cvd_higher_low:
            signal = {'type': 'LONG 📈', 'price': last_pivot['close'], 'timestamp': last_pivot['timestamp']}
    
    return signal

def calculate_stochastic(df):
    """Tính toán Stochastic Oscillator."""
    if df.empty: return None
    stoch = df.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        return stoch.iloc[-1][f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    return None

# --- BỘ MÁY QUÉT TÍN HIỆU ---

async def run_signal_checker(bot):
    """Vòng lặp chính để quét tín hiệu, sử dụng logic ngủ thông minh."""
    print("🚀 Signal checker is running with smart sleep logic...")
    from bot_handler import get_watchlist, send_formatted_signal 
    
    while True:
        # --- LOGIC NGỦ THÔNG MINH ---
        now = datetime.now(pytz.utc)
        # Tìm thời điểm bắt đầu của cây nến M15 tiếp theo
        next_run_minute = (now.minute // 15 + 1) * 15
        if next_run_minute >= 60:
            next_run_time = now.replace(minute=0, second=5, microsecond=0) + timedelta(hours=1)
        else:
            next_run_time = now.replace(minute=next_run_minute, second=5, microsecond=0)
        
        sleep_duration = (next_run_time - now).total_seconds()
        
        print(f"Next scan at {next_run_time.astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}. Sleeping for {sleep_duration:.0f} seconds.")
        await asyncio.sleep(sleep_duration)
        # --- KẾT THÚC LOGIC NGỦ ---

        print(f"\n--- Waking up at {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')} to scan signals ---")
        watchlist = get_watchlist()
        if not watchlist:
            print("Watchlist is empty. Will check again on the next cycle.")
            continue
            
        for symbol in watchlist:
            try:
                m15_data, h1_data = await asyncio.gather(
                    get_klines(symbol, TIMEFRAME_M15),
                    get_klines(symbol, TIMEFRAME_H1)
                )

                if m15_data.empty or h1_data.empty:
                    continue

                cvd_signal = calculate_cvd_divergence(m15_data)
                if not cvd_signal:
                    continue

                stoch_m15 = calculate_stochastic(m15_data)
                stoch_h1 = calculate_stochastic(h1_data)

                if stoch_m15 is None or stoch_h1 is None:
                    continue

                final_signal_message = None

                if cvd_signal['type'] == 'LONG 📈':
                    if stoch_m15 < 25 and stoch_h1 > 25:
                        final_signal_message = {**cvd_signal, 'symbol': symbol, 'win_rate': 'Trung bình'}
                    elif stoch_m15 < 25 and stoch_h1 < 25:
                        final_signal_message = {**cvd_signal, 'symbol': symbol, 'win_rate': 'Cao'}
                
                elif cvd_signal['type'] == 'SHORT 📉':
                    if stoch_m15 > 75 and stoch_h1 < 75:
                        final_signal_message = {**cvd_signal, 'symbol': symbol, 'win_rate': 'Trung bình'}
                    elif stoch_m15 > 75 and stoch_h1 > 75:
                        final_signal_message = {**cvd_signal, 'symbol': symbol, 'win_rate': 'Cao'}

                if final_signal_message:
                    await send_formatted_signal(bot, final_signal_message)

            except Exception as e:
                print(f"Lỗi không xác định khi xử lý mã {symbol}: {e}")

            await asyncio.sleep(5) # Thêm một khoảng nghỉ ngắn giữa các mã để tránh quá tải API

