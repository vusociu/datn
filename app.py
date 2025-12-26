from flask import Flask, Response, request
import cv2
import face_recognition
import os
import numpy as np
import threading
import time
import json
from mqtt_service import MQTTService
from redis_service import RedisService
from app_enum import StatusDoor

# Camera index (0 = webcam laptop đầu tiên)
CAMERA_URL = 0  # Tạm thời dùng camera laptop, có thể đổi về "http://192.168.1.12:81/stream" khi dùng ESP32-CAM

app = Flask(__name__)
cap = None  # Sẽ được khởi tạo khi cần

# Initialize MQTT Service
mqtt_service = MQTTService()

redis = RedisService(host="192.168.1.44", port=6379, db=1, password="Omt@1234")

doors = [
    "door_1",
    "door_2",
    "door_3",
    "door_4",
]

# === Khởi tạo biến toàn cục ===
FACE_DIR = "faces"
os.makedirs(FACE_DIR, exist_ok=True)

known_encodings = []
known_ids = []
next_id = 0  # ID người dùng mới sẽ tăng dần

# Lock để đảm bảo thread-safe khi xử lý nhận diện khuôn mặt
face_recognition_lock = threading.Lock()


def save_face_image(face_image, user_id):
    """Lưu khuôn mặt vào thư mục tương ứng với ID"""
    user_dir = os.path.join(FACE_DIR, f"id_{user_id}")
    os.makedirs(user_dir, exist_ok=True)
    count = len(os.listdir(user_dir))
    filename = os.path.join(user_dir, f"{count + 1}.jpg")
    cv2.imwrite(filename, face_image)
    print(f"Saved face of id_{user_id} -> {filename}")



# Topic Handlers
def recognition_handler(message):
    """Handler for RECOGNITION topic"""
    print(f"Recognition status: {message}")
    if message == "1":
        print("Camera system activated")
        # Có thể thêm logic để bắt đầu nhận diện khuôn mặt
    elif message == "0":
        print("Camera system deactivated")


def door_status_handler(message):
    """Handler for door/status topic - xử lý khi tủ đóng"""
    print(f"Door status: {message}")
    try:
        # Parse message: format có thể là "door_1" hoặc JSON {"door": "door_1"}
        if message.startswith("{"):
            data = json.loads(message)
            door_name = data.get("door")
        else:
            door_name = message
        
        if door_name in doors:
            # Cập nhật trạng thái tủ là đã đóng (USED)
            data_door = redis.hgetall("data_door")
            if door_name in data_door:
                door_data = json.loads(data_door[door_name])
                door_data["status"] = StatusDoor.USED.value
                redis.hset("data_door", {door_name: json.dumps(door_data)})
                print(f"Đã cập nhật trạng thái tủ {door_name} là đã đóng")
    except Exception as e:
        print(f"Lỗi xử lý door status: {e}")


def get_empty_door():
    """Tìm tủ trống đầu tiên từ trên xuống dưới"""
    data_door = redis.hgetall("data_door")
    
    for door in doors:
        if door not in data_door:
            # Tủ chưa có trong Redis -> trống
            return door
        
        try:
            door_data = json.loads(data_door[door])
            status = door_data.get("status")
            if status == StatusDoor.EMPTY.value:
                return door
        except:
            # Nếu parse lỗi, coi như tủ trống
            return door
    
    return None  # Không còn tủ trống


