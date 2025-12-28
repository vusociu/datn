"""
FaceNet Service - Use FaceNet for face recognition
Replacement for face_recognition library
"""
import cv2
import numpy as np
from mtcnn import MTCNN
from keras_facenet import FaceNet
import os

class FaceNetService:
    def __init__(self):
        """Initialize FaceNet service"""
        print("Initializing FaceNet service...")
        
        # Initialize MTCNN for face detection
        self.detector = MTCNN()
        
        # Initialize FaceNet model for face encoding
        # FaceNet will automatically load model on initialization
        self.embedder = FaceNet()
        
        # Threshold for face comparison (cosine distance)
        # With FaceNet, distance is usually < 1.0 for the same person
        # Threshold 0.6-0.7 usually works well
        self.threshold = 0.6
        
        print("FaceNet service is ready!")
    
    def detect_faces(self, frame):
        """
        Detect faces in frame
        
        Args:
            frame: BGR frame from OpenCV
            
        Returns:
            List of face locations in format [(top, right, bottom, left), ...]
        """
        # MTCNN needs RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Detect faces
        detections = self.detector.detect_faces(rgb_frame)
        
        face_locations = []
        for detection in detections:
            x, y, width, height = detection['box']
            # Convert from (x, y, width, height) to (top, right, bottom, left)
            top = y
            right = x + width
            bottom = y + height
            left = x
            face_locations.append((top, right, bottom, left))
        
        return face_locations
    
    def get_face_encoding(self, frame, face_location):
        """
        Get encoding of a face
        
        Args:
            frame: BGR frame from OpenCV
            face_location: Tuple (top, right, bottom, left)
            
        Returns:
            Numpy array encoding of face or None if error
        """
        try:
            top, right, bottom, left = face_location
            
            # Ensure valid coordinates
            top = max(0, top)
            left = max(0, left)
            bottom = min(frame.shape[0], bottom)
            right = min(frame.shape[1], right)
            
            # Crop face
            face_image = frame[top:bottom, left:right]
            
            if face_image.size == 0 or face_image.shape[0] < 10 or face_image.shape[1] < 10:
                return None
            
            # Resize to 160x160 (size required by FaceNet)
            face_image_resized = cv2.resize(face_image, (160, 160))
            
            # Convert to RGB (FaceNet needs RGB)
            face_image_rgb = cv2.cvtColor(face_image_resized, cv2.COLOR_BGR2RGB)
            
            # FaceNet model in keras-facenet automatically handles normalization
            # Just ensure data type is uint8
            face_image_rgb = face_image_rgb.astype('uint8')
            
            # Add batch dimension: shape (1, 160, 160, 3)
            face_image_batch = np.expand_dims(face_image_rgb, axis=0)
            
            # Get embedding - keras-facenet returns numpy array
            embedding = self.embedder.embeddings(face_image_batch)
            
            # embedding can be list or array, get first element
            if isinstance(embedding, list):
                embedding = embedding[0]
            elif embedding.ndim > 1:
                embedding = embedding[0]
            
            return embedding
            
        except Exception as e:
            print(f"Error getting encoding: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def compare_faces(self, known_encodings, face_encoding, tolerance=None):
        """
        Compare a face with a list of known faces
        
        Args:
            known_encodings: List of known encodings
            face_encoding: Encoding of face to compare
            tolerance: Threshold to determine match (default uses self.threshold)
            
        Returns:
            List of booleans indicating which faces match
        """
        if tolerance is None:
            tolerance = self.threshold
        
        if len(known_encodings) == 0:
            return []
        
        matches = []
        for known_encoding in known_encodings:
            # Calculate cosine distance
            distance = self.face_distance([known_encoding], face_encoding)[0]
            # If distance is less than threshold then it's a match
            matches.append(distance <= tolerance)
        
        return matches
    
    def face_distance(self, face_encodings, face_to_compare):
        """
        Calculate distance between a face and a list of faces
        
        Args:
            face_encodings: List of encodings
            face_to_compare: Encoding to compare
            
        Returns:
            List of distances (cosine distance)
        """
        if len(face_encodings) == 0:
            return []
        
        distances = []
        for encoding in face_encodings:
            # Calculate cosine distance
            # Cosine distance = 1 - cosine similarity
            dot_product = np.dot(encoding, face_to_compare)
            norm_a = np.linalg.norm(encoding)
            norm_b = np.linalg.norm(face_to_compare)
            
            if norm_a == 0 or norm_b == 0:
                distance = 1.0  # If one of the vectors is 0
            else:
                cosine_similarity = dot_product / (norm_a * norm_b)
                # Cosine distance: 0 = completely identical, 1 = completely different
                distance = 1 - cosine_similarity
            
            distances.append(distance)
        
        return distances

