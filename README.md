Bot Tín hiệu Giao dịch StochCVD cho Telegram
📖 Giới thiệu
Đây là một bot Telegram được lập trình bằng Python để tự động quét và gửi tín hiệu giao dịch tiền điện tử theo thời gian thực. Bot được thiết kế để chạy 24/7, lấy dữ liệu trực tiếp từ API của Binance và gửi thông báo tín hiệu đến một channel Telegram được chỉ định.

Chiến lược giao dịch cốt lõi dựa trên sự kết hợp của hai chỉ báo phân tích kỹ thuật mạnh mẽ:

Phân kỳ Delta Khối lượng Tích lũy (CVD Divergence): Dùng để xác định các tín hiệu đảo chiều tiềm năng khi có sự mâu thuẫn giữa hành động giá và áp lực mua/bán thực tế.

Chỉ báo Stochastic Oscillator: Dùng để xác nhận trạng thái quá mua/quá bán của thị trường, tăng thêm độ tin cậy cho tín hiệu.

✨ Tính năng chính
Quét tín hiệu Real-time: Bot tự động "thức dậy" và quét tín hiệu sau mỗi cây nến M15 đóng cửa.

Chiến lược Kết hợp: Chỉ gửi tín hiệu khi cả điều kiện Phân kỳ CVD và Stochastic đều được thỏa mãn.

Hỗ trợ Đa sàn: Tự động ưu tiên lấy dữ liệu từ thị trường Futures và chuyển sang Spot nếu không tìm thấy.

Quản lý Watchlist Động: Dễ dàng thêm, xóa, và xem danh sách các cặp coin cần theo dõi trực tiếp qua các lệnh trên Telegram.

Lưu trữ Bền bỉ: Khi được deploy, bot sử dụng cơ sở dữ liệu PostgreSQL để lưu trữ watchlist, đảm bảo không bị mất dữ liệu khi cập nhật code.

Tối ưu cho Deployment: Code được cấu trúc để sẵn sàng triển khai trên các nền tảng PaaS như Railway.

🛠️ Cấu trúc Dự án
/
├── .env                  # (Cần tạo) Lưu trữ các biến môi trường bí mật.
├── requirements.txt      # Danh sách các thư viện Python cần thiết.
├── main.py               # Điểm khởi đầu của ứng dụng, khởi chạy bot và bộ quét.
├── config.py             # Tải và quản lý các biến môi trường.
├── database.py           # Xử lý mọi tương tác với cơ sở dữ liệu PostgreSQL.
├── bot_handler.py        # Xử lý các lệnh từ người dùng Telegram và định dạng tin nhắn.
├── trading_logic.py      # "Bộ não" của bot, chứa toàn bộ logic phân tích kỹ thuật.
└── backtester.py         # Công cụ để kiểm tra lại chiến lược trên dữ liệu quá khứ.

⚙️ Cài đặt và Chạy Local
Yêu cầu
Python 3.10+

Git

Các bước cài đặt
Clone repository về máy:

git clone [https://github.com/CryptoVN101/cryptovn101_trading_bot.git](https://github.com/CryptoVN101/cryptovn101_trading_bot.git)
cd cryptovn101_trading_bot

(Khuyến khích) Tạo và kích hoạt môi trường ảo:

python -m venv venv
# Trên Windows
.\venv\Scripts\Activate.ps1
# Trên macOS/Linux
source venv/bin/activate

Cài đặt các thư viện cần thiết:

pip install -r requirements.txt

Tạo file .env:
Tạo một file mới có tên là .env trong thư mục gốc và điền các thông tin của bạn vào theo mẫu sau:

TELEGRAM_TOKEN="TOKEN_BOT_CUA_BAN"
CHAT_ID="ID_GROUP_CHAT_DE_RA_LENH" 
CHANNEL_ID="ID_CHANNEL_DE_NHAN_TIN_HIEU"

Lưu ý: CHAT_ID và CHANNEL_ID có thể giống nhau nếu bạn muốn bot hoạt động trong cùng một nhóm.

Chạy Bot
Chạy bot real-time:

python main.py

Chạy backtest trên dữ liệu quá khứ:

python backtester.py

🚀 Hướng dẫn Deploy lên Railway
Push code lên GitHub: Đảm bảo phiên bản code mới nhất của bạn đã có trên GitHub.

Tạo Project trên Railway:

Tạo một project mới và kết nối nó với repository GitHub của bạn.

Thêm Database:

Sử dụng Command Palette (Ctrl+K), chọn + New Service -> Database -> PostgreSQL.

Cấu hình Biến Môi trường:

Vào service của bot, chọn tab Variables.

Railway sẽ tự động cung cấp biến DATABASE_URL.

Bạn cần thêm thủ công các biến sau:

TELEGRAM_TOKEN

CHAT_ID

CHANNEL_ID

Railway sẽ tự động deploy sau khi bạn thêm biến. Bot sẽ bắt đầu hoạt động 24/7.

🤖 Các lệnh Telegram
/start: Khởi động và kiểm tra bot.

/add <SYMBOL_1> <SYMBOL_2> ...: Thêm một hoặc nhiều mã coin vào danh sách theo dõi (ví dụ: /add BTCUSDT SOLUSDT).

/remove <SYMBOL_1> <SYMBOL_2> ...: Xóa một hoặc nhiều mã coin khỏi danh sách theo dõi.

/list: Hiển thị tất cả các mã coin đang được theo dõi.

/backtest: Chạy mô phỏng backtest và gửi tất cả tín hiệu tìm được trong quá khứ lên channel.