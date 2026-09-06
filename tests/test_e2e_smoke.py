"""End-to-end smoke: public apply -> async screening -> candidate+invite+outbox
-> invite validation -> interview start/answer/complete -> recruiter views.

Drives the exact production code paths (no route mocks, no db mocks); Gmail is
the only thing stubbed, because the outbox worker sends through the real Gmail
client when one is connected.
"""
import io
from unittest.mock import MagicMock, patch

from app.core import db
from app.screening.service import run_screening_jobs

GOOD_RESUME = (
    "Backend engineer with python, sql, rest api and system design experience. "
    "5 years of experience. B.Tech in Computer Science."
)


def _create_job(client):
    client.post("/api/jobs", json={
        "job_id": "job-e2e",
        "title": "Backend Engineer",
        "description": "We need python and sql skills.",
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": 50.0,
        "minimum_experience_years": 3,
    })


def _apply(client, name="Jane E2E", email="jane.e2e@example.com"):
    return client.post(
        "/api/public/apply/job-e2e",
        data={"name": name, "email": email},
        files={"resume": ("resume.txt", io.BytesIO(GOOD_RESUME.encode()), "text/plain")},
    )


class TestEndToEndSmoke:
    def test_apply_to_completed_interview(self, client, public_client):
        _create_job(client)

        # 1. Public apply -> 202 + application id (no auth).
        resp = _apply(public_client)
        assert resp.status_code == 202
        application_id = resp.json()["application_id"]
        assert application_id

        # 2. Screening runs in the background worker -> application completes.
        run_screening_jobs()

        apps = client.get("/api/applications").json()["applications"]
        assert len(apps) == 1
        assert apps[0]["application_id"] == application_id
        assert apps[0]["screening_status"] == "completed"
        assert apps[0]["candidate_id"]

        # 2b. The recruiting side confirms the interview-mode strategy, which is
        # the gate that releases the candidate invite (Mode 1, within capacity).
        from app.screening.routing import finalize_cohort_if_ready
        status = finalize_cohort_if_ready("job-e2e")
        assert status["cohort_finalized"] is True
        from app.screening.routing import confirm_strategy
        confirm_strategy("job-e2e", "AUTO")

        # 3. Candidate created with a consumable invite; invite queued in outbox.
        candidates = db.get_all_candidates()
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand["status"] == "invited"
        assert cand["invite_code"]
        assert cand["interview_mode"] == "MODE_1"

        pending = db.get_pending_notifications()
        assert any(n["notification_type"] == "mode1_invite" for n in pending)
        assert all(n["status"] == "pending" for n in pending)

        # 4. Outbox drains via Gmail (stubbed send).
        service = MagicMock()
        service.users().messages().send().execute.return_value = {"id": "gmail-1"}
        with patch("app.screening.email_worker.get_gmail_service", return_value=service):
            from app.screening.email_worker import send_pending_notifications
            sent_ids = send_pending_notifications()
        assert pending and sent_ids
        assert db.get_pending_notifications() == []

        # Candidate is marked as invite-emailed.
        assert db.get_candidate(cand["candidate_id"])["invite_email_sent"] is True

        # 5. Candidate validates the invite, gives consent, starts the session.
        v = public_client.post("/api/candidate/validate-code", json={"invite_code": cand["invite_code"]})
        assert v.json()["valid"] is True
        token = v.json()["interview_token"]

        consent = public_client.post("/api/candidate/consent", json={
            "interview_token": token,
        })
        assert consent.json()["success"] is True
        session_id = consent.json()["session_id"]

        start = public_client.post("/api/candidate/start-session", json={
            "interview_token": token,
        })
        assert start.status_code == 200
        assert start.json()["session_id"] == session_id
        assert db.get_interview_invites_for_candidate(cand["candidate_id"])[0]["status"] == "consumed"

        # 6. Answer is scored (heuristic fallback, no LLM key required).
        answer = public_client.post("/api/candidate/submit-answer", json={
            "session_id": session_id,
            "question_id": "q-e2e",
            "category": "algorithms",
            "transcript": "I would use a hash map for O(1) lookups and a sliding window over the array.",
            "interview_token": token,
        })
        assert answer.status_code == 200
        assert isinstance(answer.json()["score"]["score"], float)

        # 7. Session completes.
        done = public_client.post("/api/candidate/complete-session", json={
            "session_id": session_id, "interview_token": token,
        })
        assert done.json()["success"] is True
        assert db.get_session(session_id)["status"] == "completed"

        # 8. Recruiter sees the completed application with a screening result.
        detail = client.get(f"/api/applications/{application_id}").json()
        assert detail["status"] == "completed" or detail["screening_status"] == "completed"
        assert detail["screening_result"]
        assert detail["screening_result"]["decision"] in ("passed", "manual_review")

        # Candidate status reflects completion.
        assert db.get_candidate(cand["candidate_id"])["status"] == "completed"

    def test_duplicate_email_rejected_even_across_screens(self, client, public_client):
        _create_job(client)
        assert _apply(public_client).status_code == 202
        dup = _apply(public_client)
        assert dup.status_code == 409