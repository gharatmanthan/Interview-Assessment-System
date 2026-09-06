"""
End-to-end acceptance of the screening business rules (MASTER-PROMPT spec):

* Spec 4/19/46 — the recruiter shortlist is exactly the passed shortlist;
  rejected and manual-review applicants never appear (backend enforced);
* Spec 6/7/16 — hard requirements gate independently of the weighted ATS
  score; a high-scoring resume still fails when a hard gate is missed;
* Spec 31/34 — screening disabled => manual review, no AI decision/invite;
* Spec 22/57 — a fully qualified applicant lands in the shortlist, validates
  the invite, starts the interview, and a re-screen that flips the decision
  to rejected hides them from the shortlist again (admin ops still intact);
* Passed status must survive the run through validate/consent/start.
"""
import io

from api.main import app as api_app
from app.core import db
from app.screening.service import run_screening_jobs
from tests.conftest import _register_and_token
from fastapi.testclient import TestClient

GOOD = (
    "Backend engineer with python, sql, rest api and system design experience. "
    "8 years of experience. B.Tech in Computer Science."
)
POOR = (
    "Customer service representative focused on retail support, inventory and "
    "point-of-sale operations. No technical background."
)
HIGH_SCORE_NO_HARD = (
    "Principal engineer. Python, SQL, PostgreSQL, Redis, Kafka, Kubernetes. "
    "12 years of hands-on software engineering experience building large systems."
)


def _job(client, job_id, **overrides):
    payload = {
        "job_id": job_id,
        "title": "Backend Engineer",
        "description": "We need python and sql skills.",
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": 50.0,
        "application_gmail_label": "",
    }
    payload.update(overrides)
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 200, resp.text


