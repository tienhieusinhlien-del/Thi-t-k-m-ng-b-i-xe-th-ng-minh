#include <WiFi.h>
#include <PubSubClient.h>
#include <MFRC522.h>
#include <SPI.h>

// ==========================================
// CẤU HÌNH MQTT VÀ WIFI (SỬA Ở ĐÂY)
// ==========================================

// WiFi Wokwi (dùng "Wokwi-GUEST", không cần mật khẩu)
const char* ssid     = "Wokwi-GUEST";
const char* password = "";

// MQTT Broker công khai - không cần tài khoản
const char* mqtt_server = "broker.hivemq.com";
const int   mqtt_port   = 1883;
const char* mqtt_topic  = "parking_system_888/rfid";   // Topic gửi UID lên
const char* client_id   = "wokwi_esp32_01"; // ID định danh thiết bị

// ==========================================

// RFID RC522
#define SS_PIN  21
#define RST_PIN 22
MFRC522 mfrc522(SS_PIN, RST_PIN);

WiFiClient   espClient;
PubSubClient mqttClient(espClient);

// ==========================================
// KẾT NỐI WiFi
// ==========================================
void connectWiFi() {
  Serial.print("Dang ket noi WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n>>> DA KET NOI WiFi!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

// ==========================================
// KẾT NỐI MQTT BROKER
// ==========================================
void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Dang ket noi MQTT broker...");
    if (mqttClient.connect(client_id)) {
      Serial.println(" OK!");
      Serial.print("Topic publish: ");
      Serial.println(mqtt_topic);
    } else {
      Serial.print(" Loi! RC=");
      Serial.println(mqttClient.state());
      Serial.println("Thu lai sau 3 giay...");
      delay(3000);
    }
  }
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();

  connectWiFi();

  mqttClient.setServer(mqtt_server, mqtt_port);
  connectMQTT();

  Serial.println("=========================================");
  Serial.println("San sang! Dua the RFID vao de quet...");
  Serial.println("=========================================");
}

// ==========================================
// LOOP
// ==========================================
void loop() {
  // Đảm bảo kết nối MQTT liên tục
  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  // Chờ thẻ RFID
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    delay(50);
    return;
  }

  // Đọc UID
  String uid_str = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    uid_str += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
    uid_str += String(mfrc522.uid.uidByte[i], HEX);
  }
  uid_str.toUpperCase();

  Serial.println("\n--- CO THE MOI! ---");
  Serial.println("UID: " + uid_str);

  // Tạo JSON payload và publish lên MQTT
  String payload = "{\"uid\":\"" + uid_str + "\"}";
  if (mqttClient.publish(mqtt_topic, payload.c_str())) {
    Serial.println(">>> Da publish len MQTT: " + payload);
  } else {
    Serial.println("!!! Loi publish MQTT!");
  }

  // Chống dội thẻ
  mfrc522.PICC_HaltA();
  delay(1500);
}
