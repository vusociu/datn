from flask import Flask, Response, request, render_template
import cv2
import os
import numpy as np
import threading
import time
import json
from mqtt_service import MQTTService
from redis_service import RedisService
from app_enum import StatusDoor
from facenet_service import FaceNetService

# Camera index (0 = first laptop webcam)
CAMERA_URL = 0  # Temporarily using laptop camera, can be changed to "http://192.168.1.12:81/stream" when using ESP32-CAM

SERVER_DOOR_STATUS="server/door/status"
SERVER_DOOR_EXECUTE="server/door/execute"

DEVICE_DOOR_OPEN="device/door/open"

app = Flask(__name__)
cap = None  # Will be initialized when needed

# Initialize MQTT Service
mqtt_service = MQTTService()

redis = RedisService(host="172.19.201.135", port=6379, db=1, password="vund1310")

doors = [
    "door_1",
    "door_2",
    "door_3",
    "door_4",
]

# === Initialize global variables ===
FACE_DIR = "faces"
os.makedirs(FACE_DIR, exist_ok=True)

# Initialize FaceNet service
facenet_service = FaceNetService()

# Initialize face recognition data (will be loaded from Redis)
known_encodings = []
known_ids = []
next_id = 0  # New user ID will increment

# Lock to ensure thread-safe face recognition processing
face_recognition_lock = threading.Lock()

# Load face recognition data from Redis on startup


def save_face_data_to_redis():
    """Save face recognition data to Redis"""
    try:
        with face_recognition_lock:
            face_data = {
                "known_ids": known_ids,
                "next_id": next_id,
                "known_encodings": [enc.tolist() for enc in known_encodings]  # Convert numpy arrays to lists
            }
            redis.set("face_recognition_data", json.dumps(face_data))
            print(f"Saved face data to Redis: {len(known_ids)} faces, next_id={next_id}")
    except Exception as e:
        print(f"Error saving face data to Redis: {e}")


def update_next_id():
    """Update next_id to the smallest unused ID"""
    global next_id, known_ids

    with face_recognition_lock:
        if len(known_ids) == 0:
            next_id = 0
        else:
            # Find the smallest unused ID starting from 0
            used_ids = set(known_ids)
            next_id = 0
            while next_id in used_ids:
                next_id += 1
        print(f"Updated next_id to {next_id}")


def remove_user_face_data(user_id):
    """Remove face recognition data for a specific user"""
    global known_encodings, known_ids

    try:
        with face_recognition_lock:
            # Find index of user_id in known_ids
            if user_id in known_ids:
                index = known_ids.index(user_id)

                # Remove from all arrays
                known_encodings.pop(index)
                known_ids.pop(index)

                # Update next_id to reuse freed ID
                update_next_id()

                # Remove face images folder
                user_dir = os.path.join(FACE_DIR, f"id_{user_id}")
                if os.path.exists(user_dir):
                    import shutil
                    shutil.rmtree(user_dir)
                    print(f"Removed face images folder: {user_dir}")
                else:
                    print(f"Face images folder not found: {user_dir}")

                # Save updated data to Redis
                save_face_data_to_redis()

                print(f"Removed face recognition data for user_id {user_id}")
                return True
            else:
                print(f"User_id {user_id} not found in known_ids")
                return False

    except Exception as e:
        print(f"Error removing face data for user_id {user_id}: {e}")
        return False


def load_face_data_from_redis():
    """Load face recognition data from Redis"""
    global known_encodings, known_ids, next_id
    try:
        face_data_str = redis.get("face_recognition_data")
        if face_data_str:
            face_data = json.loads(face_data_str)
            with face_recognition_lock:
                known_ids = face_data.get("known_ids", [])
                # Convert lists back to numpy arrays
                known_encodings = [np.array(enc) for enc in face_data.get("known_encodings", [])]

                # Update next_id based on loaded data
                update_next_id()
            print(f"Loaded face data from Redis: {len(known_ids)} faces, next_id={next_id}")
            return True
        else:
            print("No face data found in Redis, starting fresh")
            return False
    except Exception as e:
        print(f"Error loading face data from Redis: {e}")
        return False