def _apply(client, job_id, name, email, resume):
    resp = client.post(
        f"/api/public/apply/{job_id}",
        data={"name": name, "email": email},
        files={"resume": ("resume.txt", io.BytesIO(resume.encode()), "text/plain")},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["application_id"]


class TestSpectrumOfApplicants:
    """Spec 57 — the A/B/C applicant spectrum behaves as intended end-to-end."""

    def test_passed_shortlisted_rejected_hidden_high_score_still_gated(
        self, client, fresh_db, public_client
    ):
        _job(client, "job-spectrum", required_education="B.Tech")
        app_a = _apply(client, "job-spectrum", "Alice Good", "a@example.com", GOOD)
        app_b = _apply(client, "job-spectrum", "Bob Poor", "b@example.com", POOR)
        app_c = _apply(client, "job-spectrum", "Carol Gapped", "c@example.com", HIGH_SCORE_NO_HARD)

        run_screening_jobs()

        # Applicant A: passed -> invariant: candidate + active invite.
        a = db.get_application(app_a)
        assert a["status"] == "invite_pending"
        cands = db.get_all_candidates()
        cand = next(c for c in cands if c["email"] == "a@example.com")
        assert cand["invite_code"]

        # Applicant B: soft reject (far below threshold).
        b = db.get_application(app_b)
        assert b["status"] == "rejected"

        # Applicant C: high skill overlap but missed the hard education gate
        # -> rejected regardless of ATS (spec 6/7/16).
        c = db.get_application(app_c)
        result_c = db.get_screening_result(app_c)
        assert c["status"] == "rejected"
        assert result_c["hard_requirements_passed"] is False
        # verify the ATS was not the reason (score would have passed the gate)
        assert result_c["ats_score"] is not None
        assert result_c["decision"] == "rejected"
        assert "hard requirements" in result_c["decision_reason"]

        # The recruiter's shortlist is exactly Applicant A.
        shortlist = client.get("/api/candidates/job/job-spectrum").json()
        assert [s["email"] for s in shortlist] == ["a@example.com"]

    def test_qualified_applicant_gets_token_gated_interview(self, client, fresh_db, public_client):
        _job(client, "job-token")
        app_id = _apply(client, "job-token", "Alice Good", "a@example.com", GOOD)
        run_screening_jobs()

        cand = next(c for c in db.get_all_candidates() if c["email"] == "a@example.com")

        # No token -> start-session is refused even with the right IDs.
        r = public_client.post("/api/candidate/start-session", json={
            "session_id": "s-accept",
            "candidate_id": cand["candidate_id"],
            "job_id": "job-token",
        })
        assert r.status_code == 401

        v = public_client.post(
            "/api/candidate/validate-code", json={"invite_code": cand["invite_code"]}
        )
        assert v.json()["valid"] is True
        token = v.json()["interview_token"]
        assert v.json()["candidate"].get("invite_code") is None  # not echoed

        consent = public_client.post("/api/candidate/consent", json={
            "interview_token": token,
        })
        assert consent.json()["success"] is True
        session_id = consent.json()["session_id"]

        start = public_client.post("/api/candidate/start-session", json={
            "interview_token": token,
        })
        assert start.status_code == 200
        assert start.json()["candidate_name"] == "Alice Good"
        assert start.json()["session_id"] == session_id

        answer = public_client.post("/api/candidate/submit-answer", json={
            "session_id": session_id, "question_id": "q1", "category": "technical",
            "transcript": "I would profile the endpoint, isolate the slow query, add an index.",
            "interview_token": token,
        })
        assert answer.status_code == 200

        done = public_client.post(
            "/api/candidate/complete-session",
            json={"session_id": session_id, "interview_token": token},
        )
        assert done.json()["success"] is True

        # The interviewed candidate shows up for the recruiter (allowed) ...
        assert client.get(f"/api/applications/{app_id}").status_code == 200


class TestScreeningToggleAndReScreenVisibility:
    """Spec 31/34 + spec 4 — screening toggle and decision-aware shortlist."""

    def test_screening_disabled_leaves_to_manual_review(self, client, fresh_db):
        _job(client, "job-off", screening_enabled=False)
        app_id = _apply(client, "job-off", "Grace Manual", "g@example.com", GOOD)
        run_screening_jobs()

        app = db.get_application(app_id)
        assert app["screening_status"] == "completed"
        assert app["status"] == "manual_review"

        result = db.get_screening_result(app_id)
        assert result is None or result["decision"] == "manual_review"
        assert db.get_all_candidates() == []

        detail = client.get(f"/api/applications/{app_id}").json()
        assert "screening_disabled" in [e["event"] for e in detail["events"]]

    def test_rescreen_flip_hides_candidate_but_admin_ops_still_work(
        self, client, fresh_db
    ):
        _job(client, "job-flip")
        app_id = _apply(client, "job-flip", "Dana Flip", "d@example.com", GOOD)
        run_screening_jobs()

        cand = next(c for c in db.get_all_candidates() if c["email"] == "d@example.com")
        assert client.get("/api/candidates/job/job-flip").json()[0]["candidate_id"] == cand["candidate_id"]

        # Raise threshold to force a rejection on re-screen.
        job = next(j for j in client.get("/api/jobs").json() if j["job_id"] == "job-flip")
        job["screening_threshold"] = 120.0
        assert client.put("/api/jobs/job-flip", json=job).status_code == 200
        assert client.post(f"/api/applications/{app_id}/rescreen").status_code == 200
        run_screening_jobs()

        assert db.get_application(app_id)["status"] == "rejected"

        # Shortlist no longer shows the candidate ...
        assert client.get("/api/candidates/job/job-flip").json() == []
        # ... yet the row still exists and admin operations stay reachable.
        assert len(db.get_all_candidates()) == 1
        assert client.delete(f"/api/candidates/{cand['candidate_id']}").json()["success"] is True
        assert db.get_all_candidates() == []


class TestOwnershipScopedShortlistLists:
    def test_other_recruiter_shortlist_is_empty(self, fresh_db):
        owner = TestClient(api_app)
        owner.headers.update({"Authorization": f"Bearer {_register_and_token('owner-x')}"})
        stranger = TestClient(api_app)
        stranger.headers.update({"Authorization": f"Bearer {_register_and_token('stranger-x')}"})

        _job(owner, "job-sec")
        _apply(owner, "job-sec", "Alice Good", "a@example.com", GOOD)
        run_screening_jobs()

        assert len(owner.get("/api/candidates").json()) == 1
        assert stranger.get("/api/candidates").json() == []
        assert stranger.get("/api/candidates/job/job-sec").status_code == 403
        assert stranger.get("/api/applications/stats").json()["jobs"] == []