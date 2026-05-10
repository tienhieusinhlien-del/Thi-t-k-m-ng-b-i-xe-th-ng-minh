import eventlet
eventlet.monkey_patch() # Vá lỗi thư viện eventlet để hỗ trợ chạy bất đồng bộ (async) cho WebSockets

from flask import Flask, request, jsonify, send_file, Response, session, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
import json
import os
import threading
import sys
import paho.mqtt.client as mqtt
import csv
import io
import sqlite3
from typing import Dict, List, Any

# Hỗ trợ in tiếng Việt trên console Windows để không bị lỗi font
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8') 
    except Exception:
        pass

# Khởi tạo ứng dụng Web bằng Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'parking_secret!' # Khóa bảo mật cho session (phiên đăng nhập)
CORS(app) # Cho phép Cross-Origin Resource Sharing (Truy cập từ các domain khác)
socketio = SocketIO(app, cors_allowed_origins="*") # Khởi tạo SocketIO cho tính năng Real-time cập nhật giao diện

# ========================================================
# CẤU HÌNH MQTT (Broker trung gian giao tiếp phần cứng Wokwi)
# ========================================================
MQTT_BROKER     = "broker.hivemq.com" # Máy chủ MQTT công cộng
MQTT_PORT       = 1883                # Cổng tiêu chuẩn của giao thức MQTT
MQTT_TOPIC_IN   = "parking_system_888/rfid" # Kênh Server nghe mã thẻ từ ESP32 gửi lên
MQTT_TOPIC_OUT  = "parking_system_888/gate" # Kênh Server đẩy lệnh xuống ESP32 để mở cổng (Servo)
MQTT_CLIENT_ID  = "parking_server_flask_888" # Tên định danh của server Python khi kết nối MQTT

mqtt_client = None
mqtt_connected = False

# ========================================================
# CẤU HÌNH DATABASE CƠ SỞ DỮ LIỆU
# ========================================================
TONG_SO_CHO = 10 # Cố định tổng số chỗ đậu xe trong bãi
DATA_FILE   = 'parking_data.json' # File db JSON cũ (nay dùng SQLite)

# Hàm khởi tạo và tạo các bảng trong cơ sở dữ liệu SQLite (history.db)
def init_db():
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    
    # Tạo bảng lịch sử ra vào
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lich_su (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            bien_so TEXT,
            ten_chu_xe TEXT,
            thoi_gian TEXT,
            hanh_dong TEXT,
            thoi_gian_luu_tru TEXT,
            phi_gui_xe INTEGER
        )
    ''')
    
    # Tạo bảng danh sách thẻ đã đăng ký (thẻ tháng / vé tháng)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS danh_sach_the (
            uid TEXT PRIMARY KEY,
            bien_so TEXT,
            ten_chu_xe TEXT,
            ngay_dang_ky TEXT
        )
    ''')
    
    # Tạo bảng quản lý xe đang đỗ trong bãi (những xe chưa ra)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bai_xe (
            uid TEXT PRIMARY KEY,
            thoi_gian_vao TEXT
        )
    ''')
    conn.commit()
    
    # Đoạn code dưới đây dùng để chuyển dữ liệu từ file JSON cũ sang SQLite (Chỉ chạy 1 lần và tự xoá file JSON)
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}
                
                old_lich_su = data.get('lich_su', [])
                if old_lich_su:
                    cursor.execute("SELECT COUNT(*) FROM lich_su")
                    if cursor.fetchone()[0] == 0:
                        for entry in old_lich_su:
                            cursor.execute('''
                                INSERT INTO lich_su (uid, bien_so, ten_chu_xe, thoi_gian, hanh_dong, thoi_gian_luu_tru, phi_gui_xe)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                entry.get('uid'), entry.get('bien_so'), entry.get('ten_chu_xe'),
                                entry.get('thoi_gian'), entry.get('hanh_dong'), entry.get('thoi_gian_luu_tru'), entry.get('phi_gui_xe', 0)
                            ))
                        conn.commit()
                
                old_bai_xe = data.get('bai_xe', {})
                if old_bai_xe:
                    cursor.execute("SELECT COUNT(*) FROM bai_xe")
                    if cursor.fetchone()[0] == 0:
                        for b_uid, b_time in old_bai_xe.items():
                            cursor.execute("INSERT OR REPLACE INTO bai_xe (uid, thoi_gian_vao) VALUES (?, ?)", (b_uid, b_time))
                        conn.commit()
                
                old_the = data.get('danh_sach_the', {})
                if old_the:
                    cursor.execute("SELECT COUNT(*) FROM danh_sach_the")
                    if cursor.fetchone()[0] == 0:
                        for t_uid, t_info in old_the.items():
                            cursor.execute('''
                                INSERT OR REPLACE INTO danh_sach_the (uid, bien_so, ten_chu_xe, ngay_dang_ky)
                                VALUES (?, ?, ?, ?)
                            ''', (t_uid, t_info.get('bien_so', ''), t_info.get('ten_chu_xe', ''), t_info.get('ngay_dang_ky', '')))
                        conn.commit()

            os.remove(DATA_FILE)
            print("Đã migrate thành công tất cả dữ liệu sang SQLite và xoá file JSON.")
        except Exception as e:
            print(f"Lỗi migration JSON: {e}")
            
    conn.close()

