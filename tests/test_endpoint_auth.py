"""Security: the interview-scoring, integrity, and device-management endpoints
must no longer be anonymous. Contract change from the read-only audit:
  * candidate sessions (submit-answer, complete-session, recording/live-frame
    upload, integrity-flag intake) require a valid interview token bound to the
    session's owner;
  * recruiter-only endpoints (scoring/run, devices, live-frame read, integrity
    websocket) require the recruiter Bearer token.
"""
import pytest

from app.core import db


def _sponsor_candidate(public_client, resolve_code=True):
    """Seed a candidate through the real public invite flow and return
    (candidate, interview_token).

    The candidate is pre-linked to a real, backed sessions row (as if the
    server had already created it), so start-session treats that id as the
    authoritative session and returns it unchanged."""
    from app.core.models import InterviewInvite, InterviewSession

    db.save_job_posting(_job())
    db.save_candidate(
        _cand("c-a", "Sess Owner", "owner@example.com", session_id="sess-owner")
    )
    db.save_session(InterviewSession(
        session_id="sess-owner", candidate_name="Sess Owner",
        job_title="Secure Engineer", job_id="job-sec",
        status="in_progress",
    ))
    invite = InterviewInvite(
        candidate_id="c-a", job_id="job-sec", application_id=None,
        token="sec-invite-xyz",
    )
    db.create_interview_invite(invite)
    if not resolve_code:
        return db.get_candidate("c-a"), None
    v = public_client.post("/api/candidate/validate-code", json={"invite_code": "code-c-a"})
    token = v.json()["interview_token"]
    # start the session so the candidate row is linked to it
    r = public_client.post("/api/candidate/start-session", json={
        "interview_token": token,
    })
    assert r.status_code == 200
    return db.get_candidate("c-a"), token


def _job():
    from app.core.models import JobPosting

    return JobPosting(
        job_id="job-sec", title="Secure Engineer", description="d",
        required_skills=["python"], experience_level="Junior", department="Eng",
        created_by="recruiter",
    )


def _cand(candidate_id, name, email, session_id=None):
    from app.core.models import Candidate

    return Candidate(
        candidate_id=candidate_id, job_id="job-sec", name=name, email=email,
        invite_code=f"code-{candidate_id}", status="invited",
        session_id=session_id,
    )


TRANSCRIPT = "I would use a hash map and then verify the edge cases."


class TestCandidateScoringEndpointsRequireInterviewToken:
    def test_submit_answer_requires_token(self, public_client):
        _sponsor_candidate(public_client)
        no_token = public_client.post("/api/candidate/submit-answer", json={
            "session_id": "sess-owner", "question_id": "q1",
            "category": "technical", "transcript": TRANSCRIPT,
        })
        assert no_token.status_code == 401

    def test_submit_answer_rejects_token_for_another_candidate_session(self, public_client, fresh_db):
        owner, token = _sponsor_candidate(public_client)
        # forge a session for a *different* candidate
        db.save_candidate(_cand("other", "Other", "other@example.com", session_id="sess-other"))
        resp = public_client.post("/api/candidate/submit-answer", json={
            "session_id": "sess-other", "question_id": "q1",
            "category": "technical", "transcript": TRANSCRIPT,
            "interview_token": token,
        })
        assert resp.status_code == 403

    def test_submit_answer_with_owner_token_succeeds(self, public_client):
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post("/api/candidate/submit-answer", json={
            "session_id": "sess-owner", "question_id": "q1",
            "category": "technical", "transcript": TRANSCRIPT,
            "interview_token": token,
        })
        assert resp.status_code == 200
        assert 0 <= resp.json()["score"]["score"] <= 100

    def test_complete_session_requires_token(self, public_client):
        _sponsor_candidate(public_client)
        resp = public_client.post("/api/candidate/complete-session", json={"session_id": "sess-owner"})
        assert resp.status_code == 401
        assert db.get_session("sess-owner")["status"] == "in_progress"

    def test_complete_session_with_owner_token_succeeds(self, public_client):
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post("/api/candidate/complete-session", json={
            "session_id": "sess-owner", "interview_token": token,
        })
        assert resp.json()["success"] is True
        assert db.get_session("sess-owner")["status"] == "completed"


class TestUploadsRequireInterviewToken:
    def test_upload_recording_requires_token(self, public_client):
        _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/sessions/sess-owner/upload",
            files={"video": ("v.webm", b"not-important", "video/webm")},
        )
        assert resp.status_code == 401

    def test_upload_recording_with_owner_token_succeeds(self, public_client):
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/sessions/sess-owner/upload",
            headers={"X-Interview-Token": token},
            files={"video": ("v.webm", b"real-video-bytes", "video/webm")},
        )
        assert resp.status_code == 200
        assert resp.json()["saved"]["video_path"].endswith("v.webm")

    def test_live_frame_upload_requires_token(self, public_client):
        _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/sessions/sess-owner/live-frame",
            content=b"\xff\xd8fake\xff\xd9",
            headers={"Content-Type": "image/jpeg"},
        )
        assert resp.status_code == 401

    def test_live_frame_upload_with_owner_token_succeeds(self, public_client, tmp_path, monkeypatch):
        import api.routes.sessions as sessions_route

        monkeypatch.setattr(sessions_route, "LIVE_FRAMES_DIR", tmp_path / "frames")
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/sessions/sess-owner/live-frame",
            content=b"\xff\xd8fake\xff\xd9",
            headers={"Content-Type": "image/jpeg", "X-Interview-Token": token},
        )
        assert resp.status_code == 200
        assert (tmp_path / "frames" / "sess-owner.jpg").exists()


