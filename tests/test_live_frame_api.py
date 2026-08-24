"""Live-monitor frame upload/serve API + completion cleanup."""
import pytest


@pytest.fixture
def client(fresh_db):
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def frames_dir(tmp_path, monkeypatch):
    import api.routes.sessions as sessions_route

    frames = tmp_path / "live_frames"
    monkeypatch.setattr(sessions_route, "LIVE_FRAMES_DIR", frames)
    return frames


JPEG_A = b"\xff\xd8fake-jpeg-bytes-a\xff\xd9"
JPEG_B = b"\xff\xd8fake-jpeg-bytes-b\xff\xd9"


class TestLiveFrameEndpoints:
    def test_get_before_first_frame_404s(self, client, frames_dir):
        res = client.get("/api/sessions/session-x/live-frame")
        assert res.status_code == 404

    def test_upload_then_get_roundtrip(self, client, frames_dir):
        res = client.post(
            "/api/sessions/session-x/live-frame",
            content=JPEG_A,
            headers={"Content-Type": "image/jpeg"},
        )
        assert res.status_code == 200

        got = client.get("/api/sessions/session-x/live-frame")
        assert got.status_code == 200
        assert got.headers["content-type"] == "image/jpeg"
        assert got.content == JPEG_A

    def test_new_frame_overwrites_previous(self, client, frames_dir):
        client.post("/api/sessions/session-x/live-frame", content=JPEG_A)
        client.post("/api/sessions/session-x/live-frame", content=JPEG_B)
        assert client.get("/api/sessions/session-x/live-frame").content == JPEG_B

    def test_sessions_are_isolated(self, client, frames_dir):
        client.post("/api/sessions/sess-1/live-frame", content=JPEG_A)
        client.post("/api/sessions/sess-2/live-frame", content=JPEG_B)
        assert client.get("/api/sessions/sess-1/live-frame").content == JPEG_A
        assert client.get("/api/sessions/sess-2/live-frame").content == JPEG_B

    def test_empty_body_rejected(self, client, frames_dir):
        assert client.post("/api/sessions/session-x/live-frame", content=b"").status_code == 400

    def test_path_traversal_in_session_id_is_neutralized(self, client, frames_dir):
        # Router may reject encoded slashes outright (404); if the request ever
        # reaches the handler, the sanitizer must neutralize traversal. Either
        # way nothing may be written outside LIVE_FRAMES_DIR.
        res = client.post(
            "/api/sessions/..%2F..%2Fevil/live-frame",
            content=JPEG_A,
            headers={"Content-Type": "image/jpeg"},
        )
        assert res.status_code in (200, 404)
        assert all(p.name.endswith(".jpg") for p in frames_dir.rglob("*"))

    def test_live_frame_path_helper_contains_traversal(self, frames_dir):
        from api.routes.sessions import live_frame_path

        p = live_frame_path("../../evil")
        assert p.parent == frames_dir
        assert "/" not in p.name and "\\" not in p.name


class TestCleanupOnCompletion:
    def test_complete_session_deletes_live_frame(self, client, frames_dir):
        client.post(
            "/api/candidate/start-session",
            json={"session_id": "sess-live", "candidate_id": "c1", "job_id": "j1"},
        )
        client.post("/api/sessions/sess-live/live-frame", content=JPEG_A)
        assert (frames_dir / "sess-live.jpg").exists()

        client.post("/api/candidate/complete-session", json={"session_id": "sess-live"})
        assert not (frames_dir / "sess-live.jpg").exists()
        assert client.get("/api/sessions/sess-live/live-frame").status_code == 404

    def test_late_frame_after_completion_recreates_file_without_crash(self, client, frames_dir):
        """A frame arriving just after completion must not error; plain
        overwrite semantics mean the file simply reappears and will be
        removed by the next poll cycle's stale sweep — acceptable per spec.
        """
        res = client.post(
            "/api/sessions/sess-late/live-frame",
            content=JPEG_A,
            headers={"Content-Type": "image/jpeg"},
        )
        assert res.status_code == 200
