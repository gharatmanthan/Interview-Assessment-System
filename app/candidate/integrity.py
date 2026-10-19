"""
Owner: Member A
Touches: this file only

Runs locally on the candidate's machine during the interview (this is a
native desktop app, so no browser-sandbox limitation — direct socket
and process checks are fine here, unlike a web-based client).

TODO (Member A):
- port_scan(): check localhost for known remote-access ports
- process_scan(): check running processes for remote-access tools
- run_checks(): combine both + any CV-based checks (gaze, extra person,
  phone detection via mediapipe/OpenCV) into a list of IntegrityFlag
"""
import socket
import psutil
from time import monotonic

from app.core.models import IntegrityFlag
from app.candidate.face_recognition import face_match_confidence, detect_faces
from app.utils.port_scanner import scan_external_devices

REMOTE_ACCESS_PORTS = {
    3389: "RDP",
    5900: "VNC",
    5938: "TeamViewer",
    7070: "AnyDesk",
}
SUSPICIOUS_PROCESSES = {
    "teamviewer": "TeamViewer",
    "anydesk": "AnyDesk",
    "vnc": "VNC",
    "rustdesk": "RustDesk",
    "parsec": "Parsec",
}


def port_scan(timeout=0.3) -> list:
    """Returns list of (port, tool_name) for anything listening locally."""
    found = []
    for port, name in REMOTE_ACCESS_PORTS.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if result == 0:
            found.append((port, name))
    return found


def process_scan() -> list:
    """Return known remote-access processes currently running."""
    found = []
    for process in psutil.process_iter(["name"]):
        try:
            name = (process.info.get("name") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for marker, tool in SUSPICIOUS_PROCESSES.items():
            if marker in name:
                found.append((name, tool))
                break
    return found


class FaceIntegrityMonitor:
    """Debounces camera signals so transient detection noise is not an event."""

    def __init__(self, required_seconds: float = 2.0, cooldown_seconds: float = 8.0):
        self.required_seconds = required_seconds
        self.cooldown_seconds = cooldown_seconds
        self._started: dict[tuple[str, str], float] = {}
        self._last_emitted: dict[tuple[str, str], float] = {}

    def observe(self, session_id: str, candidate_id: str, frame) -> list[IntegrityFlag]:
        face_count, matched, confidence, message = face_match_confidence(candidate_id, frame)
        signal = None
        severity = "medium"
        detail = message
        if face_count == 0:
            signal = "no_face"
            detail = "No face visible in the camera frame."
        elif face_count > 1:
            signal = "extra_person"
            severity = "high"
            detail = f"{face_count} faces visible in the camera frame."
        elif not matched:
            signal = "face_mismatch"
            severity = "high"
            detail = "Visible face did not match the enrolled candidate."

        now = monotonic()
        if signal is None:
            self._started.clear()
            return []
        key = (session_id, signal)
        self._started.setdefault(key, now)
        if now - self._started[key] < self.required_seconds:
            return []
        if now - self._last_emitted.get(key, 0) < self.cooldown_seconds:
            return []
        self._last_emitted[key] = now
        return [IntegrityFlag(
            session_id=session_id,
            flag_type=signal,
            detail=detail,
            severity=severity,
            confidence=confidence,
        )]


class EnvironmentIntegrityMonitor:
    """Rate-limits host checks while allowing newly connected devices to surface."""

    def __init__(self, cooldown_seconds: float = 30.0):
        self.cooldown_seconds = cooldown_seconds
        self._last_emitted: dict[tuple[str, str, str], float] = {}

    def observe(self, session_id: str) -> list[IntegrityFlag]:
        now = monotonic()
        emitted = []
        for flag in run_checks(session_id):
            key = (flag.flag_type, flag.detail, flag.severity)
            if now - self._last_emitted.get(key, 0) < self.cooldown_seconds:
                continue
            self._last_emitted[key] = now
            emitted.append(flag)
        return emitted


def frame_checks(session_id: str, frame, candidate_id: str = "") -> list:
    """Backward-compatible one-frame checks for callers outside the live UI."""
    face_count, matched, confidence, message = face_match_confidence(candidate_id, frame)
    if face_count == 0:
        return [IntegrityFlag(session_id, "no_face", message, "medium", confidence)]
    if face_count > 1:
        return [IntegrityFlag(session_id, "extra_person", message, "high", confidence)]
    if candidate_id and not matched:
        return [IntegrityFlag(session_id, "face_mismatch", message, "high", confidence)]
    return []


def run_checks(session_id: str) -> list:
    """Combine all integrity signals into IntegrityFlag objects.
    Must return: list[IntegrityFlag] — this is what app/core/db.save_integrity_flag()
    and the Integrity Log page (Member C) expect.
    """
    flags = []
    for port, tool in port_scan():
        flags.append(
            IntegrityFlag(
                session_id=session_id,
                flag_type="remote_access_port",
                detail=f"{tool} port {port} is open",
                severity="high",
                confidence=0.95,
            )
        )
    for process_name, tool in process_scan():
        flags.append(
            IntegrityFlag(
                session_id=session_id,
                flag_type="remote_access_process",
                detail=f"{tool} process detected ({process_name})",
                severity="high",
                confidence=0.9,
            )
        )
    for device in scan_external_devices():
        flags.append(
            IntegrityFlag(
                session_id=session_id,
                flag_type=device.kind,
                detail=device.detail,
                severity=device.severity,
                confidence=device.confidence,
            )
        )
    return flags