def save_face_image(face_image, user_id):
    """Save face image to directory corresponding to ID"""
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
        # Can add logic to start face recognition
    elif message == "0":
        print("Camera system deactivated")


def door_status_handler(message):
    """Handler for door/status topic - handle when door is closed"""
    print(f"Door status: {message}")
    try:
        # Parse message: format can be "door_1" or JSON {"door": "door_1"}
        data = json.loads(message)
        door_name = data.get("door")
        door_status = data.get("status")
        if door_name in doors:
            # Update door status to closed (USED)
            data_door = redis.hgetall("data_door")
            if door_name in data_door:
                door_data = json.loads(data_door[door_name])
                door_data["status"] = door_status
                redis.hset("data_door", {door_name: json.dumps(door_data)})
                print(f"Updated door {door_name} status to {'OPEN' if door_status == StatusDoor.OPEN.value else 'CLOSED'}")
    except Exception as e:
        print(f"Error processing door status: {e}")


def get_empty_door():
    """Find first empty door from top to bottom"""
    data_door = redis.hgetall("data_door")
    
    for door in doors:
        if door not in data_door:
            # Door not in Redis -> empty
            return door
        else:
            door_data = json.loads(data_door[door])
            user_id = door_data.get("user_id")
            if user_id is None:
                return door
    return None  # No empty doors left


def recognize_face_from_camera():
    """Recognize face from camera and return user_id"""
    global known_encodings, known_ids, next_id
    
    cap_temp = cv2.VideoCapture(CAMERA_URL)
    if not cap_temp.isOpened():
        print("Cannot connect to camera")
        return None
    
    # Read some frames to ensure we have a good frame
    for _ in range(5):
        ret, frame = cap_temp.read()
        if ret and frame is not None:
            break
    
    if not ret or frame is None:
        cap_temp.release()
        return None
    
    # Detect faces using FaceNet
    face_locations = facenet_service.detect_faces(frame)
    
    if len(face_locations) == 0:
        cap_temp.release()
        return None
    
    try:
        # Get encoding of first face
        face_encoding = facenet_service.get_face_encoding(frame, face_locations[0])
        if face_encoding is None:
            cap_temp.release()
            return None
        
        with face_recognition_lock:
            # If no data yet, add first person
            if len(known_encodings) == 0:
                user_id = next_id
                next_id += 1
                known_encodings.append(face_encoding)
                known_ids.append(user_id)
                top, right, bottom, left = face_locations[0]
                face_image = frame[top:bottom, left:right]
                save_face_image(face_image, user_id)
                # save_face_data_to_redis()  # Save to Redis after adding new face
                cap_temp.release()
                return user_id
            else:
                # Match with known faces
                matches = facenet_service.compare_faces(known_encodings, face_encoding, tolerance=0.6)
                face_distances = facenet_service.face_distance(known_encodings, face_encoding)
                best_match_index = np.argmin(face_distances) if len(face_distances) > 0 else None
                
                # If matches existing person
                if best_match_index is not None and matches[best_match_index]:
                    user_id = known_ids[best_match_index]
                    cap_temp.release()
                    return user_id
                else:
                    # New face -> create new ID
                    user_id = next_id
                    next_id += 1
                    known_encodings.append(face_encoding)
                    known_ids.append(user_id)
                    top, right, bottom, left = face_locations[0]
                    face_image = frame[top:bottom, left:right]
                    save_face_image(face_image, user_id)
                    # save_face_data_to_redis()  # Save to Redis after adding new face
                    cap_temp.release()
                    return user_id
    except Exception as e:
        print(f"Face recognition error: {e}")
        cap_temp.release()
        return None


