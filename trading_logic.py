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
handler = logging.StreamHandler()  # Thêm handler mặc định cho console
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.handlers[0].formatter.converter = lambda *args: datetime.now(vietnam_tz).timetuple()

# --- CẤU HÌNH CHỈ BÁO ---
TIMEFRAME_M15 = AsyncClient.KLINE_INTERVAL_15MINUTE
TIMEFRAME_H1 = AsyncClient.KLINE_INTERVAL_1HOUR
FRACTAL_PERIODS = 2
CVD_PERIOD = 24

# Cấu hình Stochastic
STOCH_K = 16
STOCH_SMOOTH_K = 16
STOCH_D = 8

# Biến global
last_sent_signals = {}
klines_cache = {}
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
active_sockets = {}  # Lưu trữ các socket WebSocket để đóng khi cần

# --- KẾT NỐI VÀ LẤY DỮ LIỆU ---
async def get_klines(symbol, interval, limit=1500):
    client = None
    try:
        client = await AsyncClient.create()
        logger.info(f"Lấy {limit} nến cho {symbol} trên khung {interval}")
        klines = None
        try:
            klines = await client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except BinanceAPIException as e:
            if e.code == -1121:
                logger.info(f"Fallback to spot klines for {symbol}")
                klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
            else:
                raise e
        
        if klines is None:
            logger.error(f"Không thể lấy dữ liệu nến cho {symbol} trên khung {interval}")
            raise ValueError("Could not retrieve klines from any market.")

        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        logger.info(f"Đã lấy {len(df)} nến cho {symbol}")
        for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu cho {symbol} trên khung {interval}: {e}")
        return pd.DataFrame()
    finally:
        if client:
            await client.close_connection()

