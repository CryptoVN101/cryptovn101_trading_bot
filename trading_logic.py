import asyncio
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np
import pandas_ta as ta
from binance.async_client import AsyncClient 
from binance.exceptions import BinanceAPIException
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CẤU HÌNH MỚI CHO CHỈ BÁO ---
TIMEFRAME_M15 = AsyncClient.KLINE_INTERVAL_15MINUTE
TIMEFRAME_H1 = AsyncClient.KLINE_INTERVAL_1HOUR
FRACTAL_PERIODS = 2  # Đã cập nhật theo yêu cầu
CVD_PERIOD = 24

# Cấu hình Stochastic (không đổi)
STOCH_K = 16
STOCH_SMOOTH_K = 16
STOCH_D = 8

# Biến global để lưu trữ "trí nhớ" của bot
last_sent_signals = {}

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
    logger.info(f"Tính CVD cho {len(df)} nến")
    if len(df) < 50 + FRACTAL_PERIODS:
        logger.warning(f"Không đủ dữ liệu: {len(df)} nến, cần {50 + FRACTAL_PERIODS}")
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
    
    logger.info(f"Tìm thấy {len(up_fractals)} fractal đỉnh, {len(down_fractals)} fractal đáy")
    current_bar_index = len(df) - 1
    signal = None
    if len(up_fractals) >= 2:
        last_pivot_idx, prev_pivot_idx = up_fractals[-1], up_fractals[-2]
        if (current_bar_index - last_pivot_idx) < 30:
            High_Last_Price = df['high'].iloc[last_pivot_idx]
            High_Per_Price = df['high'].iloc[prev_pivot_idx]
            High_Last_Hist = df['cvd'].iloc[last_pivot_idx]
            High_Per_Hist = df['cvd'].iloc[prev_pivot_idx]
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
            if (Low_Last_Price < Low_Per_Price) and (Low_Last_Hist > Low_Per_Hist) and \
               (Low_Last_Hist < 0 and Low_Per_Hist < 0) and ((last_pivot_idx - prev_pivot_idx) < 30):
                signal = {'type': 'LONG 📈', 'price': df['close'].iloc[last_pivot_idx], 
                          'timestamp': df['timestamp'].iloc[last_pivot_idx],
                          'confirmation_timestamp': df['timestamp'].iloc[last_pivot_idx + n], 
                          'confirmation_price': df['close'].iloc[last_pivot_idx + n]}
    if signal:
        logger.info(f"Tín hiệu được tạo: {signal}")
    else:
        logger.info("Không tạo được tín hiệu phân kỳ CVD")
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

# --- BỘ MÁY QUÉT TÍN HIỆU ---
async def run_signal_checker(bot):
    logger.info("🚀 Signal checker is running...")
    from bot_handler import get_watchlist_from_db, send_formatted_signal 
    
    while True:
        now = datetime.now(pytz.utc)
        next_run_minute = (now.minute // 15 + 1) * 15
        if next_run_minute >= 60:
            next_run_time = now.replace(minute=0, second=10, microsecond=0) + timedelta(hours=1)
        else:
            next_run_time = now.replace(minute=next_run_minute, second=10, microsecond=0)
        
        sleep_duration = (next_run_time - now).total_seconds()
        
        if sleep_duration > 0:
            logger.info(f"Quét tiếp theo lúc {next_run_time.astimezone(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}. Ngủ {sleep_duration:.0f} giây.")
            await asyncio.sleep(sleep_duration)

        logger.info(f"\n--- Thức dậy lúc {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')} để quét tín hiệu ---")
        watchlist = await get_watchlist_from_db()
        if not watchlist:
            logger.warning("Watchlist rỗng. Sẽ kiểm tra lại ở chu kỳ tiếp theo.")
            continue
            
        for symbol in watchlist:
            logger.info(f"Quét {symbol}...")
            try:
                m15_data, h1_data = await asyncio.gather(get_klines(symbol, TIMEFRAME_M15), get_klines(symbol, TIMEFRAME_H1))
                if m15_data.empty or h1_data.empty:
                    logger.warning(f"Dữ liệu rỗng cho {symbol}: M15={len(m15_data)}, H1={len(h1_data)}")
                    continue

                m15_data.set_index('timestamp', inplace=True)
                h1_data.set_index('timestamp', inplace=True)

                cvd_signal_m15 = calculate_cvd_divergence(m15_data.copy().reset_index())
                if not cvd_signal_m15:
                    logger.info(f"Không có tín hiệu CVD cho {symbol}")
                    continue

                stoch_m15_series = calculate_stochastic(m15_data)
                stoch_h1_series = calculate_stochastic(h1_data)
                if stoch_m15_series is None or stoch_h1_series is None:
                    logger.warning(f"Thiếu Stochastic cho {symbol}: M15={stoch_m15_series is None}, H1={stoch_h1_series is None}")
                    continue
                
                confirmation_ts = pd.to_datetime(cvd_signal_m15['confirmation_timestamp'], unit='ms')
                
                try:
                    stoch_m15 = stoch_m15_series.loc[confirmation_ts]
                except KeyError:
                    stoch_m15_series = stoch_m15_series.sort_index()
                    stoch_m15 = stoch_m15_series[stoch_m15_series.index <= confirmation_ts].iloc[-1] if not stoch_m15_series[stoch_m15_series.index <= confirmation_ts].empty else None
                    logger.warning(f"Không tìm thấy timestamp Stochastic M15 {confirmation_ts}, dùng giá trị gần nhất: {stoch_m15}")

                try:
                    stoch_h1_latest_before = stoch_h1_series[h1_data.index <= confirmation_ts]
                    stoch_h1 = stoch_h1_latest_before.iloc[-1] if not stoch_h1_latest_before.empty else None
                except KeyError:
                    logger.warning(f"Không tìm thấy timestamp Stochastic H1 {confirmation_ts}")
                    stoch_h1 = None

                if stoch_m15 is None or stoch_h1 is None:
                    logger.warning(f"Không có Stochastic hợp lệ cho {symbol}: M15={stoch_m15}, H1={stoch_h1}")
                    continue

                logger.info(f"Giá trị Stochastic cho {symbol}: M15={stoch_m15}, H1={stoch_h1} tại {confirmation_ts}")

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
                    logger.info(f"Tín hiệu cuối cùng cho {symbol}: {final_signal_message}")
                    signal_timestamp = final_signal_message['timestamp']
                    if last_sent_signals.get(symbol) != signal_timestamp:
                        await send_formatted_signal(bot, final_signal_message)
                        last_sent_signals[symbol] = signal_timestamp
                        logger.info(f"Đã gửi tín hiệu cho {symbol}")
                    else:
                        logger.info(f"Tín hiệu trùng lặp cho {symbol}. Bỏ qua.")
                else:
                    logger.info(f"Không tạo tín hiệu cuối cùng cho {symbol} sau khi kiểm tra Stochastic")

            except Exception as e:
                logger.error(f"Lỗi xử lý {symbol}: {e}")
            await asyncio.sleep(3)