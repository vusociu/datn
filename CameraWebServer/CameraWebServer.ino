#include "esp_camera.h"
#include <WiFi.h>
#include <PubSubClient.h>

//
// WARNING!!! PSRAM IC required for UXGA resolution and high JPEG quality
//            Ensure ESP32 Wrover Module or other board with PSRAM is selected
//            Partial images will be transmitted if image exceeds buffer size
//
//            You must select partition scheme from the board menu that has at least 3MB APP space.
//            Face Recognit ion is DISABLED for ESP32 and ESP32-S2, because it takes up from 15
//            seconds to process single frame. Face Detection is ENABLED if PSRAM is enabled as well

// ===================
// Select camera model
// ===================
// #define CAMERA_MODEL_WROVER_KIT // Has PSRAM
// #define CAMERA_MODEL_ESP_EYE  // Has PSRAM
#define CAMERA_MODEL_ESP32S3_EYE // Has PSRAM
//#define CAMERA_MODEL_M5STACK_PSRAM // Has PSRAM
//#define CAMERA_MODEL_M5STACK_V2_PSRAM // M5Camera version B Has PSRAM
//#define CAMERA_MODEL_M5STACK_WIDE // Has PSRAM
//#define CAMERA_MODEL_M5STACK_ESP32CAM // No PSRAM
//#define CAMERA_MODEL_M5STACK_UNITCAM // No PSRAM
//#define CAMERA_MODEL_M5STACK_CAMS3_UNIT  // Has PSRAM
// #define CAMERA_MODEL_AI_THINKER // Has PSRAM
//#define CAMERA_MODEL_TTGO_T_JOURNAL // No PSRAM
// #define CAMERA_MODEL_XIAO_ESP32S3 // Has PSRAM
// ** Espressif Internal Boards **
//#define CAMERA_MODEL_ESP32_CAM_BOARD
//#define CAMERA_MODEL_ESP32S2_CAM_BOARD
//#define CAMERA_MODEL_ESP32S3_CAM_LCD
//#define CAMERA_MODEL_DFRobot_FireBeetle2_ESP32S3 // Has PSRAM
//#define CAMERA_MODEL_DFRobot_Romeo_ESP32S3 // Has PSRAM
#include "camera_pins.h"

// ===========================
// Door Configuration - 4 doors
// ===========================
// Relay pins để mở khóa (LOW = mở, HIGH = đóng)
#define RELAY_PIN_1 4
#define RELAY_PIN_2 5
#define RELAY_PIN_3 6
#define RELAY_PIN_4 7

// Status pins để đọc trạng thái khóa (LOW = đóng, HIGH = mở)
#define LOCK_STATUS_PIN_1 1
#define LOCK_STATUS_PIN_2 2
#define LOCK_STATUS_PIN_3 15
#define LOCK_STATUS_PIN_4 16

// Button pins để gửi execute SEND và GET
#define BUTTON_SEND_PIN 17
#define BUTTON_GET_PIN 18

// Door names matching app.py
const char* DOOR_1 = "door_1";
const char* DOOR_2 = "door_2";
const char* DOOR_3 = "door_3";
const char* DOOR_4 = "door_4";

// ===========================
// Enter your WiFi credentials
// ===========================
const char *ssid = "Hong Thanh";
const char *password = "khuavanxoi";

// ===========================
// MQTT Configuration
// ===========================
const char *mqtt_server = "192.168.1.44";
const int mqtt_port = 1883;
const char *mqtt_user = "admin";
const char *mqtt_pass = "131003";
const char *mqtt_topic_device_door_open = "device/door/open";
const char *mqtt_topic_server_door_status = "server/door/status";
const char *mqtt_topic_server_door_execute = "server/door/execute";

void startCameraServer();
void setupLedFlash(int pin);
void initCameraAndServer();
void connectMQTT();
void publishMessage(const char* topic, const char* message);
int getDoorIndex(const char* doorName);
int getRelayPin(int doorIndex);
int getStatusPin(int doorIndex);
const char* getDoorName(int doorIndex);
void openDoor(int doorIndex);
String parseJsonDoor(const String& jsonMessage);
void checkButtonPresses();

// Door opening state tracking
struct DoorState {
  bool opening;
  unsigned long openStart;
  int lastLockState;
};

DoorState doorStates[4] = {
  {false, 0, HIGH},
  {false, 0, HIGH},
  {false, 0, HIGH},
  {false, 0, HIGH}
};

