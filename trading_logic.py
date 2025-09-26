# trading_logic.py

import asyncio
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance.async_client import AsyncClient
from binance.exceptions import BinanceAPIException
from binance import BinanceSocketManager
import logging
from database import get_watchlist_from_db

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh') # Định nghĩa vietnam_tz sớm hơn
logger.handlers[0].formatter.converter = lambda *args: datetime.now(vietnam_tz).timetuple()

# --- CẤU HÌNH CHỈ BÁO ---
TIMEFRAME_M15 = AsyncClient.KLINE_INTERVAL_15MINUTE
TIMEFRAME_H1 = AsyncClient.KLINE_INTERVAL_1HOUR
FRACTAL_PERIODS = 2
CVD_PERIOD = 24
STOCH_K = 16
STOCH_SMOOTH_K = 16
STOCH_D = 8

# Biến global
last_sent_signals = {}
klines_cache = {}
active_sockets = {}

# --- KẾT NỐI VÀ LẤY DỮ LIỆU ---
async def get_klines(symbol, interval, client, max_retries=3, limit=500):
    for attempt in range(max_retries):
        try:
            logger.info(f"Lấy {limit} nến cho {symbol} trên khung {interval} (thử lần {attempt + 1})")
            klines = await client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            if not klines:
                logger.info(f"Fallback to spot klines for {symbol}")
                klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
            if klines:
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col])
                logger.info(f"Đã lấy {len(df)} nến cho {symbol}")
                return df
            raise ValueError("Could not retrieve klines from any market.")
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu cho {symbol} trên khung {interval}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Backoff exponential
            else:
                return pd.DataFrame()
    return pd.DataFrame()