def find_door_by_user_id(user_id):
    """Find door assigned to user_id"""
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
    """Handler for door/execute topic - handle sending and retrieving items"""
    print(f"Door execute: {message}")
    
    if message == "SEND":
        # Handle sending items
        print("Received send request")
        
        # Check for empty door
        empty_door = get_empty_door()
        
        if empty_door is None:
            # All doors are occupied
            print("All doors are occupied")
            mqtt_service.publish("device/door/full", "ALL_DOORS_OCCUPIED", qos=1)
            return
        
        # Recognize face
        print("Recognizing face...")
        user_id = recognize_face_from_camera()
        
        if user_id is None:
            print("Cannot recognize face")
            mqtt_service.publish("door/error", "FACE_RECOGNITION_FAILED", qos=1)
            return
        
        print(f"Recognized face with ID: {user_id}")
        
        # Save information to Redis
        door_data = {
            "status": StatusDoor.OPEN.value,  # Door is open (not closed yet)
            "user_id": user_id
        }
        redis.hset("data_door", {empty_door: json.dumps(door_data)})
        
        # Send message to open door
        mqtt_service.publish(DEVICE_DOOR_OPEN, json.dumps({"door": empty_door}), qos=1)
        print(f"Assigned door {empty_door} to user_id {user_id}")
        
    elif message == "GET":
        # Handle retrieving items
        print("Received retrieve request")
        
        # Recognize face
        print("Recognizing face...")
        user_id = recognize_face_from_camera()
        
        if user_id is None:
            print("Cannot recognize face")
            mqtt_service.publish("door/error", "FACE_RECOGNITION_FAILED", qos=1)
            return
        
        print(f"Recognized face with ID: {user_id}")
        
        # Find door assigned to this user_id
        door_name = find_door_by_user_id(user_id)
        
        if door_name is None:
            print(f"Cannot find door for user_id {user_id}")
            mqtt_service.publish("device/door/error", json.dumps({"error": "NO_DOOR_ASSIGNED", "user_id": user_id}), qos=1)
            return
        
        # Send message to open door
        mqtt_service.publish(DEVICE_DOOR_OPEN, json.dumps({"door": door_name}), qos=1)
        print(f"Opened door {door_name} for user_id {user_id}")

        # Remove user's face recognition data after successful retrieval
        remove_user_face_data(user_id)

        # Clear door data after retrieving (or mark as empty)
        door_data = {
            "status": StatusDoor.OPEN.value,
            "user_id": None
        }
        redis.hset("data_door", {door_name: json.dumps(door_data)})


def generate():
    global next_id, cap
    
    # Initialize camera if not already initialized
    if cap is None:
        cap = cv2.VideoCapture(CAMERA_URL)

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[Warning] Cannot read frame — reconnecting...")
            cap.release()
            cap = cv2.VideoCapture(CAMERA_URL)
            continue

        # Ensure frame is valid
        if frame.ndim != 3 or frame.shape[2] != 3:
            print("[Warning] Invalid frame format")
            continue

        # Detect faces using FaceNet
        face_locations = facenet_service.detect_faces(frame)

        # If no faces detected, continue streaming
        if len(face_locations) == 0:
            _, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            continue

        # Iterate through detected faces
        with face_recognition_lock:
            for face_location in face_locations:
                top, right, bottom, left = face_location
                
                # Encode face
                try:
                    face_encoding = facenet_service.get_face_encoding(frame, face_location)
                    if face_encoding is None:
                        continue
                except Exception as e:
                    print(f"[Error] Encoding error: {e}")
                    continue

                # If no data yet, add first person
                if len(known_encodings) == 0:
                    user_id = next_id
                    next_id += 1
                    known_encodings.append(face_encoding)
                    known_ids.append(user_id)
                    face_image = frame[top:bottom, left:right]
                    save_face_image(face_image, user_id)
                    save_face_data_to_redis()  # Save to Redis after adding new face
                else:
                    # Match with known faces
                    matches = facenet_service.compare_faces(known_encodings, face_encoding, tolerance=0.6)
                    face_distances = facenet_service.face_distance(known_encodings, face_encoding)
                    best_match_index = np.argmin(face_distances) if len(face_distances) > 0 else None

                    # If matches existing person
                    if best_match_index is not None and matches[best_match_index]:
                        user_id = known_ids[best_match_index]
                    else:
                        # New face -> create new ID
                        user_id = next_id
                        next_id += 1
                        known_encodings.append(face_encoding)
                        known_ids.append(user_id)
                        face_image = frame[top:bottom, left:right]
                        save_face_image(face_image, user_id)
                        save_face_data_to_redis()  # Save to Redis after adding new face

                # Draw bounding box + ID
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, f"ID {user_id}", (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Return frame for stream
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
        'face_recognition_enabled': True,
        'face_recognition_method': 'FaceNet'
    }


