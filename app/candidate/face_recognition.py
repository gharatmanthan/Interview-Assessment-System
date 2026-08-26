"""Consent-based local camera checks used before an interview starts."""
from pathlib import Path

import cv2


CASCADE_PATH = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
FACE_DETECTOR = cv2.CascadeClassifier(str(CASCADE_PATH))
PROFILE_DIR = Path(__file__).parent.parent.parent / "data" / "face_profiles"


def detect_faces(frame):
    """Return face rectangles detected in a BGR camera frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return FACE_DETECTOR.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
    )


def _profile_path(candidate_id):
    safe_candidate_id = "".join(
        character for character in candidate_id if character.isalnum() or character in "-_"
    )
    return PROFILE_DIR / f"{safe_candidate_id}_v2.jpg"


def _face_crop(frame, face):
    x, y, width, height = face
    padding_x = int(width * 0.2)
    padding_y = int(height * 0.2)
    frame_height, frame_width = frame.shape[:2]
    left = max(0, x - padding_x)
    top = max(0, y - padding_y)
    right = min(frame_width, x + width + padding_x)
    bottom = min(frame_height, y + height + padding_y)
    crop = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    crop = cv2.resize(crop, (160, 160), interpolation=cv2.INTER_AREA)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(crop)


def enroll_face(candidate_id, frame):
    """Save the single detected face as the candidate's local enrollment image."""
    faces = detect_faces(frame)
    if len(faces) != 1 or not candidate_id:
        return False
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = _profile_path(candidate_id)
    saved = cv2.imwrite(str(profile_path), _face_crop(frame, faces[0]))
    return bool(saved and profile_path.is_file())


def has_enrolled_face(candidate_id):
    return bool(candidate_id) and _profile_path(candidate_id).is_file()


def verify_enrolled_face(candidate_id, frame):
    """Check that the one visible face resembles the enrolled candidate."""
    faces = detect_faces(frame)
    if len(faces) != 1:
        return False, "Show exactly one face in the camera."
    profile_path = _profile_path(candidate_id) if candidate_id else None
    if profile_path is None or not profile_path.is_file():
        return False, "Complete the face scan on the candidate dashboard first."

    enrolled = cv2.imread(str(profile_path), cv2.IMREAD_GRAYSCALE)
    if enrolled is None:
        return False, "The saved face profile could not be read. Scan again."
    current = _face_crop(frame, faces[0])
    correlation = float(cv2.matchTemplate(
        enrolled, current, cv2.TM_CCOEFF_NORMED
    )[0, 0])
    difference = cv2.norm(enrolled, current, cv2.NORM_L1) / (160 * 160 * 255)
    if (correlation == correlation and correlation >= 0.35
            and difference <= 0.45):
        return True, "Candidate face verified."
    return False, "This face does not match the enrolled candidate."


def verify_single_face(frame):
    """Verify that the camera currently shows exactly one visible face."""
    faces = detect_faces(frame)
    if len(faces) == 1:
        return True, "Face detected. Identity is not recorded or stored."
    if not len(faces):
        return False, "No face detected. Center your face in the camera."
    return False, "Multiple faces detected. Only the candidate should be visible."