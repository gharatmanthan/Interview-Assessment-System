"""Auth + authorization (ownership/IDOR) + signed-media + invite hardening.

Uses the DB-level register helper to mint tokens directly, so HTTP auth
rate limits don't interfere.
"""
import io
import pytest
from fastapi.testclient import TestClient

from app.core import db


def _token_for(username: str, password: str = "secret123") -> str:
    from app.core.auth import register_recruiter
    from app.core.tokens import create_token

    register_recruiter(username, password, "Recruiter")
    token, _ = create_token(username)
    return token


def _auth_client(username: str = "recruiter", password: str = "secret123"):
    from api.main import app

    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {_token_for(username, password)}"})
    return client


def _create_job(client, job_id="job-a", title="Eng A"):
    client.post("/api/jobs", json={
        "job_id": job_id,
        "title": title,
        "description": "We need python and sql.",
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": 50.0,
        "minimum_experience_years": 3,
    })


class TestRecruiterAuth:
    def test_private_routes_require_auth(self, public_client):
        protected = [
            "/api/auth/me",
            "/api/jobs",
            "/api/candidates",
            "/api/applications",
            "/api/scheduling",
            "/api/settings",
            "/api/reports/dashboard",
            "/api/email-intake/poll-logs",
            "/api/media/sign",
        ]
        for path in protected:
            assert public_client.get(path).status_code == 401, path

    def test_public_routes_are_open(self, public_client):
        assert public_client.get("/api/public/jobs/nope").status_code == 404
        r = public_client.post("/api/candidate/validate-code", json={"invite_code": ""})
        assert r.status_code == 200

    def test_me_roundtrip(self, client):
        body = client.get("/api/auth/me").json()
        assert body["username"] == "recruiter"

    def test_invalid_token_rejected(self, public_client):
        public_client.headers.update({"Authorization": "Bearer not-a-real-token"})
        assert public_client.get("/api/jobs").status_code == 401

    def test_interview_token_cannot_authenticate_as_recruiter(self, public_client, fresh_db):
        from app.core.tokens import create_interview_token

        itoken, _ = create_interview_token("cand-1", "job-a")
        public_client.headers.update({"Authorization": f"Bearer {itoken}"})
        # The interview-scoped token is signed with the same secret but typed
        # differently — it must never be accepted on recruiter routes.
        assert public_client.get("/api/jobs").status_code == 401
        assert public_client.get("/api/settings").status_code == 401


class TestOwnershipScoping:
    def test_recruiter_cannot_see_others_jobs_or_their_screened_applications(self, fresh_db):
        # Recruiter A owns a job with an application (via the public apply flow).
        with _auth_client("owner-a") as a:
            _create_job(a, "job-a", "Eng A")
            a.post(
                "/api/public/apply/job-a",
                data={"name": "Jane Doe", "email": "jane@example.com"},
                files={"resume": ("resume.txt", io.BytesIO(
                    b"Backend engineer with python, sql and rest api experience. "
                    b"5 years of experience. B.Tech Computer Science."
                ), "text/plain")},
            )
        from app.screening.service import run_screening_jobs
        run_screening_jobs()

        with _auth_client("owner-a") as a:
            assert len(a.get("/api/applications").json()["applications"]) == 1
            app_id = a.get("/api/applications").json()["applications"][0]["application_id"]
            assert a.get(f"/api/applications/{app_id}").status_code == 200
            assert len(a.get("/api/candidates").json()) == 1

            with _auth_client("owner-b") as b:
                assert b.get("/api/jobs").json() == []
                assert b.get("/api/applications").json()["applications"] == []
                assert b.get("/api/candidates").json() == []
                assert b.get("/api/scheduling").json() == []
                assert b.get("/api/reports/compare", params={"job_id": "job-a"}).status_code == 403
                assert b.get("/api/candidates/job/job-a").status_code == 403
                assert b.get(f"/api/applications/{app_id}").status_code == 403
                assert b.post("/api/scheduling/allocate", json={
                    "candidate_id": "x", "job_id": "job-a",
                }).status_code == 403

    def test_create_candidate_requires_owned_job(self, fresh_db):
        with _auth_client("owner-a") as a:
            _create_job(a, "job-a", "Eng A")
        with _auth_client("owner-b") as b:
            r = b.post("/api/candidates", json={
                "candidate_id": "c1", "job_id": "job-a",
                "name": "Jane", "email": "jane@example.com",
            })
            assert r.status_code == 403


