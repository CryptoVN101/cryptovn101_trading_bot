# trading_logic.py
import asyncio
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance.async_client import AsyncClient
from binance.exceptions import BinanceAPIException
from database import get_watchlist_from_db

# --- CẤU HÌNH ---
TIMEFRAME_M15 = AsyncClient.KLINE_INTERVAL_15MINUTE
TIMEFRAME_H1 = AsyncClient.KLINE_INTERVAL_1HOUR
FRACTAL_PERIODS = 4
CVD_PERIOD = 24
STOCH_K = 16
STOCH_SMOOTH_K = 16
STOCH_D = 8
SCAN_DELAY_SECONDS = 15

# <<< SỬA ĐỔI Ở ĐÂY: Tăng giới hạn dữ liệu để ổn định chỉ báo >>>
LIVE_CANDLE_LIMIT = 1000
BACKTEST_CANDLE_LIMIT = 1500


# --- CÁC HÀM TIỆN ÍCH (KHÔNG ĐỔI) ---
async def get_klines(symbol, interval, limit=300): # Mặc định vẫn là 300
    # ... (giữ nguyên code của hàm này) ...
    client = None
    try:
        client = await AsyncClient.create()
        klines = None
        try:
            klines = await client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except BinanceAPIException as e:
            if e.code == -1121:
                print(f"'{symbol}' không tìm thấy trên Futures, thử trên Spot...")
                klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
            else: raise e
        if klines is None: raise ValueError("Không thể lấy dữ liệu nến từ bất kỳ thị trường nào.")
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        numeric_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
        return df
    except Exception as e:
        print(f"Lỗi khi lấy dữ liệu cho {symbol} trên khung {interval}: {e}")
        return pd.DataFrame()
    finally:
        if client: await client.close_connection()