def recognize_face_from_camera():
    """Nhận diện khuôn mặt từ camera và trả về user_id"""
    global known_encodings, known_ids, next_id
    
    cap_temp = cv2.VideoCapture(CAMERA_URL)
    if not cap_temp.isOpened():
        print("Không thể kết nối camera")
        return None
    
    # Đọc một số frame để đảm bảo có frame tốt
    for _ in range(5):
        ret, frame = cap_temp.read()
        if ret and frame is not None:
            break
    
    if not ret or frame is None:
        cap_temp.release()
        return None
    
    # Chuyển sang RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Phát hiện khuôn mặt
    face_locations = face_recognition.face_locations(rgb_frame)
    
    if len(face_locations) == 0:
        cap_temp.release()
        return None
    
    try:
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        if len(face_encodings) == 0:
            cap_temp.release()
            return None
        
        # Lấy khuôn mặt đầu tiên
        face_encoding = face_encodings[0]
        
        with face_recognition_lock:
            # Nếu chưa có dữ liệu nào, thêm người đầu tiên
            if len(known_encodings) == 0:
                user_id = next_id
                next_id += 1
                known_encodings.append(face_encoding)
                known_ids.append(user_id)
                face_image = frame[face_locations[0][0]:face_locations[0][2], 
                                  face_locations[0][3]:face_locations[0][1]]
                save_face_image(face_image, user_id)
                cap_temp.release()
                return user_id
            else:
                # So khớp với các khuôn mặt đã biết
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.45)
                face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                best_match_index = np.argmin(face_distances) if len(face_distances) > 0 else None
                
                # Nếu trùng với người đã có
                if best_match_index is not None and matches[best_match_index]:
                    user_id = known_ids[best_match_index]
                    cap_temp.release()
                    return user_id
                else:
                    # Khuôn mặt mới -> tạo ID mới
                    user_id = next_id
                    next_id += 1
                    known_encodings.append(face_encoding)
                    known_ids.append(user_id)
                    face_image = frame[face_locations[0][0]:face_locations[0][2], 
                                      face_locations[0][3]:face_locations[0][1]]
                    save_face_image(face_image, user_id)
                    cap_temp.release()
                    return user_id
    except Exception as e:
        print(f"Lỗi nhận diện khuôn mặt: {e}")
        cap_temp.release()
        return None


def find_door_by_user_id(user_id):
    """Tìm tủ được gán cho user_id"""
    data_door = redis.hgetall("data_door")
    
    for door, door_data_str in data_door.items():
        try:
            door_data = json.loads(door_data_str)
            if door_data.get("user_id") == user_id:
                return door
        except:
            continue
    
    return None


def door_excute_handler(message):
    """Handler cho door/execute topic - xử lý gửi đồ và lấy đồ"""
    print(f"Door execute: {message}")
    
    if message == "SEND":
        # Xử lý gửi đồ
        print("Nhận yêu cầu gửi đồ")
        
        # Kiểm tra tủ trống
        empty_door = get_empty_door()
        
        if empty_door is None:
            # Tất cả tủ đã được sử dụng
            print("Tất cả tủ đã được sử dụng")
            mqtt_service.publish("door/full", "ALL_DOORS_OCCUPIED", qos=1)
            return
        
        # Nhận diện khuôn mặt
        print("Đang nhận diện khuôn mặt...")
        user_id = recognize_face_from_camera()
        
        if user_id is None:
            print("Không thể nhận diện khuôn mặt")
            mqtt_service.publish("door/error", "FACE_RECOGNITION_FAILED", qos=1)
            return
        
        print(f"Đã nhận diện khuôn mặt với ID: {user_id}")
        
        # Lưu thông tin vào Redis
        door_data = {
            "status": StatusDoor.EMPTY.value,  # Tủ đang mở (chưa đóng)
            "user_id": user_id
        }
        redis.hset("data_door", {empty_door: json.dumps(door_data)})
        
        # Gửi message mở tủ
        mqtt_service.publish("door/open", json.dumps({"door": empty_door}), qos=1)
        print(f"Đã gán tủ {empty_door} cho user_id {user_id}")
        
    elif message == "GET":
        # Xử lý lấy đồ
        print("Nhận yêu cầu lấy đồ")
        
        # Nhận diện khuôn mặt
        print("Đang nhận diện khuôn mặt...")
        user_id = recognize_face_from_camera()
        
        if user_id is None:
            print("Không thể nhận diện khuôn mặt")
            mqtt_service.publish("door/error", "FACE_RECOGNITION_FAILED", qos=1)
            return
        
        print(f"Đã nhận diện khuôn mặt với ID: {user_id}")
        
        # Tìm tủ được gán cho user_id này
        door_name = find_door_by_user_id(user_id)
        
        if door_name is None:
            print(f"Không tìm thấy tủ cho user_id {user_id}")
            mqtt_service.publish("door/error", json.dumps({"error": "NO_DOOR_ASSIGNED", "user_id": user_id}), qos=1)
            return
        
        # Gửi message mở tủ
        mqtt_service.publish("door/open", json.dumps({"door": door_name}), qos=1)
        print(f"Đã mở tủ {door_name} cho user_id {user_id}")
        
        # Xóa dữ liệu tủ sau khi lấy đồ (hoặc đánh dấu là trống)
        door_data = {
            "status": StatusDoor.EMPTY.value,
            "user_id": None
        }
        redis.hset("data_door", {door_name: json.dumps(door_data)})