@app.route('/doors')
def get_doors_status():
    """Display door status with beautiful UI"""
    try:
        data_door = redis.hgetall("data_door")

        doors_status = {}
        stats = {'empty': 0, 'used': 0, 'open': 0}

        for door_name in doors:
            if door_name in data_door:
                try:
                    door_data = json.loads(data_door[door_name])
                    door_data["status"] = "EMPTY" if door_data["user_id"] is None else "USED"
                    doors_status[door_name] = door_data

                    # Count statistics
                    status = 'EMPTY' if door_data.get('user_id') is None else 'USED'
                    if status == 'EMPTY':
                        stats['empty'] += 1
                    elif status == 'USED':
                        stats['used'] += 1

                except json.JSONDecodeError:
                    doors_status[door_name] = {"error": "Invalid JSON data", "status": "ERROR"}
            else:
                doors_status[door_name] = {"status": "EMPTY", "user_id": None}
                stats['empty'] += 1

        return render_template('doors.html',
                             doors=doors_status,
                             total_doors=len(doors),
                             stats=stats,
                             error=None)

    except Exception as e:
        return render_template('doors.html',
                             doors={},
                             total_doors=len(doors),
                             stats={'empty': 0, 'used': 0},
                             error=f"Failed to get doors status: {str(e)}")


@app.route('/api/doors')
def get_doors_api():
    """Get doors status as JSON API"""
    try:
        data_door = redis.hgetall("data_door")

        doors_status = {}
        for door_name in doors:
            if door_name in data_door:
                try:
                    door_data = json.loads(data_door[door_name])
                    doors_status[door_name] = door_data
                except json.JSONDecodeError:
                    doors_status[door_name] = {"error": "Invalid JSON data"}
            else:
                doors_status[door_name] = {"status": "EMPTY", "user_id": None}

        return {
            'success': True,
            'doors': doors_status,
            'total_doors': len(doors)
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to get doors status: {str(e)}"
        }, 500


@app.route('/redis/health')
def check_redis_connection():
    """Check Redis connection health"""
    try:
        # Test basic Redis connection with a simple ping
        redis.ping()

        # Get some basic info from Redis client
        info = redis.client.info()
        db_size = redis.client.dbsize()

        # Get connection info from RedisService attributes
        connection_kwargs = redis.client.connection_pool.connection_kwargs

        return {
            'success': True,
            'status': 'connected',
            'redis_version': info.get('redis_version', 'unknown'),
            'connected_clients': info.get('connected_clients', 0),
            'db_size': db_size,
            'used_memory': info.get('used_memory_human', 'unknown'),
            'host': connection_kwargs.get('host', 'unknown'),
            'port': connection_kwargs.get('port', 'unknown'),
            'db': connection_kwargs.get('db', 'unknown')
        }

    except Exception as e:
        # Get connection info even when disconnected
        try:
            connection_kwargs = redis.client.connection_pool.connection_kwargs
            host = connection_kwargs.get('host', 'unknown')
            port = connection_kwargs.get('port', 'unknown')
            db = connection_kwargs.get('db', 'unknown')
        except:
            host = port = db = 'unknown'

        return {
            'success': False,
            'status': 'disconnected',
            'error': str(e),
            'host': host,
            'port': port,
            'db': db
        }, 500


if __name__ == "__main__":
    load_face_data_from_redis()
    # Subscribe to topics
    mqtt_service.subscribe(SERVER_DOOR_STATUS, door_status_handler)
    mqtt_service.subscribe(SERVER_DOOR_EXECUTE, door_excute_handler)

    mqtt_service.connect()

    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
