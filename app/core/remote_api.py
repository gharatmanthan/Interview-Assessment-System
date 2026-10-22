"""Small client for the shared Render interview API."""
from typing import Any
from urllib.parse import urlsplit

import requests
import websocket


class RemoteApiClient:
    def __init__(self, base_url: str, timeout: float = 30):
        self.base_url = self._normalize_base_url(base_url)
        self.timeout = timeout
        self.access_token = None
        self._video_socket = None

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        value = base_url.strip().rstrip("/")
        if value.startswith("https:/") and not value.startswith("https://"):
            value = "https://" + value[len("https:/"):].lstrip("/")
        elif value.startswith("http:/") and not value.startswith("http://"):
            value = "http://" + value[len("http:/"):].lstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "Remote API URL must look like "
                "https://your-service.onrender.com/api/v1"
            )
        return value

    def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        if headers:
            kwargs["headers"] = headers
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else None

    def _login(self, role: str, identity: str, password: str) -> dict | None:
        response = requests.post(
            f"{self.base_url}/auth/{role}",
            json={"identity": identity, "password": password},
            timeout=self.timeout,
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        account = response.json()
        self.access_token = account["access_token"]
        return account

    def _binary_request(self, method: str, path: str, **kwargs) -> bytes:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout,
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()
        return response.content

    def authenticate_interviewer(self, interviewer_id: str, password: str) -> dict | None:
        return self._login("interviewer", interviewer_id, password)

    def list_live_interviews(self) -> list[dict]:
        return self._request("GET", "/interviews")

    def get_live_interview(self, session_id: str) -> dict | None:
        try:
            return self._request("GET", f"/interviews/{session_id}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def start_live_interview(
        self, session_id: str, candidate_id: str, candidate_name: str,
        question: str, question_index: int = 0,
    ) -> dict:
        return self._request(
            "POST",
            "/interviews",
            json={
                "session_id": session_id,
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "question": question,
                "question_index": question_index,
            },
        )

    def update_live_interview(self, session_id: str, **fields) -> dict:
        return self._request("PATCH", f"/interviews/{session_id}", json=fields)

    def upload_frame(self, session_id: str, frame: bytes) -> None:
        self._binary_request(
            "PUT",
            f"/interviews/{session_id}/frame",
            data=frame,
            headers={"Content-Type": "image/jpeg"},
        )

    def send_video_frame(self, session_id: str, frame: bytes) -> None:
        if self._video_socket is None:
            url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
            self._video_socket = websocket.create_connection(
                f"{url}/interviews/{session_id}/video?token={self.access_token}",
                timeout=15,
            )
        try:
            self._video_socket.send(frame, opcode=websocket.ABNF.OPCODE_BINARY)
        except (websocket.WebSocketException, OSError):
            self._video_socket.close()
            self._video_socket = None

    def receive_video_frames(self, session_id: str):
        url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        socket = websocket.create_connection(
            f"{url}/interviews/{session_id}/video?token={self.access_token}",
            timeout=30,
        )
        try:
            while True:
                frame = socket.recv()
                if isinstance(frame, bytes):
                    yield frame
        finally:
            socket.close()

    def close_video(self) -> None:
        if self._video_socket is not None:
            self._video_socket.close()
            self._video_socket = None

    def download_frame(self, session_id: str) -> bytes | None:
        try:
            return self._binary_request("GET", f"/interviews/{session_id}/frame")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def save_integrity_flag(
        self, session_id: str, flag_type: str, detail: str,
        severity: str, confidence: float, timestamp: str,
    ) -> dict:
        return self._request(
            "POST",
            f"/interviews/{session_id}/integrity-flags",
            json={
                "flag_type": flag_type,
                "detail": detail,
                "severity": severity,
                "confidence": confidence,
                "timestamp": timestamp,
            },
        )

    def get_session_flags(self, session_id: str) -> list[dict]:
        return self._request("GET", f"/interviews/{session_id}/integrity-flags")

    def review_integrity_flag(
        self, session_id: str, flag_id: int, review_status: str, review_note: str = ""
    ) -> dict:
        return self._request(
            "PATCH",
            f"/interviews/{session_id}/integrity-flags/{flag_id}",
            json={"status": review_status, "note": review_note},
        )

    def approve_pending_question(
        self, session_id: str, question: str | None = None,
    ) -> dict:
        payload = {"question": question} if question else {}
        return self._request(
            "POST",
            f"/interviews/{session_id}/approve-question",
            json=payload,
        )

    def authenticate_candidate(self, candidate_id: str, password: str) -> dict | None:
        return self._login("candidate", candidate_id, password)

    def get_candidate_accounts(self) -> list[dict]:
        return self._request("GET", "/candidates")

    def create_candidate_account(
        self, candidate_id: str, password: str, full_name: str
    ) -> bool:
        try:
            self._request(
                "POST",
                "/candidates",
                json={
                    "candidate_id": candidate_id,
                    "password": password,
                    "full_name": full_name,
                },
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                return False
            raise
        return True

    def get_active_job_postings(self) -> list[dict]:
        return self._request("GET", "/jobs")

    def save_job_posting(self, title: str, description: str) -> bool:
        self._request("POST", "/jobs", json={"title": title, "description": description})
        return True
