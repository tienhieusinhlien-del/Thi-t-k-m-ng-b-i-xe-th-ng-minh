#define SS_PIN 5
#define RST_PIN 22
#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <LiquidCrystal_I2C.h>

// --- Cấu hình WiFi (Wokwi) ---
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// --- Cấu hình MQTT Broker (HiveMQ) ---
const char* mqtt_server = "broker.hivemq.com";
const char* topic_out   = "parking_system_888/rfid"; // Gửi lên server  → khớp MQTT_TOPIC_IN
const char* topic_in    = "parking_system_888/gate"; // Nhận từ server  → khớp MQTT_TOPIC_OUT

WiFiClient espClient;
PubSubClient client(espClient);
Servo gate;
MFRC522 rfid(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) message += (char)payload[i];
  
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  Serial.println(message);

  if (String(topic) == topic_in && message == "OPEN") {
    Serial.println(">>> DONG Y! MO CONG...");
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("MOI VAO/RA");
    gate.write(90); // Mở gate 90 độ
    delay(3000);    // Chờ 3 giây
    gate.write(0);  // Đóng gate
    lcd.clear();
    lcd.print("QUET THE...");
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect("ESP32_Parking_Client")) {
      Serial.println("connected");
      client.subscribe(topic_in);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);

  SPI.begin();
  rfid.PCD_Init();
  gate.attach(13);
  gate.write(0);
  
  lcd.init();
  lcd.backlight();
  lcd.print("QUET THE...");
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  // Kiểm tra có thẻ mới
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  // Lấy UID
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    uid += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  Serial.print("UID: ");
  Serial.println(uid);
  lcd.clear();
  lcd.print("UID: " + uid);

  // Gửi UID lên MQTT
  client.publish(topic_out, uid.c_str());

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  delay(1000);
}
