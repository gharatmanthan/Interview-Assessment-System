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
from app.core.models import IntegrityFlag

REMOTE_ACCESS_PORTS = {
    3389: "RDP",
    5900: "VNC",
    5938: "TeamViewer",
    7070: "AnyDesk",
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
    """TODO: use psutil to check for teamviewer.exe, anydesk.exe, vncserver, etc.
    (add psutil to requirements.txt when you start this)
    """
    raise NotImplementedError


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
            )
        )
    # TODO: append process_scan() results and CV-based flags here too
    return flags
