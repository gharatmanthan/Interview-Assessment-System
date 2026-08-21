"""Unit tests for app/candidate/face_recognition.py.

Uses blank synthetic frames so no real camera or face image is needed —
these cover the decision logic (gate conditions and messages), not the
Haar detector's accuracy.
"""
import numpy as np
import pytest

from app.candidate import face_recognition


@pytest.fixture(autouse=True)
def isolated_profile_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(face_recognition, "PROFILE_DIR", tmp_path / "face_profiles")


def blank_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_enroll_requires_exactly_one_face():
    assert face_recognition.enroll_face("cand-1", blank_frame()) is False


def test_enroll_rejects_empty_candidate_id():
    frame = blank_frame()
    assert face_recognition.enroll_face("", frame) is False


def test_has_enrolled_face_false_for_unknown_or_empty():
    assert face_recognition.has_enrolled_face("nobody-here") is False
    assert face_recognition.has_enrolled_face("") is False


def test_profile_path_sanitizes_candidate_id(tmp_path):
    path = face_recognition._profile_path("../../evil id!")
    assert path.parent == face_recognition.PROFILE_DIR
    assert path.name == "evilid.jpg"


def test_verify_single_face_no_face_message():
    ok, message = face_recognition.verify_single_face(blank_frame())
    assert ok is False
    assert "No face detected" in message


def test_verify_enrolled_face_without_profile():
    ok, message = face_recognition.verify_enrolled_face("cand-1", blank_frame())
    assert ok is False
    # A blank frame has no detectable face, so the single-face gate fires first
    assert "face" in message.lower()


def test_verify_enrolled_face_missing_profile_message(monkeypatch):
    monkeypatch.setattr(
        face_recognition, "detect_faces", lambda frame: np.array([[10, 10, 80, 80]])
    )
    ok, message = face_recognition.verify_enrolled_face("cand-1", blank_frame())
    assert ok is False
    assert "face scan" in message.lower()


def test_verify_single_face_multiple_faces_message(monkeypatch):
    two_faces = np.array([[10, 10, 80, 80], [200, 10, 80, 80]])
    monkeypatch.setattr(face_recognition, "detect_faces", lambda frame: two_faces)
    ok, message = face_recognition.verify_single_face(blank_frame())
    assert ok is False
    assert "Multiple faces" in message


def test_verify_single_face_one_face_passes(monkeypatch):
    one_face = np.array([[10, 10, 80, 80]])
    monkeypatch.setattr(face_recognition, "detect_faces", lambda frame: one_face)
    ok, message = face_recognition.verify_single_face(blank_frame())
    assert ok is True