# --- LOGIC TÍNH TOÁN CHỈ BÁO (Giữ nguyên) ---
def calculate_cvd_divergence(df, symbol):
    if len(df) < 50 + FRACTAL_PERIODS:
        return None
    n = FRACTAL_PERIODS
    price_range = df['high'] - df['low']
    df['delta'] = np.where(price_range > 0, df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range, 0)
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = ta.ema(df['delta'], length=CVD_PERIOD)
    df['ema50'] = ta.ema(df['close'], length=50)
    
    up_fractals, down_fractals = [], []
    for i in range(n, len(df) - n):
        is_uptrend = df['close'].iloc[i - n] > df['ema50'].iloc[i - n]
        is_downtrend = df['close'].iloc[i - n] < df['ema50'].iloc[i - n]
        is_pivot_high = all(df['high'].iloc[i] >= df['high'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
        is_pivot_low = all(df['low'].iloc[i] <= df['low'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
        if is_pivot_high and is_uptrend: up_fractals.append(i)
        if is_pivot_low and is_downtrend: down_fractals.append(i)
    
    current_bar_index = len(df) - 1
    signal = None
    if len(up_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = up_fractals[-1], up_fractals[-2]
        if current_bar_index - last_pivot_idx < 30 and (last_pivot_idx - prev_pivot_idx) < 30:
            if (df['high'].iloc[last_pivot_idx] > df['high'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] < df['cvd'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] > 0 and df['cvd'].iloc[prev_pivot_idx] > 0):
                signal = {'type': 'SHORT 📉', 'price': df['close'].iloc[last_pivot_idx], 'timestamp': df['timestamp'].iloc[last_pivot_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    if len(down_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = down_fractals[-1], down_fractals[-2]
        if current_bar_index - last_pivot_idx < 30 and (last_pivot_idx - prev_pivot_idx) < 30:
            if (df['low'].iloc[last_pivot_idx] < df['low'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] > df['cvd'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] < 0 and df['cvd'].iloc[prev_pivot_idx] < 0):
                signal = {'type': 'LONG 📈', 'price': df['close'].iloc[last_pivot_idx], 'timestamp': df['timestamp'].iloc[last_pivot_idx], 'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    return signal

def calculate_stochastic(df):
    if df.empty: return None
    df_reset = df.reset_index(drop=True)
    stoch = df_reset.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        stoch.index = df.index
        return stoch[f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    return None

# --- XỬ LÝ DỮ LIỆU WEBSOCKET (Giữ nguyên) ---
async def process_kline_data(symbol, interval, kline, m15_data, h1_data, bot_instance):
    from bot_handler import send_formatted_signal
    # ... (Toàn bộ logic bên trong hàm này giữ nguyên)
    if 'k' not in kline:
        logger.error(f"Dữ liệu WebSocket không hợp lệ cho {symbol} ({interval}): {kline}")
        return
    timestamp = datetime.fromtimestamp(kline['k']['t'] / 1000, vietnam_tz).strftime('%Y-%m-%d %H:%M:%S')
    kline_data = kline['k']
    new_candle = {
        'timestamp': kline_data['t'], 'open': float(kline_data['o']), 'high': float(kline_data['h']),
        'low': float(kline_data['l']), 'close': float(kline_data['c']), 'volume': float(kline_data['v']),
        'close_time': kline_data['T'], 'quote_asset_volume': float(kline_data['q']),
        'number_of_trades': kline_data['n'], 'taker_buy_base_asset_volume': float(kline_data['V']),
        'taker_buy_quote_asset_volume': float(kline_data['Q']), 'ignore': 0
    }
    
    df_target = m15_data if interval == TIMEFRAME_M15 else h1_data
    if df_target.empty:
        df_updated = pd.DataFrame([new_candle])
    else:
        df_updated = pd.concat([df_target, pd.DataFrame([new_candle])], ignore_index=True).tail(1000)

    for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
        df_updated[col] = pd.to_numeric(df_updated[col])
    
    if interval == TIMEFRAME_M15:
        klines_cache[symbol]['m15'] = df_updated
    else:
        klines_cache[symbol]['h1'] = df_updated
    
    if kline_data['x']:  # Xử lý khi nến đóng
        logger.info(f"Nến đóng cho {symbol} trên khung {interval} tại {timestamp}. Bắt đầu phân tích...")
        m15_df = klines_cache[symbol]['m15'].copy().set_index('timestamp')
        h1_df = klines_cache[symbol]['h1'].copy().set_index('timestamp')
        
        cvd_signal = calculate_cvd_divergence(m15_df.reset_index(), symbol)
        if cvd_signal:
            stoch_m15 = calculate_stochastic(m15_df)
            stoch_h1 = calculate_stochastic(h1_df)
            if stoch_m15 is not None and stoch_h1 is not None:
                confirmation_ts = pd.to_datetime(cvd_signal['confirmation_timestamp'], unit='ms')
                stoch_m15_value = stoch_m15.asof(confirmation_ts)
                stoch_h1_value = stoch_h1.asof(confirmation_ts)

                if stoch_m15_value is not None and stoch_h1_value is not None:
                    final_signal = {**cvd_signal, 'symbol': symbol, 'timeframe': 'M15', 'stoch_m15': stoch_m15_value, 'stoch_h1': stoch_h1_value}
                    if (cvd_signal['type'] == 'LONG 📈' and stoch_m15_value < 20) or \
                       (cvd_signal['type'] == 'SHORT 📉' and stoch_m15_value > 80):
                        win_rate = '80%' if ((cvd_signal['type'] == 'LONG 📈' and stoch_h1_value < 25) or
                                              (cvd_signal['type'] == 'SHORT 📉' and stoch_h1_value > 75)) else '60%'
                        final_signal['win_rate'] = win_rate
                        signal_key = (symbol, final_signal['timestamp'])
                        if signal_key not in last_sent_signals:
                            await send_formatted_signal(bot_instance, final_signal)
                            last_sent_signals[signal_key] = True
                            logger.info(f"✅ Đã gửi tín hiệu cho {symbol} lên channel")
        logger.info(f"--- Kết thúc xử lý nến cho {symbol} ---")


# --- BỘ MÁY QUÉT TÍN HIỆU LIÊN TỤC ---
async def run_signal_checker(bot_instance):
    logger.info(f"Bot khởi động với múi giờ: {datetime.now(vietnam_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"🚀 Signal checker is running with WebSocket tại {datetime.now(vietnam_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    client = await AsyncClient.create()
    bsm = BinanceSocketManager(client, max_queue_size=1000)
    
    async def initialize_watches():
        watchlist = await get_watchlist_from_db()
        if not watchlist:
            logger.warning("Watchlist rỗng. Đợi cập nhật watchlist...")
            return []
        for symbol in watchlist:
            klines_cache[symbol] = {'m15': pd.DataFrame(), 'h1': pd.DataFrame()}
            m15_data, h1_data = await asyncio.gather(
                get_klines(symbol, TIMEFRAME_M15, client),
                get_klines(symbol, TIMEFRAME_H1, client)
            )
            if not m15_data.empty: klines_cache[symbol]['m15'] = m15_data
            if not h1_data.empty: klines_cache[symbol]['h1'] = h1_data
            await asyncio.sleep(0.5)
        return watchlist

    async def start_websocket(watchlist):
        async def handle_kline_socket(symbol, interval):
            socket_key = f"{symbol.lower()}@kline_{interval}"
            async with bsm.kline_socket(symbol=symbol, interval=interval) as kline_socket:
                logger.info(f"WebSocket connected for {socket_key}")
                active_sockets[socket_key] = kline_socket
                while True:
                    try:
                        kline = await asyncio.wait_for(kline_socket.recv(), timeout=600)
                        await process_kline_data(symbol, interval, kline, klines_cache[symbol]['m15'], klines_cache[symbol]['h1'], bot_instance)
                    except asyncio.TimeoutError:
                        logger.warning(f"WebSocket timeout for {socket_key}. Reconnecting...")
                        break
                    except Exception as e:
                        logger.error(f"WebSocket lỗi cho {socket_key}: {e}. Reconnecting...")
                        break

        while True:
            try:
                tasks = [handle_kline_socket(symbol, tf) for symbol in watchlist for tf in [TIMEFRAME_M15, TIMEFRAME_H1]]
                await asyncio.gather(*tasks)
            except Exception as e:
                logger.error(f"Lỗi nghiêm trọng trong start_websocket: {e}. Khởi động lại sau 10s...")
                await asyncio.sleep(10)


    async def cleanup():
        logger.info("Cleaning up resources...")
        for key, socket in active_sockets.items():
            if hasattr(socket, 'close'):
                await socket.close()
        active_sockets.clear()
        if client and not client.session.closed:
            await client.close_connection()
        logger.info("Resources cleaned up successfully.")

    watchlist = await initialize_watches()
    if watchlist:
        try:
            await start_websocket(watchlist)
        except asyncio.CancelledError:
            logger.info("run_signal_checker task was cancelled.")
        finally:
            await cleanup()

# --- XÓA BỎ HOÀN TOÀN HÀM watchlist_monitor ---