# --- LOGIC TÍNH TOÁN CHỈ BÁO ---
def calculate_cvd_divergence(df):
    global symbol  # Đảm bảo symbol được định nghĩa trong phạm vi hàm
    logger.info(f"Tính CVD cho {symbol}: {len(df)} nến")
    if len(df) < 50 + FRACTAL_PERIODS:
        logger.warning(f"Không đủ dữ liệu cho {symbol}: {len(df)} nến, cần {50 + FRACTAL_PERIODS}")
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
    
    logger.info(f"{symbol}: Tìm thấy {len(up_fractals)} fractal đỉnh, {len(down_fractals)} fractal đáy")
    current_bar_index = len(df) - 1
    signal = None
    if len(up_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = up_fractals[-1], up_fractals[-2]
        if (current_bar_index - last_pivot_idx) < 30:
            High_Last_Price = df['high'].iloc[last_pivot_idx]
            High_Per_Price = df['high'].iloc[prev_pivot_idx]
            High_Last_Hist = df['cvd'].iloc[last_pivot_idx]
            High_Per_Hist = df['cvd'].iloc[prev_pivot_idx]
            logger.info(f"{symbol}: SHORT check - Price: {High_Last_Price} vs {High_Per_Price}, CVD: {High_Last_Hist} vs {High_Per_Hist}")
            if (High_Last_Price > High_Per_Price) and (High_Last_Hist < High_Per_Hist) and \
               (High_Last_Hist > 0 and High_Per_Hist > 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'SHORT 📉', 'price': df['close'].iloc[last_pivot_idx], 
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    if len(down_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = down_fractals[-1], down_fractals[-2]
        if (current_bar_index - last_pivot_idx) < 30:
            Low_Last_Price = df['low'].iloc[last_pivot_idx]
            Low_Per_Price = df['low'].iloc[prev_pivot_idx]
            Low_Last_Hist = df['cvd'].iloc[last_pivot_idx]
            Low_Per_Hist = df['cvd'].iloc[prev_pivot_idx]
            logger.info(f"{symbol}: LONG check - Price: {Low_Last_Price} vs {Low_Per_Price}, CVD: {Low_Last_Hist} vs {Low_Per_Hist}")
            if (Low_Last_Price < Low_Per_Price) and (Low_Last_Hist > Low_Per_Hist) and \
               (Low_Last_Hist < 0 and Low_Per_Hist < 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'LONG 📈', 'price': df['close'].iloc[last_pivot_idx], 
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    if signal:
        logger.info(f"{symbol}: Tín hiệu được tạo: {signal}")
    else:
        logger.info(f"{symbol}: Không tạo được tín hiệu phân kỳ CVD")
    return signal

def calculate_stochastic(df):
    logger.info(f"Tính Stochastic cho {len(df)} nến")
    if df.empty:
        logger.warning("Dataframe rỗng khi tính Stochastic")
        return None
    df_reset = df.reset_index(drop=True)
    stoch = df_reset.ta.stoch(k=STOCH_K, d=STOCH_D, smooth_k=STOCH_SMOOTH_K)
    if stoch is not None and not stoch.empty:
        stoch.index = df.index
        logger.info(f"Stochastic tính xong: giá trị mới nhất = {stoch.iloc[-1]}")
        return stoch[f'STOCHk_{STOCH_K}_{STOCH_D}_{STOCH_SMOOTH_K}']
    logger.warning("Tính Stochastic thất bại")
    return None

# --- XỬ LÝ DỮ LIỆU WEBSOCKET ---
async def process_kline_data(symbol, interval, kline, m15_data, h1_data):
    if 'k' not in kline:
        logger.error(f"Dữ liệu WebSocket không hợp lệ cho {symbol} ({interval}): {kline}")
        return
    timestamp = datetime.fromtimestamp(kline['k']['t'] / 1000, vietnam_tz).strftime('%Y-%m-%d %H:%M:%S')
    kline_data = kline['k']
    new_candle = {
        'timestamp': kline_data['t'],
        'open': float(kline_data['o']),
        'high': float(kline_data['h']),
        'low': float(kline_data['l']),
        'close': float(kline_data['c']),
        'volume': float(kline_data['v']),
        'close_time': kline_data['T'],
        'quote_asset_volume': float(kline_data['q']),
        'number_of_trades': kline_data['n'],
        'taker_buy_base_asset_volume': float(kline_data['V']),
        'taker_buy_quote_asset_volume': float(kline_data['Q']),
        'ignore': 0
    }
    
    if interval == TIMEFRAME_M15:
        df = m15_data
    else:
        df = h1_data
    
    if df.empty:
        df = pd.DataFrame([new_candle])
    else:
        df = pd.concat([df, pd.DataFrame([new_candle])], ignore_index=True)
        df = df.tail(1500)
    
    for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])
    
    if interval == TIMEFRAME_M15:
        klines_cache[symbol]['m15'] = df
    else:
        klines_cache[symbol]['h1'] = df
    
    if kline_data['x']:
        logger.info(f"Nhận nến mới và xử lý cho {symbol} trên khung {interval} tại {timestamp}")
        logger.info(f"Cập nhật cache cho {symbol}: M15={len(klines_cache[symbol]['m15'])}, H1={len(klines_cache[symbol]['h1'])} nến")
        logger.info(f"--- Kết thúc xử lý nến cho {symbol} ---")

# --- BỘ MÁY QUÉT TÍN HIỆU LIÊN TỤC ---
async def run_signal_checker(bot_instance):  # Thêm bot_instance làm tham số
    logger.info(f"Bot khởi động với múi giờ: {datetime.now(vietnam_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"🚀 Signal checker is running with WebSocket tại {datetime.now(vietnam_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    from bot_handler import get_watchlist_from_db, send_formatted_signal
    
    client = await AsyncClient.create()
    bsm = BinanceSocketManager(client, max_queue_size=1000)
    
    async def initialize_watches():
        watchlist = await get_watchlist_from_db()
        if not watchlist:
            logger.warning("Watchlist rỗng. Đợi cập nhật watchlist...")
            return
        for symbol in watchlist:
            klines_cache[symbol] = {'m15': pd.DataFrame(), 'h1': pd.DataFrame()}
            m15_data, h1_data = await asyncio.gather(
                get_klines(symbol, TIMEFRAME_M15),
                get_klines(symbol, TIMEFRAME_H1)
            )
            klines_cache[symbol]['m15'] = m15_data
            klines_cache[symbol]['h1'] = h1_data
        return watchlist

    async def start_websocket(watchlist):
        async def handle_kline_socket(symbol, interval):
            while True:
                try:
                    async with bsm.kline_futures_socket(symbol=symbol.lower(), interval=interval) as kline_socket:
                        active_sockets[(symbol, interval)] = kline_socket
                        while True:
                            kline = await kline_socket.recv()
                            await process_kline_data(symbol, interval, kline, klines_cache[symbol]['m15'], klines_cache[symbol]['h1'])
                            if interval == TIMEFRAME_M15 and 'k' in kline and kline['k']['x']:
                                m15_data = klines_cache[symbol]['m15'].copy()
                                h1_data = klines_cache[symbol]['h1'].copy()
                                if m15_data.empty or h1_data.empty:
                                    logger.warning(f"Dữ liệu rỗng cho {symbol}: M15={len(m15_data)}, H1={len(h1_data)}")
                                    continue
                                m15_data.set_index('timestamp', inplace=True)
                                h1_data.set_index('timestamp', inplace=True)
                                cvd_signal_m15 = calculate_cvd_divergence(m15_data.copy().reset_index())
                                if not cvd_signal_m15:
                                    continue
                                stoch_m15_series = calculate_stochastic(m15_data)
                                stoch_h1_series = calculate_stochastic(h1_data)
                                if stoch_m15_series is None or stoch_h1_series is None:
                                    continue
                                confirmation_ts = pd.to_datetime(cvd_signal_m15['confirmation_timestamp'], unit='ms')
                                stoch_m15 = stoch_m15_series[stoch_m15_series.index <= confirmation_ts].iloc[-1] if not stoch_m15_series[stoch_m15_series.index <= confirmation_ts].empty else None
                                stoch_h1_latest_before = stoch_h1_series[h1_data.index <= confirmation_ts]
                                stoch_h1 = stoch_h1_latest_before.iloc[-1] if not stoch_h1_latest_before.empty else None
                                if stoch_m15 is None or stoch_h1 is None:
                                    continue
                                final_signal_message = None
                                base_signal = {**cvd_signal_m15, 'symbol': symbol, 'timeframe': 'M15', 'stoch_m15': stoch_m15, 'stoch_h1': stoch_h1}
                                if cvd_signal_m15['type'] == 'LONG 📈' and stoch_m15 < 20:
                                    if stoch_h1 > 25:
                                        final_signal_message = {**base_signal, 'win_rate': '60%'}
                                    elif stoch_h1 < 25:
                                        final_signal_message = {**base_signal, 'win_rate': '80%'}
                                elif cvd_signal_m15['type'] == 'SHORT 📉' and stoch_m15 > 80:
                                    if stoch_h1 < 75:
                                        final_signal_message = {**base_signal, 'win_rate': '60%'}
                                    elif stoch_h1 > 75:
                                        final_signal_message = {**base_signal, 'win_rate': '80%'}
                                if final_signal_message:
                                    signal_timestamp = final_signal_message['timestamp']
                                    if last_sent_signals.get(symbol) != signal_timestamp:
                                        await send_formatted_signal(bot_instance, final_signal_message)  # Sử dụng bot_instance
                                        last_sent_signals[symbol] = signal_timestamp
                                        logger.info(f"✅ Đã gửi tín hiệu cho {symbol} lên channel")
                                    else:
                                        logger.info(f"Tín hiệu trùng lặp cho {symbol}. Bỏ qua.")
                            await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"WebSocket ngắt kết nối cho {symbol} ({interval}): {str(e)}. Reconnect sau 5s...")
                    await asyncio.sleep(5)

        tasks = []
        for symbol in watchlist:
            tasks.append(handle_kline_socket(symbol, TIMEFRAME_M15))
            tasks.append(handle_kline_socket(symbol, TIMEFRAME_H1))
        await asyncio.gather(*tasks)

    # Khởi chạy
    watchlist = await initialize_watches()
    if watchlist:
        asyncio.create_task(start_websocket(watchlist))
        asyncio.create_task(watchlist_monitor(bot_instance))  # Truyền bot_instance
    try:
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Lỗi trong main loop: {e}")
    finally:
        for socket in active_sockets.values():
            await socket.close()
        await client.close_connection()

# --- HÀM ĐỊNH KỲ KIỂM TRA WATCHLIST ---
async def watchlist_monitor(bot_instance):  # Thêm bot_instance làm tham số
    while True:
        try:
            from bot_handler import reload_signal_checker  # Import tại đây để tránh vòng lặp
            await reload_signal_checker(bot_instance)  # Gọi với bot_instance
            await asyncio.sleep(60)  # Kiểm tra mỗi 60 giây
        except Exception as e:
            logger.error(f"Lỗi trong watchlist_monitor: {e}")
            await asyncio.sleep(5)