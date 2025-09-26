# database.py
import asyncpg
from config import DATABASE_URL
import asyncio

# Biến global để giữ connection pool
db_pool = None

async def init_db():
    """
    Khởi tạo connection pool và tạo bảng nếu chưa tồn tại.
    Hàm này chỉ được gọi một lần khi bot khởi động.
    """
    global db_pool
    if db_pool:
        return
        
    try:
        db_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,
            max_size=5 # Giới hạn 5 kết nối đồng thời
        )
        # Sử dụng pool để thực thi lệnh
        async with db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT UNIQUE NOT NULL
                );
            ''')
        print("Database pool initialized, 'watchlist' table is ready.")
    except Exception as e:
        print(f"FATAL: Could not connect to the database: {e}")
        # Dừng chương trình nếu không kết nối được DB
        # Cân nhắc thêm xử lý tắt bot an toàn ở đây
        raise e

async def close_db_pool():
    """Đóng connection pool khi bot tắt."""
    global db_pool
    if db_pool:
        await db_pool.close()
        print("Database pool closed.")
        db_pool = None

async def get_watchlist_from_db():
    """Lấy danh sách các mã coin từ database bằng cách sử dụng pool."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('SELECT symbol FROM watchlist ORDER BY symbol ASC;')
        return [row['symbol'] for row in rows]

async def add_symbols_to_db(symbols: list):
    """Thêm một hoặc nhiều mã coin vào database bằng cách sử dụng pool."""
    async with db_pool.acquire() as conn:
        await conn.executemany('''
            INSERT INTO watchlist (symbol) VALUES ($1)
            ON CONFLICT (symbol) DO NOTHING;
        ''', [(s,) for s in symbols])

async def remove_symbols_from_db(symbols: list):
    """Xóa một hoặc nhiều mã coin khỏi database bằng cách sử dụng pool."""
    async with db_pool.acquire() as conn:
        await conn.executemany('DELETE FROM watchlist WHERE symbol = $1;', [(s,) for s in symbols])