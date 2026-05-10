# Smart Parking System (Hệ thống bãi đỗ xe thông minh)

Hệ thống quản lý bãi đỗ xe thông minh sử dụng **ESP32**, **RFID**, và ứng dụng web thời gian thực với **Python (Flask, Socket.IO)**.

## 🚀 Tính năng nổi bật
- **Quản lý xe vào/ra:** Nhận diện thẻ RFID để ghi nhận thời gian vào/ra của phương tiện.
- **Cập nhật thời gian thực (Real-time):** Giao diện web tự động cập nhật trạng thái bãi đỗ và lịch sử thông qua WebSockets (Socket.IO) mà không cần tải lại trang.
- **Giao diện Web trực quan:** Theo dõi số lượng chỗ trống, lịch sử xe và quản lý thẻ RFID.
- **Lưu trữ dữ liệu:** Sử dụng cơ sở dữ liệu SQLite (`history.db`) gọn nhẹ.
- **Tích hợp IoT:** Giao tiếp với thiết bị phần cứng ESP32 qua giao thức MQTT.

## 🛠️ Công nghệ sử dụng
- **Backend:** Python, Flask, Flask-SocketIO
- **Frontend:** HTML, CSS, JavaScript
- **Database:** SQLite
- **Hardware/IoT:** ESP32, Cảm biến RFID (MFRC522), Giao thức MQTT

## 📁 Cấu trúc thư mục chính
```text
.
├── app.py                  # File khởi chạy máy chủ Backend (Flask)
├── parking.html            # Giao diện chính quản lý bãi đỗ xe
├── login.html              # Giao diện đăng nhập hệ thống
├── Code.ino                # Mã nguồn C++ chạy trên vi điều khiển ESP32
├── esp32_rfid/             # Các đoạn code liên quan đến phần cứng
├── client.py / simulate_esp32.py # Các script giả lập thiết bị ESP32 đẩy dữ liệu
├── reset_history.py        # Script tiện ích để xóa/reset dữ liệu trong Database
└── requirements.txt        # Danh sách các thư viện Python cần cài đặt
```

## ⚙️ Hướng dẫn cài đặt và khởi chạy

### 1. Yêu cầu hệ thống
- Máy tính đã cài đặt [Python](https://www.python.org/downloads/) (khuyến nghị bản 3.7 trở lên).

### 2. Cài đặt các thư viện cần thiết
Mở Terminal/Command Prompt tại thư mục dự án và chạy lệnh:
```bash
pip install -r requirements.txt
```

### 3. Khởi động Server
Chạy file backend chính:
```bash
python app.py
```

### 4. Truy cập hệ thống
Sau khi server báo chạy thành công, mở trình duyệt web và truy cập:
```
http://localhost:5000
```
*(Lưu ý: Nếu có màn hình đăng nhập, hãy sử dụng tài khoản được lưu trữ trong hệ thống)*.

---
*Dự án Thiết kế mạng truyền thông dữ liệu - Nhóm 4 (D18DTVT2).*
