from flask import Flask, Response, request
import cv2
import face_recognition
import os
import numpy as np
import threading
import time
from mqtt_service import MQTTService

# ESP32-CAM stream URL
CAMERA_URL = "http://192.168.1.12:81/stream"

app = Flask(__name__)
# cap = cv2.VideoCapture(CAMERA_URL)

# Initialize MQTT Service
mqtt_service = MQTTService()

# === Khởi tạo biến toàn cục ===
FACE_DIR = "faces"
os.makedirs(FACE_DIR, exist_ok=True)

known_encodings = []
known_ids = []
next_id = 0  # ID người dùng mới sẽ tăng dần


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
    """Handler for door/status topic"""
    print(f"Door status: {message}")
    # Có thể thêm logic để xử lý trạng thái cửa


def generate():
    global next_id

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[Warning] Cannot read frame — reconnecting...")
            cap.open(CAMERA_URL)
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

        success = mqtt_service.publish_message(topic, message)
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
    mqtt_status = mqtt_service.get_connection_status()
    return {
        'status': 'running',
        'mqtt': mqtt_status,
        'known_faces': len(known_ids),
        'camera_url': CAMERA_URL,
        'face_recognition_enabled': True
    }


if __name__ == "__main__":
    # Subscribe to topics
    mqtt_service.subscribe("door/status", door_status_handler)

    mqtt_service.connect()

    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
