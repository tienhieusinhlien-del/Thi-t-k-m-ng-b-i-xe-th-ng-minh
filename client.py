import paho.mqtt.client as mqtt
import json
import time
import random
import requests

BASE_URL  = "http://localhost:5000"
CARDS_URL = f"{BASE_URL}/api/cards"

# Cùng broker và topic với ESP32
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT   = 1883
MQTT_TOPIC  = "parking_system_888/rfid"  # Phải khớp với MQTT_TOPIC_IN trong app.py
CLIENT_ID   = f"python_sim_{random.randint(1000, 9999)}"

# Thẻ mặc định
DEFAULT_UIDS = ["UID_XE_01", "UID_XE_02", "UID_XE_03"]

def get_all_uids():
    try:
        res = requests.get(CARDS_URL, timeout=3)
        registered = list(res.json().get('danh_sach_the', {}).keys())
    except Exception:
        registered = []
    return list(dict.fromkeys(DEFAULT_UIDS + registered))

# Kết nối MQTT
client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv5)

def on_connect(cl, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[MQTT] Đã kết nối broker: {MQTT_BROKER}")
    else:
        print(f"[MQTT] Lỗi kết nối! RC={rc}")

client.on_connect = on_connect

print("========== MÔ PHỎNG QUẸT THẺ RFID (MQTT) ==========")
print(f"Broker : {MQTT_BROKER}:{MQTT_PORT}")
print(f"Topic  : {MQTT_TOPIC}")
print("(Nhấn Ctrl+C để dừng)\n")

client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
client.loop_start()

time.sleep(2)  # Chờ kết nối xong

queue = []
try:
    while True:
        # Nạp lại danh sách khi hết hàng đợi
        if not queue:
            all_uids = get_all_uids()
            print(f"\n[✓] Vòng mới — {len(all_uids)} thẻ sẽ quét lần lượt:")
            for uid in all_uids:
                tag = "[đăng ký]" if uid not in DEFAULT_UIDS else "[mặc định]"
                print(f"    • {uid}  {tag}")
            print()
            queue = all_uids[:]
            random.shuffle(queue)

        uid = queue.pop(0)
        payload = uid  # Gửi plain UID string, không phải JSON

        print(f"\n--- Publish MQTT: {uid} ---")
        result = client.publish(MQTT_TOPIC, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"  -> OK | Gửi lên topic '{MQTT_TOPIC}'")
        else:
            print(f"  -> LỖI publish! Code: {result.rc}")

        delay = random.randint(4, 8)
        print(f"  (Chờ {delay} giây...)")
        time.sleep(delay)

except KeyboardInterrupt:
    print("\nĐã dừng mô phỏng.")
    client.loop_stop()
    client.disconnect()