def calculate_stochastic(df):
    # ... (giữ nguyên code của hàm này) ...
    if df.empty: return None
    df_reset = df.reset_index(drop=True) if 'timestamp' in df.index.names else df.copy()
    stoch = df_reset.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        return stoch[f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    return None

# --- LOGIC TÌM TÍN HIỆU (KHÔNG ĐỔI) ---
def find_all_signals_for_backtest(df: pd.DataFrame):
    # ... (giữ nguyên code của hàm này) ...
    n = FRACTAL_PERIODS
    if len(df) < 50 + n: return []
    price_range = df['high'] - df['low']
    df['delta'] = np.where(price_range > 0, df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range, 0)
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = ta.ema(df['delta'], length=CVD_PERIOD)
    df['ema50'] = ta.ema(df['close'], length=50)
    up_fractals, down_fractals = [], []
    for i in range(n, len(df) - n):
        is_uptrend = df['close'].iloc[i] > df['ema50'].iloc[i]
        is_downtrend = df['close'].iloc[i] < df['ema50'].iloc[i]
        is_pivot_high = df['high'].iloc[i] >= df['high'].iloc[i-n:i+n+1].max()
        is_pivot_low = df['low'].iloc[i] <= df['low'].iloc[i-n:i+n+1].min()
        if is_pivot_high and is_uptrend: up_fractals.append(i)
        if is_pivot_low and is_downtrend: down_fractals.append(i)
    all_signals = []
    for i in range(1, len(up_fractals)):
        last_pivot_idx, prev_pivot_idx = up_fractals[i], up_fractals[i-1]
        if (df['high'].iloc[last_pivot_idx] > df['high'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] < df['cvd'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] > 0 and df['cvd'].iloc[prev_pivot_idx] > 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
            all_signals.append({'type': 'SHORT 📉', 'price': df['close'].iloc[last_pivot_idx], 'timestamp': df['timestamp'].iloc[last_pivot_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 'confirmation_price': df['close'].iloc[last_pivot_idx + n], 'timeframe': 'M15'})
    for i in range(1, len(down_fractals)):
        last_pivot_idx, prev_pivot_idx = down_fractals[i], down_fractals[i-1]
        if (df['low'].iloc[last_pivot_idx] < df['low'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] > df['cvd'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] < 0 and df['cvd'].iloc[prev_pivot_idx] < 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
            all_signals.append({'type': 'LONG 📈', 'price': df['close'].iloc[last_pivot_idx], 'timestamp': df['timestamp'].iloc[last_pivot_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 'confirmation_price': df['close'].iloc[last_pivot_idx + n], 'timeframe': 'M15'})
    return all_signals

def find_latest_confirmed_signal(df: pd.DataFrame):
    # ... (giữ nguyên code của hàm này) ...
    n = FRACTAL_PERIODS
    if len(df) < 50 + n: return None
    price_range = df['high'] - df['low']
    df['delta'] = np.where(price_range > 0, df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range, 0)
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = ta.ema(df['delta'], length=CVD_PERIOD)
    df['ema50'] = ta.ema(df['close'], length=50)
    up_fractals, down_fractals = [], []
    for i in range(n, len(df) - n):
        is_uptrend = df['close'].iloc[i] > df['ema50'].iloc[i]
        is_downtrend = df['close'].iloc[i] < df['ema50'].iloc[i]
        is_pivot_high = df['high'].iloc[i] >= df['high'].iloc[i-n:i+n+1].max()
        is_pivot_low = df['low'].iloc[i] <= df['low'].iloc[i-n:i+n+1].min()
        if is_pivot_high and is_uptrend: up_fractals.append(i)
        if is_pivot_low and is_downtrend: down_fractals.append(i)
    signal = None
    if len(up_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = up_fractals[-1], up_fractals[-2]
        if (last_pivot_idx + n) == (len(df) - 1):
            if (df['high'].iloc[last_pivot_idx] > df['high'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] < df['cvd'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] > 0 and df['cvd'].iloc[prev_pivot_idx] > 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'SHORT 📉', 'price': df['close'].iloc[last_pivot_idx], 'timestamp': df['timestamp'].iloc[last_pivot_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 'confirmation_price': df['close'].iloc[last_pivot_idx + n], 'timeframe': 'M15'}
    if not signal and len(down_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = down_fractals[-1], down_fractals[-2]
        if (last_pivot_idx + n) == (len(df) - 1):
            if (df['low'].iloc[last_pivot_idx] < df['low'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] > df['cvd'].iloc[prev_pivot_idx]) and (df['cvd'].iloc[last_pivot_idx] < 0 and df['cvd'].iloc[prev_pivot_idx] < 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'LONG 📈', 'price': df['close'].iloc[last_pivot_idx], 'timestamp': df['timestamp'].iloc[last_pivot_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 'confirmation_price': df['close'].iloc[last_pivot_idx + n], 'timeframe': 'M15'}
    return signal

# --- BỘ QUÉT TÍN HIỆU LIVE (SỬA LỖI) ---
async def run_signal_checker(bot):
    from bot_handler import send_formatted_signal
    print("🚀 Signal checker is running with FINAL combined logic...")
    processed_signals = set()
    while True:
        now = datetime.now(pytz.utc)
        next_run_minute = (now.minute // 15 + 1) * 15
        if next_run_minute >= 60:
            next_run_time = now.replace(minute=0, second=SCAN_DELAY_SECONDS, microsecond=0) + timedelta(hours=1)
        else:
            next_run_time = now.replace(minute=next_run_minute, second=SCAN_DELAY_SECONDS, microsecond=0)
        sleep_duration = (next_run_time - now).total_seconds()
        if sleep_duration > 0:
            print(f"Next scan at {next_run_time.astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}. Sleeping for {sleep_duration:.0f} seconds.")
            await asyncio.sleep(sleep_duration)
        print(f"\n--- Waking up at {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')} to scan signals ---")
        watchlist = await get_watchlist_from_db()
        if not watchlist:
            print("Watchlist is empty. Will check again on the next cycle.")
            continue
        for symbol in watchlist:
            print(f"   -> Scanning {symbol}...")
            try:
                # <<< SỬA ĐỔI Ở ĐÂY: Sử dụng hằng số LIVE_CANDLE_LIMIT >>>
                m15_data_raw, h1_data_raw = await asyncio.gather(
                    get_klines(symbol, TIMEFRAME_M15, limit=LIVE_CANDLE_LIMIT),
                    get_klines(symbol, TIMEFRAME_H1, limit=LIVE_CANDLE_LIMIT)
                )
                if m15_data_raw.empty or h1_data_raw.empty: continue
                recent_signal = find_latest_confirmed_signal(m15_data_raw.copy())
                if not recent_signal: continue
                signal_id = f"{symbol}_{recent_signal['timestamp']}"
                if signal_id in processed_signals: 
                    print(f"      - Signal for {symbol} at pivot {datetime.fromtimestamp(recent_signal['timestamp']/1000).strftime('%H:%M')} already processed. Skipping.")
                    continue
                print(f"      🔥 Found a confirmed signal for {symbol}! Pivot at {datetime.fromtimestamp(recent_signal['timestamp']/1000, tz=pytz.utc).astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M %d-%m')}, Confirmed at {datetime.fromtimestamp(recent_signal['confirmation_timestamp']/1000, tz=pytz.utc).astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M %d-%m')}")
                m15_data_raw['stoch_k'] = calculate_stochastic(m15_data_raw)
                h1_data_raw['stoch_k'] = calculate_stochastic(h1_data_raw)
                m15_data_raw.set_index('timestamp', inplace=True)
                h1_data_raw.set_index('timestamp', inplace=True)
                try:
                    stoch_m15_val = m15_data_raw.loc[recent_signal['confirmation_timestamp'], 'stoch_k']
                    stoch_h1_val = h1_data_raw.loc[h1_data_raw.index <= recent_signal['confirmation_timestamp'], 'stoch_k'].iloc[-1]
                except (KeyError, IndexError): continue
                base_signal = {**recent_signal, 'symbol': symbol, 'stoch_m15': stoch_m15_val, 'stoch_h1': stoch_h1_val}
                final_signal = None
                if base_signal['type'] == 'LONG 📈' and stoch_m15_val < 20:
                    if stoch_h1_val > 25: final_signal = {**base_signal, 'win_rate': '60%'}
                    elif stoch_h1_val < 25: final_signal = {**base_signal, 'win_rate': '80%'}
                elif base_signal['type'] == 'SHORT 📉' and stoch_m15_val > 80:
                    if stoch_h1_val < 75: final_signal = {**base_signal, 'win_rate': '60%'}
                    elif stoch_h1_val > 75: final_signal = {**base_signal, 'win_rate': '80%'}
                if final_signal:
                    await send_formatted_signal(bot, final_signal)
                    processed_signals.add(signal_id)
            except Exception as e:
                print(f"Error processing {symbol}: {e}", exc_info=True)
            await asyncio.sleep(2)