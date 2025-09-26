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
FRACTAL_PERIODS = 2
CVD_PERIOD = 24
STOCH_K = 16
STOCH_SMOOTH_K = 16
STOCH_D = 8
# <<< THÊM HẰNG SỐ MỚI TẠI ĐÂY >>>
# Số giây chờ sau khi nến đóng cửa trước khi quét
SCAN_DELAY_SECONDS = 10 

# --- KẾT NỐI VÀ LẤY DỮ LIỆU (Không đổi) ---
async def get_klines(symbol, interval, limit=300):
    # ... (giữ nguyên code của hàm này) ...
    client = None
    try:
        client = await AsyncClient.create()
        klines = None
        try:
            klines = await client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except BinanceAPIException as e:
            if e.code == -1121: # Lỗi "Invalid symbol" cho Futures
                print(f"'{symbol}' không tìm thấy trên Futures, thử trên Spot...")
                klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
            else:
                raise e
        
        if klines is None:
            raise ValueError("Không thể lấy dữ liệu nến từ bất kỳ thị trường nào.")

        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        numeric_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
        return df
    except Exception as e:
        print(f"Lỗi khi lấy dữ liệu cho {symbol} trên khung {interval}: {e}")
        return pd.DataFrame()
    finally:
        if client:
            await client.close_connection()

# --- CÁC HÀM TÍNH TOÁN (Không đổi) ---
def calculate_stochastic(df):
    # ... (giữ nguyên code của hàm này) ...
    if df.empty: return None
    df_reset = df.reset_index(drop=True) if 'timestamp' in df.index.names else df.copy()
    stoch = df_reset.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        return stoch[f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    return None

# --- LOGIC "CHUẨN" (Không đổi) ---
def find_cvd_divergence_signals(m15_data: pd.DataFrame):
    # ... (giữ nguyên code của hàm này) ...
    if len(m15_data) < 50 + FRACTAL_PERIODS:
        return []
    # ... (phần còn lại của logic tìm tín hiệu giữ nguyên)
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
        is_pivot_high = m15_data['high'].iloc[i] >= m15_data['high'].iloc[i-n:i+n+1].max()
        is_pivot_low = m15_data['low'].iloc[i] <= m15_data['low'].iloc[i-n:i+n+1].min()
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
    return m15_signals


# --- BỘ QUÉT TÍN HIỆU LIVE ---
async def run_signal_checker(bot):
    from bot_handler import send_formatted_signal

    print("🚀 Signal checker is running with updated logic...")
    processed_signals = set()

    while True:
        watchlist = await get_watchlist_from_db()
        print(f"Current watchlist contains {len(watchlist)} symbol(s): {', '.join(watchlist) if watchlist else 'None'}")
        
        now = datetime.now(pytz.utc)
        next_run_minute = (now.minute // 15 + 1) * 15
        
        # <<< THAY ĐỔI Ở ĐÂY: Sử dụng hằng số SCAN_DELAY_SECONDS >>>
        if next_run_minute >= 60:
            next_run_time = now.replace(minute=0, second=SCAN_DELAY_SECONDS, microsecond=0) + timedelta(hours=1)
        else:
            next_run_time = now.replace(minute=next_run_minute, second=SCAN_DELAY_SECONDS, microsecond=0)
        
        sleep_duration = (next_run_time - now).total_seconds()
        
        if sleep_duration > 0:
            print(f"Next scan at {next_run_time.astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}. Sleeping for {sleep_duration:.0f} seconds.")
            await asyncio.sleep(sleep_duration)

        print(f"\n--- Waking up at {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')} to scan signals ---")
        
        # Lấy lại watchlist một lần nữa phòng trường hợp có thay đổi trong lúc bot ngủ
        watchlist = await get_watchlist_from_db()
        if not watchlist:
            print("Watchlist is empty. Will check again on the next cycle.")
            continue
            
        for symbol in watchlist:
            # ... (giữ nguyên logic quét của vòng lặp for) ...
            print(f"   -> Scanning {symbol}...")
            try:
                m15_data_raw, h1_data_raw = await asyncio.gather(
                    get_klines(symbol, TIMEFRAME_M15, limit=300),
                    get_klines(symbol, TIMEFRAME_H1, limit=300)
                )

                if m15_data_raw.empty or h1_data_raw.empty:
                    print(f"      - Data empty for {symbol}, skipping.")
                    continue

                m15_base_signals = find_cvd_divergence_signals(m15_data_raw.copy())
                if not m15_base_signals:
                    continue
                
                last_candle_timestamp = m15_data_raw['timestamp'].iloc[-2]
                recent_signal = None
                for sig in reversed(m15_base_signals):
                    if sig['timestamp'] == last_candle_timestamp:
                         recent_signal = sig
                         break
                
                if not recent_signal:
                    continue

                signal_id = f"{symbol}_{recent_signal['timestamp']}"
                if signal_id in processed_signals:
                    continue
                
                print(f"      🔥 Found a potential signal for {symbol} at {datetime.fromtimestamp(recent_signal['timestamp']/1000, tz=pytz.utc).astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M %d-%m-%Y')}")

                m15_data_raw['stoch_k'] = calculate_stochastic(m15_data_raw)
                h1_data_raw['stoch_k'] = calculate_stochastic(h1_data_raw)
                
                m15_data_raw.set_index('timestamp', inplace=True)
                h1_data_raw.set_index('timestamp', inplace=True)

                try:
                    stoch_m15_val = m15_data_raw.loc[recent_signal['timestamp'], 'stoch_k']
                    stoch_h1_val = h1_data_raw.loc[h1_data_raw.index <= recent_signal['timestamp'], 'stoch_k'].iloc[-1]
                except (KeyError, IndexError):
                    continue

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
                print(f"Lỗi không xác định khi xử lý mã {symbol}: {e}", exc_info=True)
            
            await asyncio.sleep(2)