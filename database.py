# database.py
import asyncpg
from config import DATABASE_URL

# --- KHỞI TẠO VÀ QUẢN LÝ DATABASE ---

async def init_db():
    """Khởi tạo bảng watchlist nếu chưa tồn tại."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id SERIAL PRIMARY KEY,
                symbol TEXT UNIQUE NOT NULL
            );
        ''')
        print("Database initialized, 'watchlist' table is ready.")
    finally:
        await conn.close()

async def get_watchlist_from_db():
    """Lấy danh sách các mã coin từ database."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch('SELECT symbol FROM watchlist ORDER BY symbol ASC;')
        return [row['symbol'] for row in rows]
    finally:
        await conn.close()

async def add_symbols_to_db(symbols: list):
    """Thêm một hoặc nhiều mã coin vào database."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # ON CONFLICT DO NOTHING để tránh lỗi khi thêm mã đã tồn tại
        await conn.executemany('''
            INSERT INTO watchlist (symbol) VALUES ($1)
            ON CONFLICT (symbol) DO NOTHING;
        ''', [(s,) for s in symbols])
    finally:
        await conn.close()

async def remove_symbols_from_db(symbols: list):
    """Xóa một hoặc nhiều mã coin khỏi database."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.executemany('DELETE FROM watchlist WHERE symbol = $1;', [(s,) for s in symbols])
    finally:
        await conn.close()