bool cameraInitialized = false;
bool mqttConnected = false;
const unsigned long DOOR_OPEN_TIME = 500; // milliseconds

// Button debounce variables
int lastButtonSendState = HIGH;
int lastButtonGetState = HIGH;
unsigned long lastDebounceTimeSend = 0;
unsigned long lastDebounceTimeGet = 0;
const unsigned long DEBOUNCE_DELAY = 200; // milliseconds

WiFiClient espClient;
PubSubClient client(espClient);

void initCameraAndServer() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;  // for streaming
  //config.pixel_format = PIXFORMAT_RGB565; // for face detection/recognition
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  // if PSRAM IC present, init with UXGA resolution and higher JPEG quality
  //                      for larger pre-allocated frame buffer.
  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 10;
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
      // Limit the frame size when PSRAM is not available
      config.frame_size = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  } else {
    // Best option for face detection/recognition
    config.frame_size = FRAMESIZE_240X240;
#if CONFIG_IDF_TARGET_ESP32S3
    config.fb_count = 2;
#endif
  }

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  // camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  // initial sensors are flipped vertically and colors are a bit saturated
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);        // flip it back
    s->set_brightness(s, 1);   // up the brightness just a bit
    s->set_saturation(s, -2);  // lower the saturation
  }
  // drop down frame size for higher initial frame rate
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_QVGA);
  }

#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

#if defined(CAMERA_MODEL_ESP32S3_EYE)
  s->set_vflip(s, 1);
#endif

// Setup LED FLash if LED pin is defined in camera_pins.h
#if defined(LED_GPIO_NUM)
  setupLedFlash(LED_GPIO_NUM);
#endif

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  startCameraServer();

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("' to connect");

  // Publish MQTT message when camera is initialized
}


void publishMessage(const char* topic, const String& message) {
  if (mqttConnected && client.connected()) {
    if (client.publish(topic, message.c_str())) {
      Serial.print("Published '");
      Serial.print(message);
      Serial.print("' to topic: ");
      Serial.println(topic);
    } else {
      Serial.println("Failed to publish MQTT message");
    }
  } else {
    Serial.println("MQTT not connected, skipping publish");
  }
}