class TestSignedMedia:
    def test_sign_requires_auth(self, public_client):
        assert public_client.get("/api/media/sign", params={"path": "a/b"}).status_code == 401

    def _seed_upload_session(self, recruiter, session_id="sess-1", job_id="job-a"):
        _create_job(recruiter, job_id, "Eng A")
        recruiter.post("/api/sessions", json={
            "session_id": session_id, "candidate_name": "Jane",
            "job_title": "Eng A", "job_id": job_id,
        })

    def test_media_served_only_with_valid_signature(self, public_client, tmp_path, monkeypatch):
        import api.routes.media as media_route

        monkeypatch.setattr(media_route, "MEDIA_DIR", tmp_path)
        target = tmp_path / "sess-1"
        target.mkdir()
        (target / "recording.bin").write_bytes(b"recording-bytes")

        with _auth_client() as recruiter:
            self._seed_upload_session(recruiter)
            url = recruiter.get("/api/media/sign", params={"path": "sess-1/recording.bin"}).json()["url"]

        # Unsigned fetch -> 403.
        assert public_client.get("/media/sess-1/recording.bin").status_code == 403

        # Signed fetch -> file served.
        resp = public_client.get(url)
        assert resp.status_code == 200
        assert resp.content == b"recording-bytes"

    def test_traversal_rejected_even_with_signature(self, public_client, tmp_path, monkeypatch):
        import api.routes.media as media_route

        monkeypatch.setattr(media_route, "MEDIA_DIR", tmp_path)
        (tmp_path / "secret.txt").write_text("nope")

        with _auth_client() as recruiter:
            self._seed_upload_session(recruiter)
            # A path starting outside any media root is refused at signing.
            assert recruiter.get("/api/media/sign", params={"path": "../../secret.txt"}).status_code == 403
            # An owned session can be signed, but the traversal segments are
            # resolved away when serving — nothing outside MEDIA_DIR is ever
            # read (404) or the resolved path check refuses (403).
            url = recruiter.get(
                "/api/media/sign", params={"path": "sess-1/../secret.txt"}
            ).json()["url"]
        resp = public_client.get(url)
        assert resp.status_code in (403, 404)

    def test_recruiter_cannot_sign_another_jobs_media(self, fresh_db, tmp_path, monkeypatch):
        import api.routes.media as media_route

        monkeypatch.setattr(media_route, "MEDIA_DIR", tmp_path)
        target = tmp_path / "sess-9"
        target.mkdir()
        (target / "recording.bin").write_bytes(b"recording-bytes")

        with _auth_client("owner-a") as a:
            self._seed_upload_session(a, "sess-9", "job-a")
        with _auth_client("owner-b") as b:
            assert b.get("/api/media/sign", params={"path": "sess-9/recording.bin"}).status_code == 403

    def test_resume_served_only_when_owned(self, public_client, tmp_path, monkeypatch):
        import api.routes.media as media_route

        monkeypatch.setattr(media_route, "RESUMES_DIR", tmp_path)
        (tmp_path / "candidate-a.txt").write_text("resume text")

        from app.core.models import Application
        with _auth_client("owner-a") as a:
            _create_job(a, "job-a", "Eng A")
            db.create_application(Application(
                application_id="app-1", job_id="job-a", full_name="Jane",
                email="jane@example.com", resume_path=str(tmp_path / "candidate-a.txt"),
            ))
            url = a.get("/api/media/sign", params={"path": "candidate-a.txt"}).json()["url"]

        resp = public_client.get(url)
        assert resp.status_code == 200
        assert resp.content == b"resume text"

        # A different recruiter owns neither the application nor the job.
        with _auth_client("owner-b") as b:
            assert b.get("/api/media/sign", params={"path": "candidate-a.txt"}).status_code == 403

    def test_recording_upload_neutralizes_traversal_session_id(self, fresh_db, tmp_path, monkeypatch):
        import asyncio
        import io as _io

        import api.routes.sessions as sessions_route
        from fastapi import UploadFile

        monkeypatch.setattr(sessions_route, "UPLOADS_DIR", tmp_path)

        from app.core.models import Candidate, InterviewSession
        db.save_session(InterviewSession(
            session_id="../evil", candidate_name="Jane", job_title="Eng A", job_id="job-a",
        ))
        db.save_candidate(Candidate(
            candidate_id="cand-evil", job_id="job-a", name="Jane", email="evil@example.com",
            invite_code="evil123", status="invited", session_id="../evil",
        ))
        from app.core.tokens import create_interview_token
        token, _ = create_interview_token("cand-evil", "job-a")

        video = UploadFile(file=_io.BytesIO(b"clip-bytes"), filename="clip.bin")
        res = asyncio.run(sessions_route.upload_recording("../evil", video=video, audio=None,
                                                          x_interview_token=token))
        assert res["success"] is True
        # Even though the session_id literally contains traversal, nothing may
        # be written outside UPLOADS_DIR and the stored rel path is sanitized.
        assert not (tmp_path.parent / "evil").exists()
        assert (tmp_path / ".._evil" / "clip.bin").exists()
        assert res["saved"]["video_path"].startswith(".._evil/")

    def test_absolute_resume_path_is_normalized_for_media(self, tmp_path, monkeypatch):
        import api.routes.media as media_route

        monkeypatch.setattr(media_route, "RESUMES_DIR", tmp_path)
        target = tmp_path / "apply-job-1-jane.txt"
        target.write_text("resume text")

        rel = media_route.to_relative_media_path(str(target))
        assert rel == "apply-job-1-jane.txt"

        assert media_route.to_relative_media_path("already/relative.txt") == "already/relative.txt"