def generate():
    global next_id, cap
    
    # Khởi tạo camera nếu chưa có
    if cap is None:
        cap = cv2.VideoCapture(CAMERA_URL)

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[Warning] Cannot read frame — reconnecting...")
            cap.release()
            cap = cv2.VideoCapture(CAMERA_URL)
            continue

        # Đảm bảo frame hợp lệ
        if frame.ndim != 3 or frame.shape[2] != 3:
            print("[Warning] Invalid frame format")
            continue

        # Chuyển sang RGB (face_recognition dùng RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Phát hiện khuôn mặt
        face_locations = face_recognition.face_locations(rgb_frame)

        # Nếu không có khuôn mặt thì tiếp tục stream
        if len(face_locations) == 0:
            _, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            continue

        # Mã hóa khuôn mặt
        try:
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        except Exception as e:
            print(f"[Error] Encoding error: {e}")
            continue

        # Duyệt qua từng khuôn mặt phát hiện được
        with face_recognition_lock:
            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):

                # Nếu chưa có dữ liệu nào, thêm người đầu tiên
                if len(known_encodings) == 0:
                    user_id = next_id
                    next_id += 1
                    known_encodings.append(face_encoding)
                    known_ids.append(user_id)
                    face_image = frame[top:bottom, left:right]
                    save_face_image(face_image, user_id)
                else:
                    # So khớp với các khuôn mặt đã biết
                    matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.45)
                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    best_match_index = np.argmin(face_distances) if len(face_distances) > 0 else None

                    # Nếu trùng với người đã có
                    if True in matches and best_match_index is not None and matches[best_match_index]:
                        user_id = known_ids[best_match_index]
                    else:
                        # Khuôn mặt mới -> tạo ID mới
                        user_id = next_id
                        next_id += 1
                        known_encodings.append(face_encoding)
                        known_ids.append(user_id)
                        face_image = frame[top:bottom, left:right]
                        save_face_image(face_image, user_id)

            # Vẽ khung + ID
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {user_id}", (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Trả frame cho stream
        _, jpeg = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')


@app.route('/stream')
def stream():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/test_publish', methods=['POST'])
def test_publish():
    """Test endpoint to publish MQTT message via POST request"""
    try:
        data = request.get_json()

        if not data:
            return {"error": "No JSON data provided"}, 400

        topic = data.get('topic')
        message = data.get('message')

        if not topic or not message:
            return {"error": "Both 'topic' and 'message' are required"}, 400

        success = mqtt_service.publish(topic, message, qos=1)
        if success:
            return {
                "success": True,
                "message": f"Published '{message}' to topic '{topic}'"
            }
        else:
            return {"error": "Failed to publish message"}, 500

    except Exception as e:
        return {"error": f"Failed to publish: {str(e)}"}, 500


@app.route('/status')
def status():
    """Get system status"""
    mqtt_status = mqtt_service.is_connected()
    return {
        'status': 'running',
        'mqtt': 'connected' if mqtt_status else 'disconnected',
        'known_faces': len(known_ids),
        'camera_url': CAMERA_URL,
        'face_recognition_enabled': True
    }


if __name__ == "__main__":
    # Subscribe to topics
    mqtt_service.subscribe("door/status", door_status_handler)
    mqtt_service.subscribe("door/execute", door_excute_handler)

    mqtt_service.connect()

    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
