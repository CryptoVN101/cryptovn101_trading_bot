# 🤖 Bot Tín hiệu Giao dịch StochCVD cho Telegram

## 📖 Giới thiệu
Đây là một bot Telegram được lập trình bằng **Python** để tự động quét và gửi tín hiệu giao dịch tiền điện tử theo thời gian thực.  
Bot được thiết kế chạy **24/7**, lấy dữ liệu trực tiếp từ API của **Binance** và gửi thông báo tín hiệu đến một channel Telegram được chỉ định.  

### 🔑 Chiến lược giao dịch cốt lõi
1. **Phân kỳ Delta Khối lượng Tích lũy (CVD Divergence):** Dùng để xác định tín hiệu đảo chiều tiềm năng khi có sự mâu thuẫn giữa hành động giá và áp lực mua/bán thực tế.  
2. **Chỉ báo Stochastic Oscillator:** Xác nhận trạng thái quá mua/quá bán của thị trường, tăng thêm độ tin cậy cho tín hiệu.  

---

## ✨ Tính năng chính
- **Quét tín hiệu Real-time:** Bot tự động "thức dậy" và quét tín hiệu sau mỗi cây nến M15 đóng cửa.  
- **Chiến lược kết hợp:** Chỉ gửi tín hiệu khi cả điều kiện **CVD Divergence** và **Stochastic** đều được thỏa mãn.  
- **Hỗ trợ đa sàn:** Ưu tiên lấy dữ liệu từ thị trường **Futures**, fallback sang **Spot** nếu không tìm thấy.  
- **Quản lý Watchlist động:** Thêm, xóa, xem danh sách coin cần theo dõi trực tiếp qua các lệnh trên Telegram.  
- **Lưu trữ bền bỉ:** Sử dụng cơ sở dữ liệu **PostgreSQL** để lưu watchlist, tránh mất dữ liệu khi cập nhật code.  
- **Tối ưu cho Deployment:** Sẵn sàng triển khai trên các nền tảng **PaaS** như Railway.  

---

## 🛠️ Cấu trúc Dự án
/
├── .env # (Cần tạo) Lưu trữ các biến môi trường bí mật
├── requirements.txt # Danh sách các thư viện Python
├── main.py # Điểm khởi đầu, khởi chạy bot và bộ quét
├── config.py # Quản lý biến môi trường
├── database.py # Xử lý tương tác với PostgreSQL
├── bot_handler.py # Xử lý lệnh Telegram & định dạng tin nhắn
├── trading_logic.py # "Bộ não" của bot (logic phân tích kỹ thuật)
└── backtester.py # Công cụ kiểm tra chiến lược với dữ liệu quá khứ


---

## ⚙️ Cài đặt và Chạy Local

### 🔧 Yêu cầu
- Python **3.10+**  
- Git  

### 📌 Các bước cài đặt
```bash
# Clone repository
git clone https://github.com/CryptoVN101/cryptovn101_trading_bot.git
cd cryptovn101_trading_bot

# (Khuyến khích) Tạo môi trường ảo
python -m venv venv

# Trên Windows
.\venv\Scripts\Activate.ps1

# Trên macOS/Linux
source venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt

📝 Tạo file .env

Tạo file .env trong thư mục gốc và thêm nội dung sau:

TELEGRAM_TOKEN="TOKEN_BOT_CUA_BAN"
CHAT_ID="ID_GROUP_CHAT_DE_RA_LENH"
CHANNEL_ID="ID_CHANNEL_DE_NHAN_TIN_HIEU"

Lưu ý: CHAT_ID và CHANNEL_ID có thể giống nhau nếu bạn muốn bot hoạt động trong cùng một nhóm

# Chạy bot real-time
python main.py

# Chạy backtest dữ liệu quá khứ
python backtester.py

🚀 Hướng dẫn Deploy lên Railway

Push code lên GitHub.

Tạo Project mới trên Railway và kết nối với repository GitHub.

Thêm Database:

Command Palette → + New Service → Database → PostgreSQL.

Cấu hình biến môi trường:

Railway sẽ tự động cung cấp DATABASE_URL.

Thêm thủ công:

TELEGRAM_TOKEN

CHAT_ID

CHANNEL_ID

Railway sẽ tự động deploy sau khi thêm biến. Bot sẽ hoạt động 24/7

🤖 Các lệnh Telegram

/start → Khởi động và kiểm tra bot.

/add <SYMBOL_1> <SYMBOL_2> ... → Thêm coin vào watchlist.

Ví dụ: /add BTCUSDT SOLUSDT

/remove <SYMBOL_1> <SYMBOL_2> ... → Xóa coin khỏi watchlist.

/list → Hiển thị toàn bộ coin đang theo dõi.

/backtest → Chạy backtest và gửi toàn bộ tín hiệu lịch sử.


---

Bạn có muốn mình thêm **badge (Python version, Telegram Bot, Railway Deploy)** ngay phần đầu README để nhìn chuyên nghiệp hơn không?