class TestInterviewInviteHardening:
    def test_invite_consumed_once_session_starts(self, fresh_db, public_client):
        with _auth_client() as recruiter:
            _create_job(recruiter, "job-a", "Eng A")
            recruiter.post(
                "/api/public/apply/job-a",
                data={"name": "Jane Doe", "email": "jane@example.com"},
                files={"resume": ("resume.txt", io.BytesIO(
                    b"Backend engineer with python, sql and rest api experience. "
                    b"5 years of experience. B.Tech Computer Science."
                ), "text/plain")},
            )
        from app.screening.service import run_screening_jobs
        run_screening_jobs()

        candidate = db.get_all_candidates()[0]
        code = candidate["invite_code"]

        first = public_client.post("/api/candidate/validate-code", json={"invite_code": code})
        assert first.json()["valid"] is True
        token = first.json()["interview_token"]
        assert token
        assert first.json()["candidate"].get("invite_code") is None

        start = public_client.post("/api/candidate/start-session", json={
            "session_id": "sess-1", "candidate_id": candidate["candidate_id"], "job_id": "job-a",
            "interview_token": token,
        })
        assert start.status_code == 200

        invites = db.get_interview_invites_for_candidate(candidate["candidate_id"])
        assert invites[0]["status"] == "consumed"

        denied = public_client.post("/api/candidate/validate-code", json={"invite_code": code})
        assert denied.json()["valid"] is False
        assert "already been used" in denied.json()["message"]

    def test_start_session_requires_valid_interview_token(self, fresh_db, public_client):
        with _auth_client() as recruiter:
            _create_job(recruiter, "job-a", "Eng A")
            recruiter.post(
                "/api/public/apply/job-a",
                data={"name": "Jane Doe", "email": "jane@example.com"},
                files={"resume": ("resume.txt", io.BytesIO(
                    b"Backend engineer with python, sql and rest api experience. "
                    b"5 years of experience. B.Tech Computer Science."
                ), "text/plain")},
            )
        from app.screening.service import run_screening_jobs
        run_screening_jobs()

        candidate = db.get_all_candidates()[0]
        code = candidate["invite_code"]

        # No token.
        r = public_client.post("/api/candidate/start-session", json={
            "session_id": "sess-x", "candidate_id": candidate["candidate_id"], "job_id": "job-a",
        })
        assert r.status_code == 401

        # Forged / garbage token.
        r = public_client.post("/api/candidate/start-session", json={
            "session_id": "sess-x", "candidate_id": candidate["candidate_id"], "job_id": "job-a",
            "interview_token": "garbage-token",
        })
        assert r.status_code == 401

        # Valid token but edited identity must be ignored (derived server-side).
        v = public_client.post("/api/candidate/validate-code", json={"invite_code": code})
        token = v.json()["interview_token"]
        r = public_client.post("/api/candidate/start-session", json={
            "session_id": "sess-x", "candidate_id": "someone-else", "job_id": "job-a",
            "interview_token": token,
        })
        assert r.status_code == 200
        sessions = [s for s in db.get_all_sessions() if s["session_id"] == "sess-x"]
        assert sessions and sessions[0]["candidate_name"] == "Jane Doe"

        # Recruiter auth tokens are not valid interview access.
        r = public_client.post("/api/candidate/start-session", json={
            "session_id": "sess-y", "candidate_id": candidate["candidate_id"], "job_id": "job-a",
            "interview_token": _token_for("recruiter_b-a2c"),
        })
        assert r.status_code == 401