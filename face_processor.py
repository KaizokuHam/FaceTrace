import os
import sys
import hashlib
import numpy as np
import cv2
import mediapipe as mp

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def compute_file_sha256(file_path: str) -> str:
    """Compute deterministic SHA-256 hash of original file bytes."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def serialize_embedding(embedding: np.ndarray) -> bytes:
    """
    Deterministically serialize a numeric embedding array.
    Ensures float32 data type and contiguous memory layout.
    """
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding, dtype=np.float32)
    contiguous = np.ascontiguousarray(embedding, dtype=np.float32)
    return contiguous.tobytes()


def compute_embedding_sha256(embedding: np.ndarray) -> tuple[bytes, str]:
    """Serialize embedding and compute its SHA-256 hash."""
    serialized = serialize_embedding(embedding)
    emb_sha256 = hashlib.sha256(serialized).hexdigest()
    return serialized, emb_sha256


def detect_faces(image_rgb: np.ndarray, min_confidence: float = 0.5) -> list:
    """
    Detect faces in an RGB image using MediaPipe FaceDetection.
    Returns list of detections.
    """
    mp_face_detection = mp.solutions.face_detection
    with mp_face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=min_confidence
    ) as detector:
        results = detector.process(image_rgb)
        return results.detections if results.detections else []


def extract_face_embedding(image_rgb: np.ndarray) -> np.ndarray:
    """
    Extract deterministic numeric face representation using canonical 3D facial landmarks.
    Features are centered around the facial centroid and L2-normalized to achieve scale & translation invariance.
    Output is a 1434-dimensional float32 vector (478 landmarks * 3 coordinates).
    """
    mp_face_mesh = mp.solutions.face_mesh
    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=2,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as mesh:
        results = mesh.process(image_rgb)
        if not results.multi_face_landmarks:
            raise ValueError("FaceMesh failed to extract landmarks from detected face.")
        if len(results.multi_face_landmarks) > 1:
            raise ValueError(f"FaceMesh detected multiple faces ({len(results.multi_face_landmarks)}). Exactly one is required.")

        landmarks = results.multi_face_landmarks[0].landmark
        coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float32)

        # Centroid-center to achieve translation invariance
        centroid = np.mean(coords, axis=0)
        centered = coords - centroid

        # L2-normalize to achieve scale invariance
        norm = np.linalg.norm(centered)
        if norm > 1e-6:
            normalized = centered / norm
        else:
            normalized = centered

        return normalized.flatten().astype(np.float32)


def process_face(image_path: str) -> dict:
    """
    Execute Phase 1 face processing on the given image path:
    1. Compute original image SHA-256 hash.
    2. Load image and detect faces.
    3. Validate face count (0 -> fail, >1 -> fail, 1 -> proceed).
    4. Generate deterministic face embedding and its SHA-256 hash.

    Note: The embedding represents numerical facial features suitable for comparison
    and representation, and does not constitute proof of real-world legal identity.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found: {image_path}")

    image_sha256 = compute_file_sha256(image_path)

    # Read image via OpenCV
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Failed to read image at: {image_path}")

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    detections = detect_faces(img_rgb)
    face_count = len(detections)

    if face_count == 0:
        return {
            "success": False,
            "error_code": "NO_FACES",
            "message": "Detected 0 faces in image.",
            "face_count": 0,
            "image_sha256": image_sha256,
            "embedding": None,
            "embedding_bytes": None,
            "embedding_sha256": None,
        }

    if face_count > 1:
        return {
            "success": False,
            "error_code": "MULTIPLE_FACES",
            "message": f"Multiple faces detected ({face_count} faces). Exactly one face is required.",
            "face_count": face_count,
            "image_sha256": image_sha256,
            "embedding": None,
            "embedding_bytes": None,
            "embedding_sha256": None,
        }

    # Exactly one face detected
    embedding = extract_face_embedding(img_rgb)
    emb_bytes, emb_sha256 = compute_embedding_sha256(embedding)

    return {
        "success": True,
        "error_code": None,
        "message": "Exactly one face detected and embedding successfully generated.",
        "face_count": 1,
        "image_sha256": image_sha256,
        "embedding": embedding,
        "embedding_dim": len(embedding),
        "embedding_bytes": emb_bytes,
        "embedding_sha256": emb_sha256,
    }
