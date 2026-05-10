import requests
import time
import random

# Địa chỉ server Flask
BASE_URL  = "http://127.0.0.1:5000"
SCAN_URL  = f"{BASE_URL}/api/scan_rfid"
CARDS_URL = f"{BASE_URL}/api/cards"

# Thẻ mặc định luôn có sẵn
DEFAULT_UIDS = ["UID_XE_01", "UID_XE_02", "UID_XE_03"]

def get_all_uids():
    """Lấy danh sách thẻ đăng ký từ server và gộp với thẻ mặc định."""
    try:
        res = requests.get(CARDS_URL, timeout=3)
        res.raise_for_status()
        registered = list(res.json().get('danh_sach_the', {}).keys())
    except Exception as e:
        print(f"  [!] Lỗi lấy danh sách thẻ: {e}")
        registered = []

    # Gộp thẻ mặc định + thẻ đăng ký, không trùng lặp, giữ thứ tự
    combined = list(dict.fromkeys(DEFAULT_UIDS + registered))
    return combined

def simulate_scan(uid):
    """Giả lập quẹt 1 thẻ RFID."""
    print(f"\n--- Quẹt thẻ: {uid} ---")
    try:
        res  = requests.post(SCAN_URL, json={"uid": uid}, timeout=3)
        data = res.json()
        print(f"  -> {res.status_code} | {data.get('message', data)}")
    except requests.exceptions.ConnectionError:
        print("  [!] Lỗi kết nối! Hãy đảm bảo server app.py đang chạy.")
    except Exception as e:
        print(f"  [!] Lỗi: {e}")


if __name__ == "__main__":
    print("========== MÔ PHỎNG QUẸT THẺ RFID ==========")
    print("(Nhấn Ctrl+C để dừng)\n")

    queue = []  # Hàng đợi round-robin

    while True:
        # Nếu hàng đợi trống → nạp lại danh sách mới nhất và xáo trộn
        if not queue:
            all_uids = get_all_uids()

            print(f"\n[✓] Vòng mới — {len(all_uids)} thẻ sẽ được quét lần lượt:")
            for uid in all_uids:
                tag = "[đăng ký]" if uid not in DEFAULT_UIDS else "[mặc định]"
                print(f"    • {uid}  {tag}")
            print()

            # Xáo trộn để thứ tự ngẫu nhiên nhưng đảm bảo mỗi thẻ đều được quét
            queue = all_uids[:]
            random.shuffle(queue)

        # Lấy thẻ tiếp theo trong hàng đợi
        uid = queue.pop(0)
        simulate_scan(uid)

        delay = random.randint(3, 8)
        print(f"  (Chờ {delay} giây...)")
        time.sleep(delay)