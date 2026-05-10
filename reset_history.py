import sqlite3

def reset_history(clear_parking_lot=True):
    try:
        conn = sqlite3.connect('history.db')
        cursor = conn.cursor()
        
        # Xóa toàn bộ dữ liệu trong bảng lịch sử
        cursor.execute('DELETE FROM lich_su')
        
        # Reset lại index id (autoincrement) về 0
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="lich_su"')
        
        # Tùy chọn: Xóa cả xe đang nằm trong bãi hiển thị
        if clear_parking_lot:
            cursor.execute('DELETE FROM bai_xe')
            
        conn.commit()
        
        # Chạy lệnh VACUUM để SQLite thực sự giải phóng dung lượng ổ cứng, 
        # làm cho file history.db nhẹ đi sau khi xóa.
        cursor.execute('VACUUM')
        conn.commit()

        conn.close()
        print("Đã reset biểu đồ và lịch sử xe ra vào thành công! (Vẫn giữ nguyên các thẻ đã đăng ký)")
    except Exception as e:
        print(f"Có lỗi xảy ra: {e}")

if __name__ == "__main__":
    confirm = input("Bạn có chắc chắn muốn xóa toàn bộ lịch sử xe ra vào không? (y/n): ")
    if confirm.lower() == 'y':
        reset_history(clear_parking_lot=True)
    else:
        print("Đã hủy quá trình reset.")
