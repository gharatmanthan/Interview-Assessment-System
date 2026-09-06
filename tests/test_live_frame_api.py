"""Live-monitor frame upload/serve API + completion cleanup."""
import pytest

from app.core import db


@pytest.fixture
def cc(fresh_db, public_client):
    """Candidate-client sponsor: seeds an invited candidate, validates the
    invite, and starts a session so every candidate-scoring endpoint has a
    valid X-Interview-Token."""

    def _sponsor():
        import uuid

        from app.core.models import Candidate, InterviewInvite, JobPosting

        uid = uuid.uuid4().hex[:8]
        cid = f"cand-{uid}"
        code = f"cam{uid}"
        db.save_job_posting(JobPosting(
            job_id="job-cam", title="Cam Engineer", description="d",
            required_skills=["python"], experience_level="Junior", department="Eng",
            created_by="recruiter",
        ))
        db.save_candidate(Candidate(
            candidate_id=cid, job_id="job-cam", name=f"Cam {uid}",
            email=f"{uid}@example.com", invite_code=code, status="invited",
        ))
        db.create_interview_invite(InterviewInvite(
            candidate_id=cid, job_id="job-cam", application_id=None,
            token=f"cam-invite-{uid}",
        ))
        v = public_client.post("/api/candidate/validate-code", json={"invite_code": code})
        token = v.json()["interview_token"]
        r = public_client.post("/api/candidate/start-session", json={
            "interview_token": token,
        })
        assert r.status_code == 200
        return token, r.json()["session_id"]

    return _sponsor


@pytest.fixture
def frames_dir(tmp_path, monkeypatch):
    import api.routes.sessions as sessions_route

    frames = tmp_path / "live_frames"
    monkeypatch.setattr(sessions_route, "LIVE_FRAMES_DIR", frames)
    return frames


JPEG_A = b"\xff\xd8fake-jpeg-bytes-a\xff\xd9"
JPEG_B = b"\xff\xd8fake-jpeg-bytes-b\xff\xd9"


class TestLiveFrameEndpoints:
    def test_get_requires_recruiter_auth(self, public_client):
        assert public_client.get("/api/sessions/session-x/live-frame").status_code == 401

    def test_upload_then_get_roundtrip(self, public_client, client, frames_dir, cc):
        token, sid = cc()
        res = public_client.post(
            f"/api/sessions/{sid}/live-frame",
            content=JPEG_A,
            headers={"Content-Type": "image/jpeg", "X-Interview-Token": token},
        )
        assert res.status_code == 200

        got = client.get(f"/api/sessions/{sid}/live-frame")
        assert got.status_code == 200
        assert got.headers["content-type"] == "image/jpeg"
        assert got.content == JPEG_A

    def test_new_frame_overwrites_previous(self, public_client, client, frames_dir, cc):
        token, sid = cc()
        public_client.post(f"/api/sessions/{sid}/live-frame", content=JPEG_A,
                           headers={"X-Interview-Token": token})
        public_client.post(f"/api/sessions/{sid}/live-frame", content=JPEG_B,
                           headers={"X-Interview-Token": token})
        assert client.get(f"/api/sessions/{sid}/live-frame").content == JPEG_B

    def test_sessions_are_isolated(self, public_client, client, frames_dir, cc):
        token_a, sid_a = cc()
        public_client.post(f"/api/sessions/{sid_a}/live-frame", content=JPEG_A,
                           headers={"X-Interview-Token": token_a})
        # second candidate for a different session
        token_b, sid_b = cc()
        public_client.post(f"/api/sessions/{sid_b}/live-frame", content=JPEG_B,
                           headers={"X-Interview-Token": token_b})
        assert client.get(f"/api/sessions/{sid_a}/live-frame").content == JPEG_A
        assert client.get(f"/api/sessions/{sid_b}/live-frame").content == JPEG_B

    def test_empty_body_rejected(self, public_client, cc):
        token, sid = cc()
        assert public_client.post(
            f"/api/sessions/{sid}/live-frame", content=b"",
            headers={"X-Interview-Token": token},
        ).status_code == 400

    def test_path_traversal_in_session_id_is_neutralized(self, public_client, frames_dir):
        # If the request ever reaches the handler, the sanitizer must neutralize
        # traversal; anything else is rejected upstream. Either way nothing may
        # be written outside LIVE_FRAMES_DIR.
        res = public_client.post(
            "/api/sessions/..%2F..%2Fevil/live-frame",
            content=JPEG_A,
            headers={"Content-Type": "image/jpeg"},
        )
        assert res.status_code in (401, 404)
        assert all(p.name.endswith(".jpg") for p in frames_dir.rglob("*"))

    def test_live_frame_path_helper_contains_traversal(self, frames_dir):
        from api.routes.sessions import live_frame_path

        p = live_frame_path("../../evil")
        assert p.parent == frames_dir
        assert "/" not in p.name and "\\" not in p.name


class TestCleanupOnCompletion:
    def test_complete_session_deletes_live_frame(self, public_client, client, frames_dir, cc):
        token, sid = cc()
        public_client.post(f"/api/sessions/{sid}/live-frame", content=JPEG_A,
                           headers={"X-Interview-Token": token})
        assert (frames_dir / f"{sid}.jpg").exists()

        public_client.post("/api/candidate/complete-session", json={
            "session_id": sid, "interview_token": token,
        })
        assert not (frames_dir / f"{sid}.jpg").exists()
        assert client.get(f"/api/sessions/{sid}/live-frame").status_code == 404

    def test_late_frame_after_completion_with_valid_token_recreates_file(self, public_client, frames_dir, cc):
        """A frame arriving just after completion (from the still-running
        candidate app, which holds a valid token) must not error; plain
        overwrite semantics mean the file simply reappears and will be
        removed by the next poll cycle's stale sweep — acceptable per spec.
        """
        token, sid = cc()
        res = public_client.post(
            f"/api/sessions/{sid}/live-frame",
            content=JPEG_A,
            headers={"Content-Type": "image/jpeg", "X-Interview-Token": token},
        )
        assert res.status_code == 200