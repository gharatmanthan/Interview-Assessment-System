"""Small client for the shared Render interview API."""
from typing import Any

import requests


class RemoteApiClient:
    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs) -> Any:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else None

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
        self._request(
            "PUT",
            f"/interviews/{session_id}/frame",
            json={"image": frame.hex()},
        )

    def download_frame(self, session_id: str) -> bytes | None:
        response = requests.get(
            f"{self.base_url}/interviews/{session_id}/frame",
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

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
        response = requests.post(
            f"{self.base_url}/candidates/auth",
            json={"candidate_id": candidate_id, "password": password},
            timeout=self.timeout,
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        return response.json()

    def get_candidate_accounts(self) -> list[dict]:
        return self._request("GET", "/candidates")

    def create_candidate_account(
        self, candidate_id: str, password: str, full_name: str
    ) -> bool:
        response = requests.post(
            f"{self.base_url}/candidates",
            json={
                "candidate_id": candidate_id,
                "password": password,
                "full_name": full_name,
            },
            timeout=self.timeout,
        )
        if response.status_code == 409:
            return False
        response.raise_for_status()
        return True

    def get_active_job_postings(self) -> list[dict]:
        return self._request("GET", "/jobs")

    def save_job_posting(self, title: str, description: str) -> bool:
        self._request("POST", "/jobs", json={"title": title, "description": description})
        return True