# Gọi lệnh khởi tạo DB mỗi khi khởi động server
init_db()

# ================================
# CÁC HÀM TƯƠNG TÁC VỚI CƠ SỞ DỮ LIỆU (DB HELPERS)
# Mỗi lần Web muốn lưu, lấy thông tin đều gọi các hàm này
# ================================

# Lưu thông tin lịch sử của 1 chiếc xe (vào/ra) vào bảng 'lich_su'
def insert_history(entry):
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO lich_su (uid, bien_so, ten_chu_xe, thoi_gian, hanh_dong, thoi_gian_luu_tru, phi_gui_xe)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        entry.get('uid'), entry.get('bien_so'), entry.get('ten_chu_xe'),
        entry.get('thoi_gian'), entry.get('hanh_dong'),
        entry.get('thoi_gian_luu_tru'), entry.get('phi_gui_xe', 0)
    ))
    conn.commit()
    conn.close()

# Rút toàn bộ lịch sử ra/vào từ sqlite (thường dùng để xuất file CSV)
def get_all_history():
    conn = sqlite3.connect('history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM lich_su ORDER BY id ASC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Rút lịch sử vào ra của DUY NHẤT 1 thẻ (Tìm theo UID)
def get_history_by_uid(uid):
    conn = sqlite3.connect('history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM lich_su WHERE uid = ? ORDER BY id ASC', (uid,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Rút 50 dòng lịch sử mới nhất hiển thị ra Web (để tránh lấy nhiều gây lag trang)
def get_recent_history(limit=50):
    conn = sqlite3.connect('history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM (SELECT * FROM lich_su ORDER BY id DESC LIMIT ?) ORDER BY id ASC', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Rút danh sách những xe rác/xe vãng lai (Chưa đăng ký theo vé tháng nhưng từng quẹt vào)
def get_unique_guest_cars():
    conn = sqlite3.connect('history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT uid, MAX(bien_so) as bien_so, MAX(ten_chu_xe) as ten_chu_xe FROM lich_su GROUP BY uid')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Lấy danh sách Toàn bộ xe và chủ xe đã đăng ký vé tháng
def get_all_the():
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('SELECT uid, bien_so, ten_chu_xe, ngay_dang_ky FROM danh_sach_the')
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {'bien_so': row[1], 'ten_chu_xe': row[2], 'ngay_dang_ky': row[3]} for row in rows}

# Truy xuất thông tin của 1 chiếc vé tháng cụ thể
def get_the(uid):
    conn = sqlite3.connect('history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM danh_sach_the WHERE uid = ?', (uid,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'bien_so': row['bien_so'], 'ten_chu_xe': row['ten_chu_xe'], 'ngay_dang_ky': row['ngay_dang_ky']}
    return None

# Đăng ký / Thêm 1 thẻ xe mới vào danh sách vé tháng
def add_the(uid, info):
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO danh_sach_the (uid, bien_so, ten_chu_xe, ngay_dang_ky) VALUES (?, ?, ?, ?)',
                  (uid, info.get('bien_so', ''), info.get('ten_chu_xe', ''), info.get('ngay_dang_ky', '')))
    conn.commit()
    conn.close()

# Gỡ bỏ/Xoá bỏ vé tháng của 1 xe
def delete_the(uid):
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM danh_sach_the WHERE uid = ?', (uid,))
    conn.commit()
    conn.close()

# Lấy danh sách toàn bộ xe hiện đang ĐẬU BÊN TRONG BÃI 
def get_all_bai_xe():
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('SELECT uid, thoi_gian_vao FROM bai_xe')
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

# Ghi chú thích thẻ vừa quẹt "VÀO BÃI"
def add_xe_vao_bai(uid, thoi_gian_vao):
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO bai_xe (uid, thoi_gian_vao) VALUES (?, ?)', (uid, thoi_gian_vao))
    conn.commit()
    conn.close()

# Tháo bỏ biển thẻ vừa quẹt "RA BÃI" (Không còn đậu trong bãi nữa)
def remove_xe_khoi_bai(uid):
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('SELECT thoi_gian_vao FROM bai_xe WHERE uid = ?', (uid,))
    row = cursor.fetchone()
    if row:
        cursor.execute('DELETE FROM bai_xe WHERE uid = ?', (uid,))
        conn.commit()
        conn.close()
        return row[0]
    conn.close()
    return "Không rõ"

# Đếm tổng số lượng xe đang đậu trên sân
def count_xe_trong_bai():
    conn = sqlite3.connect('history.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM bai_xe')
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ========================================================
# LOGIC XỬ LÝ CHÍNH KHI NHẬN TÍN HIỆU QUẸT THẺ (CHỨC NĂNG LÕI)
# Phân tích xe đó là ĐANG VÀO hay ĐANG RA, và có mở cổng không?
# ========================================================
def xu_ly_uid(uid):
    uid = uid.strip().upper()
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S") # Lấy thời gian hiện tại
    
    # B1: Lấy thông tin xe (Neu ko dang ky thi là KHÁCH)
    info = get_the(uid) or {"bien_so": "CHƯA ĐK", "ten_chu_xe": "KHÁCH"}
    bien_so = info.get('bien_so')
    ten = info.get('ten_chu_xe')

    action_result = "OPEN" # Chữ Gửi lệnh MQTT mở cổng
    log_entry = {
        "uid": uid, "bien_so": bien_so, "ten_chu_xe": ten,
        "thoi_gian": now_str
    }

    # B2: Lấy thông tin bãi đỗ xe để soi xem xe này ĐÃ CÓ TRONG BÃI hay CHƯA
    bai_xe_hien_tai = get_all_bai_xe()
    if uid in bai_xe_hien_tai:
        # NẾU ĐÃ CÓ MẶT TRONG BÃI => Mạch được hiểu là quẹt để XUẤT BẾN / RA BÃI
        vao_luc_str = str(bai_xe_hien_tai.get(uid))
        remove_xe_khoi_bai(uid) # Loại bỏ xe ra khỏi bãi
        log_entry["hanh_dong"] = "RA KHỎI BÃI"
        log_entry["thoi_gian_luu_tru"] = f"Vào lúc {vao_luc_str}"
        
        # B2-1: Tính tiền tự động (giả định tính 10.000đ/ 1 Cứ mỗi tiếng)
        try:
            if vao_luc_str != "Không rõ":
                if len(vao_luc_str) <= 8: # Chặn lỗi dữ liệu cũ kiểu cũ
                    today = datetime.now().strftime("%Y-%m-%d")
                    vao_luc_str = f"{today} {vao_luc_str}"
                
                vao_dt = datetime.strptime(vao_luc_str, "%Y-%m-%d %H:%M:%S")
                duration = now_dt - vao_dt
                hours = max(1.0, duration.total_seconds() / 3600.0) # Tính giờ
                fee = int(hours * 10000) # Qui đổi tiền
                log_entry["phi_gui_xe"] = fee
            else:
                log_entry["phi_gui_xe"] = 10000
        except Exception as e:
            print(f"Lỗi tính phí: {e}")
            log_entry["phi_gui_xe"] = 10000 

        print(f"[{now_str}] XE RA: {uid} | Mở cổng...")
    else:
        # NẾU KHÔNG CÓ TRONG BÃI => Mạch được hiểu là quẹt để NHẬP BẾN / VÀO BÃI
        # B2-2: Nhưng phải kiểm tra xem bãi đã hết chỗ chưa
        if count_xe_trong_bai() >= TONG_SO_CHO:
            print(f"[{now_str}] BÃI ĐẦY! Từ chối: {uid}")
            return "FULL" # Bãi đầy thì trả về Full, không mở cổng
        
        # Nếu còn chỗ trống => Nhận xe
        add_xe_vao_bai(uid, now_str) 
        log_entry["hanh_dong"] = "VÀO BÃI"
        log_entry["thoi_gian_luu_tru"] = ""
        print(f"[{now_str}] XE VÀO: {uid} | Mở cổng...")

    # Ghi log lịch sử lưu cơ sở dữ liệu
    insert_history(log_entry)
    
    # B3: Lệnh xuất yêu cầu mở cổng Servo đá qua Mạch Wokwi Bằng MQTT - ĐẨY DỮ LIỆU ĐẾN WOKWI
    if mqtt_client:
        mqtt_client.publish(MQTT_TOPIC_OUT, "OPEN")
    
    # B4: Broadcast tức thời về Trình Duyệt Web qua tính năng SocketIO để UI cập nhật không cần Reset Load
    tat_ca_xe = {}
    danh_sach_the_hien_tai = get_all_the()
    for t_uid, t_info in danh_sach_the_hien_tai.items():
        tat_ca_xe[t_uid] = t_info.copy()
    guest_cars = get_unique_guest_cars()
    for entry in guest_cars:
        g_uid = str(entry.get('uid', ''))
        if g_uid and g_uid not in tat_ca_xe:
            tat_ca_xe[g_uid] = {
                'bien_so': entry.get('bien_so', 'CHƯA ĐK'),
                'ten_chu_xe': entry.get('ten_chu_xe', 'Khách'),
                'is_guest': True
            }

    # Bắn tín hiệu và Gói Data Sang Giao diện
    socketio.emit('parking_update', {
        'action': log_entry["hanh_dong"],
        'uid': uid,
        'bien_so': bien_so,
        'status': get_current_status(),
        'lich_su_hoat_dong': get_recent_history(50),
        'danh_sach_the': danh_sach_the_hien_tai,
        'tat_ca_xe': tat_ca_xe
    })
    
    return action_result

# Hàm thu thập gom số liệu chỗ trống/số chỗ đỗ trên sân
def get_current_status():
    bai_xe_hien_tai = get_all_bai_xe()
    return {
        'tong_so_cho': TONG_SO_CHO,
        'so_cho_trong': TONG_SO_CHO - len(bai_xe_hien_tai),
        'danh_sach_xe_trong_bai': bai_xe_hien_tai,
        'mqtt_connected': mqtt_connected
    }

# ========================================================
# CÁC HÀM XỬ LÝ LẮNG NGHE MQTT VỚI MẠCH (LẤY DỮ LIỆU WOKWI)
# ========================================================
# Xảy ra khi file kết nối MQTT Thành Công với Broker
def on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print(f"[MQTT] Đã kết nối thành công (rc={rc}). Đang subscribe...")
        client.subscribe(MQTT_TOPIC_IN) # Bật chế độ lắng nghe (Hóng chuyện) kênh MQTT thẻ
        socketio.emit('mqtt_status', {'connected': True}) # Báo chớp Tín Hiệu Xanh lá cây ở phần Web
    else:
        mqtt_connected = False
        print(f"[MQTT] Kết nối thất bại với mã lỗi: {rc}")

# Xác nhận đã lắng nghe (Subscribe)
def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print(f"[MQTT] Đã Subscribe thành công vào các topic (mid: {mid})")

# CALLBACK XẢY RA KHI WOKWI ĐÃ QUẸT ĐƯỢC THẺ VÀ BẮN DỮ LIỆU ĐÓ MANG VỀ
def on_message(client, userdata, msg):
    try:
        # Bước 1: Decode giải mã gói tin ra chữ String
        payload_raw = msg.payload.decode('utf-8').strip()
        print(f"[MQTT] Nhận dữ liệu: {payload_raw}")
        try:
            # Nếu payload là JSON (như {"uid": "..."}), ta phân tách bóc chuỗi
            data = json.loads(payload_raw)
            if isinstance(data, dict):
                uid = data.get('uid', str(payload_raw))
            else:
                uid = str(payload_raw)
        except json.JSONDecodeError:
            # Còn không phải thì ép nguyên chuỗi đó lấy UUID
            uid = payload_raw
        
        # Đẩy gói Data thẻ vừa lấy được vào hàm Phân Loại cửa VÀO/RA
        xu_ly_uid(str(uid))
    except Exception as e:
        print(f"[MQTT] Lỗi xử lý tin nhắn: {e}")

# Hàm móc nối phần mềm Python kết nối với HiveMQ Broker
def start_mqtt():
    global mqtt_client
    print(f"[MQTT] Đang khởi tạo client (ID: {MQTT_CLIENT_ID})...")
    # Cài đặt hàm kết nối phiên bản 2 chuẩn mực
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv5)
    
    # Mapping Function - Khai báo nối
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_subscribe = on_subscribe
    try:
        print(f"[MQTT] Đang kết nối tới Broker {MQTT_BROKER}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60) # Thiết lập cổng kết nối (Connect server)
        print("[MQTT] Bắt đầu vòng lặp lắng nghe (Non-blocking)...")
        while True:
            mqtt_client.loop(timeout=1.0) # Background listening 
            socketio.sleep(0.1) # Nhường luồng cho Web không bị nghẽn
    except Exception as e:
        print(f"[MQTT] Lỗi kết nối Broker: {e}")

# ========================================================
# FLASK API ROUTING: KẾT NỐI VÀ ĐIỀU HƯỚNG TRANG WEB GIAO DIỆN
# ========================================================
# Trang đăng nhập của bãi gửi xe
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Đối chiếu pass db
        try:
            with open('login_db.json', 'r', encoding='utf-8') as f:
                db = json.load(f)
        except Exception:
            db = {"admin": "123456"}
            
        if db.get(username) == password:
            session['user'] = username # Xác nhận Session
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Sai tên đăng nhập hoặc mật khẩu'}), 401
            
    return send_file('login.html')

# Rout xóa Session Cookies xuất bản web (Logout)
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# Rout chính: Dashboard Hệ thống gửi File Html (khi gõ localhost:5000)
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return send_file('parking.html')

# API URL Web có thể Fetch gọi lấy số lượng/trạng thái xe tĩnh
@app.route('/api/status', methods=['GET'])
def get_status():
    # Gom tất cả các xe (cả đã đăng ký và vãng lai) để hiển thị ở tab Thống kê
    tat_ca_xe = {}
    
    danh_sach_the_hien_tai = get_all_the()
    # 1. Xe đã đăng ký
    for uid, info in danh_sach_the_hien_tai.items():
        tat_ca_xe[uid] = info.copy()
    
    # 2. Xe vãng lai (từ lịch sử)
    guest_cars = get_unique_guest_cars()
    for entry in guest_cars:
        uid = str(entry.get('uid', ''))
        if uid and uid not in tat_ca_xe:
            tat_ca_xe[uid] = {
                'bien_so': entry.get('bien_so', 'CHƯA ĐK'),
                'ten_chu_xe': entry.get('ten_chu_xe', 'Khách'),
                'is_guest': True
            }

    # Bắn ra dữ liệu chuỗi Json chuẩn
    return jsonify({
        **get_current_status(),
        'lich_su_hoat_dong': get_recent_history(50), 
        'danh_sach_the': danh_sach_the_hien_tai,
        'tat_ca_xe': tat_ca_xe
    }), 200

# Trả Dữ Liệu mảng thẻ đã đăng ký vé tháng
@app.route('/api/cards', methods=['GET'])
def get_cards():
    return jsonify({'danh_sach_the': get_all_the()}), 200

# API thêm đăng ký danh bạ xe (Quản trị viên sử dụng)
@app.route('/api/cards/register', methods=['POST'])
def register():
    data = request.json
    uid = data.get('uid', '').strip().upper()
    if not uid: return jsonify({'message': 'Thiếu UID'}), 400
    
    info = {
        'bien_so': data.get('bien_so', 'UNKNOWN'),
        'ten_chu_xe': data.get('ten_chu_xe', 'GUEST'),
        'ngay_dang_ky': datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    add_the(uid, info)
    return jsonify({'message': 'Đã đăng ký thẻ mới'}), 200

# Tiêu diệt gỡ thẻ UID (Remove database)
@app.route('/api/cards/<uid>', methods=['DELETE'])
def delete_card(uid):
    uid = uid.strip().upper()
    if get_the(uid):
        delete_the(uid)
        return jsonify({'message': f'Đã xoá thẻ {uid}'}), 200
    return jsonify({'message': 'Không tìm thấy thẻ'}), 404

# Nút Export Xuất File Excel CSV toàn bộ lịch sử (Làm Báo Cáo Doanh Thu)
@app.route('/api/export', methods=['GET'])
def export_csv():
    output = io.StringIO()
    output.write('\ufeff') # Add BOM Encoding UTF-8 hỗ trợ Excel Vietsub Tránh lỗi font!
    writer = csv.writer(output)
    writer.writerow(['UID', 'Biển Số', 'Chủ Xe', 'Thời Gian', 'Hành Động', 'Thời Gian Lưu Trú', 'Phí (VNĐ)'])
    lich_su_all = get_all_history()
    for entry in lich_su_all:
        writer.writerow([
            entry.get('uid'), entry.get('bien_so'), entry.get('ten_chu_xe'),
            entry.get('thoi_gian'), entry.get('hanh_dong'), 
            entry.get('thoi_gian_luu_tru'), entry.get('phi_gui_xe', 0)
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=parking_history.csv"}
    )

# Gọi logic hàm thống kê chi tiết lượt gửi/ra của từng xe bằng biểu đồ Chart.JS
@app.route('/api/stats/<uid>', methods=['GET'])
def get_stats(uid):
    uid = uid.strip().upper()
    car_history = get_history_by_uid(uid)
    
    entries = []
    for h in car_history:
        if h.get('hanh_dong') == "VÀO BÃI":
            try:
                t_str = str(h.get('thoi_gian', ''))
                if len(t_str) <= 8: 
                    continue
                dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                entries.append(dt)
            except: continue

    now = datetime.now()
    days = {}
    for i in range(7):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        days[d] = 0
    for dt in entries:
        d_str = dt.strftime("%Y-%m-%d")
        if d_str in days:
            days[d_str] += 1
            
    weeks = {}
    for i in range(4):
        w_dt = now - timedelta(weeks=i)
        w_num = w_dt.isocalendar()[1]
        weeks[f"Tuần {w_num}"] = 0
    for dt in entries:
        w_num = dt.isocalendar()[1]
        key = f"Tuần {w_num}"
        if key in weeks:
            weeks[key] += 1

    months = {f"Tháng {m}": 0 for m in range(1, 13)}
    for dt in entries:
        if dt.year == now.year:
            months[f"Tháng {dt.month}"] += 1

    return jsonify({
        'uid': uid,
        'info': get_the(uid) or {},
        'total_entries': len(entries),
        'by_day': days,
        'by_week': weeks,
        'by_month': months,
        'history': car_history[::-1][:20]
    })

# Giả lập quét thẻ thử nghiệm trên Web mà KHÔNG cần mạch thực tế
@app.route('/api/scan_rfid', methods=['POST'])
def scan_rfid():
    data = request.json
    uid = data.get('uid', '').strip().upper()
    if not uid: return jsonify({'message': 'Thiếu UID'}), 400
    res = xu_ly_uid(uid)
    return jsonify({'message': f'Thẻ {uid}: {res}', 'status': res}), 200

# ========================================================
# KẾT NỐI VÀ CHẠY HỆ THỐNG / KICKSTART SYSTEM PÙNG!
# (Thằng này là lệnh main cốt lõi chạy đầu tiên để kéo mọi thứ lên)
# ========================================================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("KHỞI ĐỘNG HỆ THỐNG QUẢN LÝ BÃI ĐỖ XE")
    print("="*50)
    
    # 1 Lệnh yêu cầu cho file MQTT Luôn Hoạt Động Kèm Luồng (Đa Nhiệm/Background Task)
    print("[1/2] Đang khởi động MQTT background task...")
    socketio.start_background_task(start_mqtt)
    print("-> MQTT task đã được lên lịch chạy.")
    
    # 2 Mở khoá và Launch (Phát sóng) cho Website khởi tạo Socket Real-time
    print("[2/2] Đang khởi động Web Server (SocketIO)...")
    print(f"-> Địa chỉ truy cập: http://127.0.0.1:5000")
    print("-> Nhấn Ctrl + C để dừng server.")
    
    try:
        # allow_unsafe_werkzeug=True hỗ trợ chạy debug trên một số môi trường đặc biệt
        # host='0.0.0.0' để biến máy chạy file này thành Web Server Hosting thực sự cho truy cập lan. Port port mặc định là 5000.
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"\n[LỖI SERVER]: {e}")