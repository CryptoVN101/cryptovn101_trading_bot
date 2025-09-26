import asyncio
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance.async_client import AsyncClient
from binance.exceptions import BinanceAPIException
from binance import AsyncClient, BinanceSocketManager
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
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
                
                # <<< SỬA LỖI DTYPE: Chuyển đổi tất cả các cột numeric để đảm bảo dtype nhất quán
                numeric_cols = [
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'
                ]
                for col in numeric_cols:
                    df[col] = pd.to_numeric(df[col])
                # >>> KẾT THÚC SỬA LỖI DTYPE
                
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


# --- LOGIC TÍNH TOÁN CHỈ BÁO ---
# ... (Phần còn lại của file giữ nguyên như phiên bản trước)
def calculate_cvd_divergence(df, symbol):
    if len(df) < 50 + FRACTAL_PERIODS:
        return None
    n = FRACTAL_PERIODS
    price_range = df['high'] - df['low']
    df['delta'] = np.where(price_range > 0, df['volume'] * (2 * df['close'] - df['low'] - df['high']) / price_range, 0)
    df['delta'] = df['delta'].fillna(0)
    df['cvd'] = ta.ema(df['delta'], length=CVD_PERIOD)
    df['ema50'] = ta.ema(df['close'], length=50)
    
    up_fractals = []
    down_fractals = []
    for i in range(n, len(df) - n):
        is_uptrend = df['close'].iloc[i - n] > df['ema50'].iloc[i - n]
        is_downtrend = df['close'].iloc[i - n] < df['ema50'].iloc[i - n]
        is_pivot_high = all(df['high'].iloc[i] >= df['high'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
        is_pivot_low = all(df['low'].iloc[i] <= df['low'].iloc[j] for j in range(i - n, i + n + 1) if j != i)
        if is_pivot_high and is_uptrend:
            up_fractals.append(i)
        if is_pivot_low and is_downtrend:
            down_fractals.append(i)
    
    current_bar_index = len(df) - 1
    signal = None
    if len(up_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = up_fractals[-1], up_fractals[-2]
        if current_bar_index - last_pivot_idx < 30:
            if (df['high'].iloc[last_pivot_idx] > df['high'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] < df['cvd'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] > 0 and df['cvd'].iloc[prev_pivot_idx] > 0 and
                last_pivot_idx - prev_pivot_idx < 30):
                signal = {'type': 'SHORT 📉', 'price': df['close'].iloc[last_pivot_idx],
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n],
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    if len(down_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = down_fractals[-1], down_fractals[-2]
        if current_bar_index - last_pivot_idx < 30:
            if (df['low'].iloc[last_pivot_idx] < df['low'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] > df['cvd'].iloc[prev_pivot_idx] and
                df['cvd'].iloc[last_pivot_idx] < 0 and df['cvd'].iloc[prev_pivot_idx] < 0 and
                last_pivot_idx - prev_pivot_idx < 30):
                signal = {'type': 'LONG 📈', 'price': df['close'].iloc[last_pivot_idx],
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n],
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    return signal

def calculate_stochastic(df):
    if df.empty:
        return None
    df_reset = df.reset_index(drop=True)
    stoch = df_reset.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        stoch.index = df.index
        return stoch[f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    return None

# --- XỬ LÝ DỮ LIỆU WEBSOCKET ---
async def process_kline_data(symbol, interval, kline, m15_data, h1_data, bot_instance):
    if 'k' not in kline:
        logger.error(f"Dữ liệu WebSocket không hợp lệ cho {symbol} ({interval}): {kline}")
        return
    
    timestamp_str = datetime.fromtimestamp(kline['k']['t'] / 1000, vietnam_tz).strftime('%Y-%m-%d %H:%M:%S')
    kline_data = kline['k']
    new_candle = {
        'timestamp': kline_data['t'], 'open': float(kline_data['o']), 'high': float(kline_data['h']),
        'low': float(kline_data['l']), 'close': float(kline_data['c']), 'volume': float(kline_data['v']),
        'close_time': kline_data['T'], 'quote_asset_volume': float(kline_data['q']),
        'number_of_trades': kline_data['n'], 'taker_buy_base_asset_volume': float(kline_data['V']),
        'taker_buy_quote_asset_volume': float(kline_data['Q']), 'ignore': '0'
    }
    
    df_to_update = klines_cache[symbol]['m15'] if interval == TIMEFRAME_M15 else klines_cache[symbol]['h1']
    
    if df_to_update.empty or new_candle['timestamp'] > df_to_update.iloc[-1]['timestamp']:
        # Tạo DataFrame từ new_candle với dtypes rõ ràng để tránh lỗi
        new_df_row = pd.DataFrame([new_candle])
        # Đảm bảo dtypes của new_df_row khớp với df_to_update nếu df_to_update không rỗng
        if not df_to_update.empty:
            new_df_row = new_df_row.astype(df_to_update.dtypes.to_dict())
        df_to_update = pd.concat([df_to_update, new_df_row], ignore_index=True).tail(1000)

    else:
        # Cập nhật dòng cuối cùng
        for key, value in new_candle.items():
            if key in df_to_update.columns:
                 df_to_update.iloc[-1, df_to_update.columns.get_loc(key)] = value


    if interval == TIMEFRAME_M15:
        klines_cache[symbol]['m15'] = df_to_update
    else:
        klines_cache[symbol]['h1'] = df_to_update
    
    if kline_data['x']:  # Xử lý khi nến đóng
        logger.info(f"Nhận nến mới và xử lý cho {symbol} trên khung {interval} tại {timestamp_str}")
        
        m15_df = klines_cache[symbol]['m15'].copy().set_index('timestamp')
        h1_df = klines_cache[symbol]['h1'].copy().set_index('timestamp')
        
        cvd_signal = calculate_cvd_divergence(m15_df.reset_index(), symbol)
        
        if cvd_signal:
            stoch_m15 = calculate_stochastic(m15_df)
            stoch_h1 = calculate_stochastic(h1_df)
            
            if stoch_m15 is not None and stoch_h1 is not None:
                pivot_ts = pd.to_datetime(cvd_signal['timestamp'], unit='ms')
                
                stoch_m15_value = stoch_m15[stoch_m15.index <= pivot_ts].iloc[-1] if not stoch_m15[stoch_m15.index <= pivot_ts].empty else None
                stoch_h1_value = stoch_h1[stoch_h1.index <= pivot_ts].iloc[-1] if not stoch_h1[stoch_h1.index <= pivot_ts].empty else None
                
                if stoch_m15_value is not None and stoch_h1_value is not None:
                    final_signal = {**cvd_signal, 'symbol': symbol, 'timeframe': 'M15', 'stoch_m15': stoch_m15_value, 'stoch_h1': stoch_h1_value}
                    
                    if (cvd_signal['type'] == 'LONG 📈' and stoch_m15_value < 20) or \
                       (cvd_signal['type'] == 'SHORT 📉' and stoch_m15_value > 80):
                        
                        win_rate = '80%' if ((cvd_signal['type'] == 'LONG 📈' and stoch_h1_value < 25) or
                                              (cvd_signal['type'] == 'SHORT 📉' and stoch_h1_value > 75)) else '60%'
                        final_signal['win_rate'] = win_rate
                        
                        signal_key = (symbol, final_signal['timestamp'])
                        if signal_key not in last_sent_signals:
                            from bot_handler import send_formatted_signal
                            await send_formatted_signal(bot_instance, final_signal)
                            last_sent_signals[signal_key] = datetime.now()
                            logger.info(f"✅ Đã gửi tín hiệu cho {symbol} lên channel")
        logger.info(f"--- Kết thúc xử lý nến cho {symbol} ---")


# --- BỘ MÁY QUÉT TÍN HIỆU LIÊN TỤC ---
# (Giữ nguyên không đổi)
async def run_signal_checker(bot_instance):
    logger.info(f"Bot khởi động với múi giờ: {datetime.now(vietnam_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"🚀 Signal checker is running with WebSocket tại {datetime.now(vietnam_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    from bot_handler import get_watchlist_from_db
    client = await AsyncClient.create()
    bsm = BinanceSocketManager(client, max_queue_size=1000)
    
    async def initialize_watches():
        watchlist = await get_watchlist_from_db()
        if not watchlist:
            logger.warning("Watchlist rỗng. Đợi cập nhật watchlist...")
            return
        for symbol in watchlist:
            klines_cache[symbol] = {'m15': pd.DataFrame(), 'h1': pd.DataFrame()}
            m15_data = await get_klines(symbol, TIMEFRAME_M15, client)
            h1_data = await get_klines(symbol, TIMEFRAME_H1, client)
            if not m15_data.empty:
                klines_cache[symbol]['m15'] = m15_data
            if not h1_data.empty:
                klines_cache[symbol]['h1'] = h1_data
            await asyncio.sleep(0.5)
        return watchlist

    async def start_websocket(watchlist):
        async def handle_kline_socket(symbol, interval):
            while True:
                try:
                    async with bsm.kline_socket(symbol=symbol.lower(), interval=interval) as kline_socket:
                        active_sockets[(symbol, interval)] = kline_socket
                        logger.debug(f"WebSocket connected for {symbol} ({interval})")
                        while True:
                            kline = await kline_socket.recv()
                            await process_kline_data(symbol, interval, kline, klines_cache[symbol]['m15'], klines_cache[symbol]['h1'], bot_instance)
                            await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"WebSocket ngắt kết nối cho {symbol} ({interval}): {str(e)}. Reconnect sau 5s...")
                    await asyncio.sleep(5)

        tasks = [handle_kline_socket(symbol, TIMEFRAME_M15) for symbol in watchlist] + \
                [handle_kline_socket(symbol, TIMEFRAME_H1) for symbol in watchlist]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def cleanup():
        for socket in active_sockets.values():
            await socket.close()
        if client and not client.session.closed:
            await client.close_connection()
        active_sockets.clear()
        logger.info("Resources cleaned up successfully.")

    try:
        watchlist = await initialize_watches()
        if watchlist:
            await start_websocket(watchlist)
    except asyncio.CancelledError:
        logger.info("Task cancelled, cleaning up resources...")
    except Exception as e:
        logger.error(f"Lỗi trong main loop của run_signal_checker: {e}")
    finally:
        await cleanup()