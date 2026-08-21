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
    return PROFILE_DIR / f"{safe_candidate_id}.jpg"


def _face_crop(frame, face):
    x, y, width, height = face
    crop = cv2.cvtColor(frame[y:y + height, x:x + width], cv2.COLOR_BGR2GRAY)
    return cv2.resize(crop, (160, 160), interpolation=cv2.INTER_AREA)


def enroll_face(candidate_id, frame):
    """Save the single detected face as the candidate's local enrollment image."""
    faces = detect_faces(frame)
    if len(faces) != 1 or not candidate_id:
        return False
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(_profile_path(candidate_id)), _face_crop(frame, faces[0])))


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
    correlation = cv2.compareHist(
        cv2.calcHist([enrolled], [0], None, [64], [0, 256]),
        cv2.calcHist([current], [0], None, [64], [0, 256]),
        cv2.HISTCMP_CORREL,
    )
    difference = cv2.norm(enrolled, current, cv2.NORM_L1) / (160 * 160 * 255)
    if correlation >= 0.55 and difference <= 0.24:
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