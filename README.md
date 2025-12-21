# Face Recognition System with MQTT Integration

Hệ thống nhận diện khuôn mặt với tích hợp MQTT cho ESP32-S3 Eye và Flask server.

## 📁 Cấu trúc Project

```
datn/
├── app.py                    # Flask web server với face recognition
├── mqtt_service.py           # MQTT Service class
├── CameraWebServer/          # ESP32-S3 Eye Arduino code
│   ├── CameraWebServer.ino
│   └── camera_pins.h
├── faces/                    # Thư mục lưu khuôn mặt đã nhận diện
├── known_faces/             # Thư mục khuôn mặt đã biết
├── new_faces/               # Thư mục khuôn mặt mới
└── test.png                 # File test
```

## 🚀 Cài đặt và Chạy

### 1. Cài đặt dependencies Python

```bash
pip install flask opencv-python face-recognition paho-mqtt numpy
```

### 2. Chạy Flask Server

```bash
python app.py
```

Server sẽ chạy trên:
- **Local:** http://127.0.0.1:5000
- **Network:** http://192.168.1.44:5000

## 📡 MQTT Configuration

### Broker Settings
- **Host:** 192.168.1.44
- **Port:** 1883
- **Username:** admin
- **Password:** 131003
- **Protocol:** MQTT v3.1.1 (for better broker compatibility)
- **Keep Alive:** 60 seconds
- **Auto Reconnect:** Enabled with exponential backoff
- **QoS:** 0 (At most once delivery)
- **Last Will:** Publishes "offline" status on disconnect

### Topics
- **RECOGNITION:** Camera activation status
- **door/status:** Door lock status (LOCKED/OPEN)

### Connection Reliability Features
- ✅ **Automatic Reconnection** với exponential backoff
- ✅ **Connection Status Monitoring**
- ✅ **Message Retry Logic** (max 3 attempts)
- ✅ **QoS Level 1** cho reliability
- ✅ **Background Reconnection Thread**
- ✅ **Detailed Logging** với emoji indicators

## 🔧 API Endpoints

### GET /stream
Stream video từ ESP32-CAM với nhận diện khuôn mặt

### POST /test_publish
Test publish MQTT message
```json
{
  "topic": "TEST_TOPIC",
  "message": "Hello World"
}
```

### GET /status
Xem trạng thái hệ thống
```json
{
  "status": "running",
  "mqtt_connected": true,
  "known_faces": 5,
  "camera_url": "http://192.168.1.12:81/stream"
}
```

## 📋 MQTTService Class

Class `MQTTService` trong `mqtt_service.py` với **robust connection handling**:

### Basic Usage
```python
from mqtt_service import MQTTService

# Khởi tạo với custom settings
mqtt_service = MQTTService(
    broker="192.168.1.44",
    port=1883,
    username="admin",
    password="131003"
)

# Kết nối (tự động reconnect khi mất kết nối)
mqtt_service.connect()

# Publish message với retry logic
mqtt_service.publish_message("topic", "message")

# Subscribe với handler
def my_handler(message):
    print(f"Received: {message}")

mqtt_service.subscribe_topic("my_topic", my_handler)
```

### Advanced Features
```python
# Kiểm tra trạng thái kết nối chi tiết
status = mqtt_service.get_connection_status()
print(status)
# {
#   'connected': True,
#   'connecting': False,
#   'broker': '192.168.1.44:1883',
#   'subscribed_topics': ['RECOGNITION', 'door/status'],
#   'reconnect_thread_alive': False
# }

# Unsubscribe topic
mqtt_service.unsubscribe_topic("old_topic")

# Disconnect cleanly
mqtt_service.disconnect()
```

### Connection Reliability (MQTT v3.1.1)
- 🔄 **Auto-reconnection** với exponential backoff (1-60s)
- 📊 **QoS 0** cho compatibility với hầu hết brokers
- 🔁 **Retry logic** cho publish operations (3 attempts)
- 🧵 **Background threads** cho reconnection
- 📝 **Last Will message** publishes "offline" on unexpected disconnect
- 🟢 **Online status** published on successful connection
- 📝 **Detailed logging** với MQTT prefixes

## 🔌 ESP32-S3 Eye Setup

1. **Upload code** từ `CameraWebServer/CameraWebServer.ino`
2. **Kết nối hardware:**
   - Button: GPIO 2 ↔ GND
   - Relay: GPIO 4
   - Lock sensor: GPIO 13
3. **Cấu hình WiFi** trong code
4. **Power on** và nhấn button để khởi động camera

## 📝 Cách sử dụng

1. **ESP32-S3 Eye** tự động kết nối MQTT ngay khi khởi động
2. **Nhấn button** trên ESP32 để khởi động camera
3. Camera sẽ publish `"1"` lên topic `RECOGNITION`
4. **Flask server** nhận message và có thể xử lý logic tương ứng
5. Xem stream tại: `http://localhost:5000/stream`

## 🔧 Customization

### Thay đổi MQTT Broker
```python
mqtt_service = MQTTService(
    broker="your-broker-ip",
    port=1883,
    username="your-username",
    password="your-password"
)
```

### Thêm Topic Handler
```python
def custom_handler(message):
    # Xử lý message tùy chỉnh
    print(f"Custom topic received: {message}")

mqtt_service.subscribe_topic("CUSTOM_TOPIC", custom_handler)
```

## 📊 System Architecture

```
ESP32-S3 Eye ──MQTT──► Flask Server ──► Face Recognition
     │                       │
     └─ Camera Stream ───────┘
     │
     └─ Button Control ──► MQTT Messages
```

## 🐛 Troubleshooting

### MQTT Issues
- **Kết nối chập chờn:**
  - Kiểm tra network connectivity đến broker
  - Verify broker credentials (username/password)
  - Check firewall blocking port 1883
  - Test với MQTT client khác (MQTT Explorer)

- **Không thể publish/subscribe:**
  - Check `mqtt_service.is_connected()` status
  - View detailed status: `GET /status`
  - Check broker logs for authentication errors

### Camera Issues
- **Camera không stream:** Kiểm tra ESP32-CAM URL trong `CAMERA_URL`
- **ESP32 không kết nối:** Verify WiFi credentials trong Arduino code

### Face Recognition Issues
- **Face recognition lỗi:** Cài đặt dlib và face-recognition library đúng cách
- **OpenCV errors:** Cập nhật OpenCV: `pip install --upgrade opencv-python`

### Debug Commands
```bash
# Check MQTT status
curl http://localhost:5000/status

# Test MQTT publish
curl -X POST http://localhost:5000/test_publish \
  -H "Content-Type: application/json" \
  -d '{"topic":"TEST","message":"Hello"}'

# Run MQTT connection test
python test_mqtt.py
```

### Test Script
File `test_mqtt.py` để test MQTT connection reliability:

```bash
python test_mqtt.py
```

Features:
- ✅ Auto-reconnection testing
- ✅ Publish/subscribe testing
- ✅ Connection monitoring
- ✅ Graceful shutdown (Ctrl+C)

### Logs
Check console output for status messages:
- "Connected to MQTT broker" - Connection successful
- "Failed to connect to MQTT broker" - Connection failed
- "MQTT reconnection attempt" - Reconnecting in progress
- "MQTT published" - Message sent successfully
- "MQTT message received" - Message received from broker
- 📊 Status updates
- 🎯 Test handler messages

## 📄 License

Project này dành cho mục đích giáo dục và nghiên cứu.