class TestRecruiterOnlyEndpoints:
    def test_scoring_run_requires_recruiter(self, public_client):
        resp = public_client.post("/api/scoring/run", json={
            "session_id": "s1", "question_id": "q1",
            "category": "technical", "transcript": TRANSCRIPT,
        })
        assert resp.status_code == 401

    def test_scoring_run_with_recruiter_token_succeeds(self, client):
        resp = client.post("/api/scoring/run", json={
            "session_id": "s1", "question_id": "q1",
            "category": "technical", "transcript": TRANSCRIPT,
        })
        assert resp.status_code == 200

    def test_list_devices_requires_recruiter(self, public_client):
        assert public_client.get("/api/devices").status_code == 401

    def test_list_devices_with_recruiter_token_succeeds(self, client):
        assert client.get("/api/devices").status_code == 200

    def test_live_frame_read_requires_recruiter(self, public_client):
        assert public_client.get("/api/sessions/sess-owner/live-frame").status_code == 401

    def test_integrity_intake_requires_token(self, public_client):
        _sponsor_candidate(public_client)
        resp = public_client.post("/api/integrity/flags", json={"flags": [{
            "session_id": "sess-owner", "flag_type": "suspicious_process",
            "detail": "proc", "severity": "medium",
        }]})
        assert resp.status_code == 401


class TestIntegrityIntakeWithToken:
    def test_integrity_flags_saved_with_owner_token(self, public_client):
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/integrity/flags",
            headers={"X-Interview-Token": token},
            json={"flags": [{
                "session_id": "sess-owner", "flag_type": "suspicious_process",
                "detail": "proc.exe", "severity": "medium",
            }]},
        )
        assert resp.status_code == 200
        flags = db.get_all_integrity_flags()
        assert len(flags) == 1
        assert flags[0]["session_id"] == "sess-owner"

    def test_integrity_flags_for_foreign_session_rejected(self, public_client, fresh_db):
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/integrity/flags",
            headers={"X-Interview-Token": token},
            json={"flags": [{
                "session_id": "sess-someone-else", "flag_type": "suspicious_process",
                "detail": "proc.exe", "severity": "medium",
            }]},
        )
        assert resp.status_code == 403


class TestUploadSizeCaps:
    def test_oversized_live_frame_rejected(self, public_client, tmp_path, monkeypatch):
        import api.routes.sessions as sessions_route

        monkeypatch.setattr(sessions_route, "LIVE_FRAMES_DIR", tmp_path / "frames")
        _, token = _sponsor_candidate(public_client)
        resp = public_client.post(
            "/api/sessions/sess-owner/live-frame",
            content=b"\xff\xd8" + b"x" * (sessions_route.MAX_LIVE_FRAME_BYTES + 10) + b"\xff\xd9",
            headers={"Content-Type": "image/jpeg", "X-Interview-Token": token},
        )
        assert resp.status_code == 413
        assert not (tmp_path / "frames" / "sess-owner.jpg").exists()

    def test_oversized_recording_rejected(self, public_client, tmp_path, monkeypatch):
        import api.routes.sessions as sessions_route

        monkeypatch.setattr(sessions_route, "UPLOADS_DIR", tmp_path / "uploads")
        _, token = _sponsor_candidate(public_client)
        # Force the file cap tiny so the test is fast and deterministic.
        monkeypatch.setattr(sessions_route, "MAX_RECORDING_FILE_BYTES", 1024)
        resp = public_client.post(
            "/api/sessions/sess-owner/upload",
            headers={"X-Interview-Token": token},
            files={"video": ("big.webm", b"v" * (2048), "video/webm")},
        )
        assert resp.status_code == 413

    def test_oversized_recruiter_resume_rejected(self, client, tmp_path, monkeypatch, fresh_db):
        import api.routes.candidates as candidates_route

        monkeypatch.setattr(candidates_route, "RESUME_DIR", tmp_path / "resumes")
        monkeypatch.setattr(candidates_route, "MAX_RESUME_BYTES", 1024)
        client.post("/api/jobs", json={
            "job_id": "job-size", "title": "Size Job", "description": "d",
            "required_skills": ["python"], "experience_level": "Junior", "department": "Eng",
        })
        client.post("/api/candidates", json={
            "candidate_id": "cand-size", "job_id": "job-size",
            "name": "Big Resume", "email": "big@example.com",
        })
        resp = client.post(
            "/api/candidates/cand-size/resume",
            files={"file": ("r.txt", b"r" * (2048), "text/plain")},
        )
        assert resp.status_code == 400