void connectMQTT() {
  if (!client.connected()) {
    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(mqttCallback);

    Serial.print("Attempting MQTT connection...");
    String clientId = "ESP32Camera-";
    clientId += String(random(0xffff), HEX);

    if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {
      Serial.println("connected");
      // Subscribe to device/door/open topic để nhận lệnh mở cửa từ server
      subscribeTopic(mqtt_topic_device_door_open);
      mqttConnected = true;
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      mqttConnected = false;
    }
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");

  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.println(message);

  // Xử lý message từ topic device/door/open
  if (strcmp(topic, mqtt_topic_device_door_open) == 0) {
    // Parse JSON message: {"door": "door_1"}
    String doorName = parseJsonDoor(message);
    
    if (doorName.length() > 0) {
      int doorIndex = getDoorIndex(doorName.c_str());
      if (doorIndex >= 0 && doorIndex < 4) {
        Serial.print("Opening door: ");
        Serial.println(doorName);
        openDoor(doorIndex);
      } else {
        Serial.print("Invalid door name: ");
        Serial.println(doorName);
      }
    } else {
      Serial.println("Failed to parse door name from JSON");
    }
  }
}

// Parse JSON message để lấy tên cửa
// Format: {"door": "door_1"}
String parseJsonDoor(const String& jsonMessage) {
  // Tìm "door" trong JSON
  int doorIndex = jsonMessage.indexOf("\"door\"");
  if (doorIndex == -1) {
    return "";
  }
  
  // Tìm dấu " sau "door":
  int colonIndex = jsonMessage.indexOf(":", doorIndex);
  if (colonIndex == -1) {
    return "";
  }
  
  // Tìm dấu " đầu tiên sau dấu :
  int quoteStart = jsonMessage.indexOf("\"", colonIndex);
  if (quoteStart == -1) {
    return "";
  }
  
  // Tìm dấu " tiếp theo để kết thúc giá trị
  int quoteEnd = jsonMessage.indexOf("\"", quoteStart + 1);
  if (quoteEnd == -1) {
    return "";
  }
  
  return jsonMessage.substring(quoteStart + 1, quoteEnd);
}

// Lấy index của cửa từ tên cửa
int getDoorIndex(const char* doorName) {
  if (strcmp(doorName, DOOR_1) == 0) return 0;
  if (strcmp(doorName, DOOR_2) == 0) return 1;
  if (strcmp(doorName, DOOR_3) == 0) return 2;
  if (strcmp(doorName, DOOR_4) == 0) return 3;
  return -1;
}

// Lấy tên cửa từ index
const char* getDoorName(int doorIndex) {
  switch(doorIndex) {
    case 0: return DOOR_1;
    case 1: return DOOR_2;
    case 2: return DOOR_3;
    case 3: return DOOR_4;
    default: return "";
  }
}

// Lấy chân relay từ index cửa
int getRelayPin(int doorIndex) {
  switch(doorIndex) {
    case 0: return RELAY_PIN_1;
    case 1: return RELAY_PIN_2;
    case 2: return RELAY_PIN_3;
    case 3: return RELAY_PIN_4;
    default: return -1;
  }
}

// Lấy chân status từ index cửa
int getStatusPin(int doorIndex) {
  switch(doorIndex) {
    case 0: return LOCK_STATUS_PIN_1;
    case 1: return LOCK_STATUS_PIN_2;
    case 2: return LOCK_STATUS_PIN_3;
    case 3: return LOCK_STATUS_PIN_4;
    default: return -1;
  }
}

// Mở cửa (kích hoạt relay)
void openDoor(int doorIndex) {
  if (doorIndex < 0 || doorIndex >= 4) {
    return;
  }
  
  int relayPin = getRelayPin(doorIndex);
  if (relayPin == -1) {
    return;
  }
  
  // Kích hoạt relay (LOW = mở)
  digitalWrite(relayPin, LOW);
  doorStates[doorIndex].opening = true;
  doorStates[doorIndex].openStart = millis();
  
  Serial.print("Door ");
  Serial.print(getDoorName(doorIndex));
  Serial.println(" opening...");
}

void subscribeTopic(const char* topic) {
  if (client.connected()) {
    if (client.subscribe(topic)) {
      Serial.print("Subscribed to: ");
      Serial.println(topic);
    } else {
      Serial.println("Failed to subscribe");
    }
  }
}

// Kiểm tra và xử lý nút bấm SEND và GET
void checkButtonPresses() {
  // Đọc trạng thái hiện tại của nút SEND
  int currentButtonSendState = digitalRead(BUTTON_SEND_PIN);
  
  // Kiểm tra nếu trạng thái thay đổi (có thể do nhiễu hoặc nhấn nút)
  if (currentButtonSendState != lastButtonSendState) {
    // Reset timer debounce
    lastDebounceTimeSend = millis();
  }
  
  // Nếu đã đủ thời gian debounce
  if ((millis() - lastDebounceTimeSend) > DEBOUNCE_DELAY) {
    // Nếu nút được nhấn (LOW do INPUT_PULLUP)
    if (currentButtonSendState == LOW && lastButtonSendState == HIGH) {
      // Gửi message "SEND" đến topic server/door/execute
      if (mqttConnected && client.connected()) {
        publishMessage(mqtt_topic_server_door_execute, "SEND");
        Serial.println("SEND button pressed - published SEND command");
      } else {
        Serial.println("MQTT not connected, cannot send SEND command");
      }
    }
  }
  
  // Cập nhật trạng thái cuối cùng của nút SEND
  lastButtonSendState = currentButtonSendState;
  
  // Đọc trạng thái hiện tại của nút GET
  int currentButtonGetState = digitalRead(BUTTON_GET_PIN);
  
  // Kiểm tra nếu trạng thái thay đổi
  if (currentButtonGetState != lastButtonGetState) {
    // Reset timer debounce
    lastDebounceTimeGet = millis();
  }
  
  // Nếu đã đủ thời gian debounce
  if ((millis() - lastDebounceTimeGet) > DEBOUNCE_DELAY) {
    // Nếu nút được nhấn (LOW do INPUT_PULLUP)
    if (currentButtonGetState == LOW && lastButtonGetState == HIGH) {
      // Gửi message "GET" đến topic server/door/execute
      if (mqttConnected && client.connected()) {
        publishMessage(mqtt_topic_server_door_execute, "GET");
        Serial.println("GET button pressed - published GET command");
      } else {
        Serial.println("MQTT not connected, cannot send GET command");
      }
    }
  }
  
  // Cập nhật trạng thái cuối cùng của nút GET
  lastButtonGetState = currentButtonGetState;
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  
  // Khởi tạo các chân relay cho 4 cửa
  pinMode(RELAY_PIN_1, OUTPUT);
  pinMode(RELAY_PIN_2, OUTPUT);
  pinMode(RELAY_PIN_3, OUTPUT);
  pinMode(RELAY_PIN_4, OUTPUT);
  
  // Khởi tạo các chân status cho 4 cửa
  pinMode(LOCK_STATUS_PIN_1, INPUT_PULLUP);
  pinMode(LOCK_STATUS_PIN_2, INPUT_PULLUP);
  pinMode(LOCK_STATUS_PIN_3, INPUT_PULLUP);
  pinMode(LOCK_STATUS_PIN_4, INPUT_PULLUP);
  
  // Đặt tất cả relay ở trạng thái HIGH (đóng)
  digitalWrite(RELAY_PIN_1, HIGH);
  digitalWrite(RELAY_PIN_2, HIGH);
  digitalWrite(RELAY_PIN_3, HIGH);
  digitalWrite(RELAY_PIN_4, HIGH);
  
  // Đọc trạng thái ban đầu của các cửa
  doorStates[0].lastLockState = digitalRead(LOCK_STATUS_PIN_1);
  doorStates[1].lastLockState = digitalRead(LOCK_STATUS_PIN_2);
  doorStates[2].lastLockState = digitalRead(LOCK_STATUS_PIN_3);
  doorStates[3].lastLockState = digitalRead(LOCK_STATUS_PIN_4);
  
  Serial.println("System started. 4-door lock system initialized.");

  // Khởi tạo các chân nút bấm SEND và GET
  pinMode(BUTTON_SEND_PIN, INPUT_PULLUP);
  pinMode(BUTTON_GET_PIN, INPUT_PULLUP);
  
  // Đọc trạng thái ban đầu của các nút
  lastButtonSendState = digitalRead(BUTTON_SEND_PIN);
  lastButtonGetState = digitalRead(BUTTON_GET_PIN);
  
  Serial.println("SEND and GET buttons initialized.");

  // Configure button pin (if needed)
  pinMode(BUTTON_GPIO_NUM, INPUT_PULLUP);

  // Connect to WiFi
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");

  // Connect to MQTT broker
  connectMQTT();
}

void loop() {
  // Check button press (LOW when pressed due to INPUT_PULLUP)
  // if (digitalRead(BUTTON_GPIO_NUM) == LOW && !cameraInitialized) {
  //   Serial.println("Button pressed! Starting camera...");
  //   delay(200); // Debounce delay

  //   initCameraAndServer();
  //   cameraInitialized = true;

  //   Serial.println("Camera stream started successfully!");
  // }

  // Maintain MQTT connection
  if (!client.connected()) {
    connectMQTT();
  }
  client.loop();

  // Kiểm tra nút bấm SEND và GET
  checkButtonPresses();

  // Xử lý đóng relay sau thời gian mở cửa cho từng cửa
  for (int i = 0; i < 4; i++) {
    if (doorStates[i].opening && millis() - doorStates[i].openStart >= DOOR_OPEN_TIME) {
      int relayPin = getRelayPin(i);
      if (relayPin != -1) {
        digitalWrite(relayPin, HIGH);
        doorStates[i].opening = false;
        Serial.print("Door ");
        Serial.print(getDoorName(i));
        Serial.println(" relay closed");
      }
    }
  }

  // Kiểm tra trạng thái đóng/mở của từng cửa
  for (int i = 0; i < 4; i++) {
    int statusPin = getStatusPin(i);
    if (statusPin == -1) {
      continue;
    }
    
    int lockState = digitalRead(statusPin);
    
    // Nếu trạng thái thay đổi
    if (lockState != doorStates[i].lastLockState) {
      doorStates[i].lastLockState = lockState;
      
      const char* doorName = getDoorName(i);
      
      // LOW = cửa đóng (locked), HIGH = cửa mở (open)
      if (lockState == LOW) {
        // Cửa đã đóng - gửi message đến server
        // Format: "door_1" hoặc JSON {"door": "door_1"}
        publishMessage(mqtt_topic_server_door_status, doorName);
        Serial.print("Door ");
        Serial.print(doorName);
        Serial.println(" closed (LOCKED)");
      } else {
        Serial.print("Door ");
        Serial.print(doorName);
        Serial.println(" opened");
      }
    }
  }

  delay(100); // Small delay to prevent excessive polling
}
