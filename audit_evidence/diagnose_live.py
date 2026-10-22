"""Read-only diagnostic for InterviewIQ remote live monitoring.

Run on the machine that shows the empty "Live Interview Monitor":

    .venv\\Scripts\\python.exe audit_evidence\\diagnose_live.py

It prints:
  1. the local backend mode / remote URL (no secrets),
  2. whether the Render interviewer login succeeds,
  3. whether /interviews returns live sessions,
  4. whether /candidates returns registered candidates,
  5. whether a camera frame exists for the live session.

Credentials are prompted for and never stored or printed.
"""

from __future__ import annotations

import getpass
import json
import pathlib
import sys

import requests

DEFAULT_BASE = "https://interviewiq-api-736y.onrender.com/api/v1"
TIMEOUT = 90  # Render free tier can cold-start for ~60 s


def show_local_settings() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    path = root / "data" / "settings.json"
    print("=" * 66)
    print("LOCAL DESKTOP SETTINGS")
    print("=" * 66)
    print(f"file        : {path}")
    if not path.exists():
        print("exists      : NO  (defaults to backend_mode='local')")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"unreadable  : {exc}")
        return
    print(f"backend_mode: {data.get('backend_mode')!r}")
    print(f"remote_url  : {data.get('remote_api_url')!r}")
    print(f"camera_index: {data.get('camera_index')!r}")
    print(
        "\nIf backend_mode is 'local', this app never contacts Render.\n"
        "On the interviewer machine it must be 'remote' with the /api/v1 URL.\n"
    )


def request_json(session: requests.Session, method: str, url: str, **kwargs):
    try:
        response = session.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        print(f"  ERROR: could not reach {url}\n         {exc}")
        return None
    try:
        body = response.json()
    except ValueError:
        body = response.text[:300]
    return response, body


def main() -> int:
    show_local_settings()

    if "--settings-only" in sys.argv:
        return 0

    print("=" * 66)
    print("RENDER SERVICE")
    print("=" * 66)
    base = input(f"Base URL [{DEFAULT_BASE}]: ").strip() or DEFAULT_BASE
    base = base.rstrip("/")
    if not base.endswith("/api/v1"):
        print("WARNING: the URL should end with /api/v1")
    print(f"using: {base}\n")

    session = requests.Session()

    ready = request_json(session, "GET", base.replace("/api/v1", "") + "/health/ready")
    if ready:
        response, body = ready
        print(f"/health/ready -> HTTP {response.status_code} {body}")

    identity = input("Render interviewer ID: ").strip()
    password = getpass.getpass("Render interviewer password: ")

    print("\n[1] POST /auth/interviewer")
    result = request_json(
        session, "POST", f"{base}/auth/interviewer",
        json={"identity": identity, "password": password},
    )
    if result is None:
        return 2
    response, body = result
    print(f"    HTTP {response.status_code}")
    if response.status_code != 200:
        print(f"    body: {body}")
        print(
            "\n    LOGIN FAILED. The Render interviewer account does not accept\n"
            "    these credentials. It is seeded on the server from the Render\n"
            "    environment variables INTERVIEWER_ID / INTERVIEWER_PASSWORD.\n"
            "    Note: after the first deploy, changing those variables does NOT\n"
            "    update the stored password (ON CONFLICT DO NOTHING)."
        )
        return 3

    token = body.get("access_token")
    if not token:
        print("    no access_token in response")
        return 4
    print(f"    token received (length {len(token)}), expires at "
          f"{body.get('expires_at', 'unknown')}")
    headers = {"Authorization": f"Bearer {token}"}

    print("\n[2] GET /interviews  (live sessions)")
    result = request_json(session, "GET", f"{base}/interviews", headers=headers)
    if result is None:
        return 5
    response, body = result
    print(f"    HTTP {response.status_code}")
    if response.status_code != 200:
        print(f"    body: {body}")
        return 6
    interviews = body
    print(f"    live sessions: {len(interviews)}")
    for item in interviews:
        print(
            f"      - {item.get('candidate_name')} | session={item.get('session_id')} "
            f"| status={item.get('status')} | updated={item.get('updated_at')}"
        )

    print("\n[3] GET /candidates  (registered candidates, shown as READY)")
    result = request_json(session, "GET", f"{base}/candidates", headers=headers)
    if result is None:
        return 7
    response, body = result
    print(f"    HTTP {response.status_code}")
    if response.status_code != 200:
        print(f"    body: {body}")
        return 8
    print(f"    candidates: {len(body)}")
    for item in body:
        print(f"      - {item.get('candidate_id')} | {item.get('full_name')}")

    live = [item for item in interviews if item.get("status") == "live"]

    print("\n[4] GET /interviews/{id}/frame  (camera frame)")
    if not live:
        print("    skipped: no live session right now")
        print(
            "\n    The candidate app is not currently live on Render.\n"
            "    Start an interview from a candidate app that is ALSO in\n"
            "    'Shared Render API' mode, then run this again."
        )
        return 0

    session_id = live[0]["session_id"]
    print(f"    checking session {session_id}")
    result = request_json(
        session, "GET", f"{base}/interviews/{session_id}/frame", headers=headers
    )
    if result is None:
        return 9
    response, body = result
    print(f"    HTTP {response.status_code}")
    print(f"    content-type: {response.headers.get('content-type')}")
    print(f"    bytes: {len(response.content)}")
    if response.status_code == 200 and response.content:
        print("    FRAME OK - the monitor should be able to show it.")
    elif response.status_code == 404:
        print(
            "\n    NO FRAME STORED. The candidate is live but no JPEG has been\n"
            "    saved. Either the candidate is not sending frames, or the\n"
            "    deployed backend is older than commit c105713 (which added\n"
            "    db.save_live_frame to the WebSocket path)."
        )
    else:
        print(f"    body: {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
