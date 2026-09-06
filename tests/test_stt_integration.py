"""Phase 2A: STT Integration — /api/sessions/{session_id}/transcribe tests.

Mocks the Whisper model so tests run without downloading it or requiring GPU.
"""
import io
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core import db
from app.core.models import Candidate, InterviewSession, JobPosting


def _job(job_id="job-stt", title="STT Engineer", owner="recruiter"):
    db.save_job_posting(JobPosting(
        job_id=job_id, title=title, description="d", required_skills=["python"],
        experience_level="Junior", department="Eng", created_by=owner,
    ))


def _candidate_and_session(cand_id="cand-stt", session_id="sess-stt"):
    _job()
    db.save_candidate(Candidate(
        candidate_id=cand_id, job_id="job-stt", name="STT Tester",
        email="stt@example.com", invite_code="code-stt", status="invited",
    ))
    db.save_session(InterviewSession(
        session_id=session_id, candidate_name="STT Tester",
        job_title="STT Engineer", job_id="job-stt", status="in_progress",
    ))
    db.update_candidate_status(cand_id, "in_progress", session_id=session_id)


def _token_for(cand_id="cand-stt", job_id="job-stt"):
    from app.core.tokens import create_interview_token
    token, _ = create_interview_token(cand_id, job_id)
    return token


class TestTranscribeEndpoint:
    def test_successful_transcription(self, public_client, tmp_path):
        _candidate_and_session()
        token = _token_for()
        audio_dir = tmp_path / "uploads" / "sess-stt"
        audio_dir.mkdir(parents=True)
        (audio_dir / "q_q1.webm").write_bytes(b"fake-audio-data")

        import api.routes.sessions as sess_mod
        with patch.object(sess_mod, "UPLOADS_DIR", tmp_path / "uploads"):
            with patch("app.engine.stt.transcribe", return_value="Hello world transcript"):
                resp = public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q1"},
                    files={"audio": ("q1.webm", b"fake-audio-data", "audio/webm")},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["question_id"] == "q1"
        assert body["transcript"] == "Hello world transcript"
        assert body["audio_path"] is not None

        stored = db.get_question_transcript("sess-stt", "q1")
        assert stored is not None
        assert stored["transcript"] == "Hello world transcript"

    def test_invalid_token_rejected(self, public_client, tmp_path):
        _candidate_and_session()
        resp = public_client.post(
            "/api/sessions/sess-stt/transcribe",
            headers={"X-Interview-Token": "bogus-token"},
            data={"question_id": "q1"},
            files={"audio": ("q1.webm", b"data", "audio/webm")},
        )
        assert resp.status_code == 401

    def test_no_token_rejected(self, public_client, tmp_path):
        _candidate_and_session()
        resp = public_client.post(
            "/api/sessions/sess-stt/transcribe",
            data={"question_id": "q1"},
            files={"audio": ("q1.webm", b"data", "audio/webm")},
        )
        assert resp.status_code == 401

    def test_cannot_transcribe_another_candidates_session(self, public_client, fresh_db):
        _candidate_and_session(cand_id="cand-owner", session_id="sess-owner")
        token_owner = _token_for(cand_id="cand-owner", job_id="job-stt")

        db.save_candidate(Candidate(
            candidate_id="cand-other", job_id="job-stt", name="Other",
            email="other@example.com", invite_code="code-other", status="invited",
        ))
        db.save_session(InterviewSession(
            session_id="sess-other", candidate_name="Other",
            job_title="STT Engineer", job_id="job-stt", status="in_progress",
        ))
        db.update_candidate_status("cand-other", "in_progress", session_id="sess-other")

        resp = public_client.post(
            "/api/sessions/sess-other/transcribe",
            headers={"X-Interview-Token": token_owner},
            data={"question_id": "q1"},
            files={"audio": ("q1.webm", b"data", "audio/webm")},
        )
        assert resp.status_code == 403

    def test_session_not_found(self, public_client, fresh_db):
        """Candidate exists with a dangling session_id (no matching sessions
        row). Auth passes but the session lookup returns 404."""
        _job()
        db.save_candidate(Candidate(
            candidate_id="cand-dangle", job_id="job-stt", name="Dangle",
            email="dangle@example.com", invite_code="code-dangle",
            status="in_progress", session_id="nonexistent-sess",
        ))
        token = _token_for(cand_id="cand-dangle", job_id="job-stt")
        resp = public_client.post(
            "/api/sessions/nonexistent-sess/transcribe",
            headers={"X-Interview-Token": token},
            data={"question_id": "q1"},
            files={"audio": ("q1.webm", b"data", "audio/webm")},
        )
        assert resp.status_code == 404

    def test_stt_failure_returns_500(self, public_client, tmp_path):
        _candidate_and_session()
        token = _token_for()
        audio_dir = tmp_path / "uploads" / "sess-stt"
        audio_dir.mkdir(parents=True)
        (audio_dir / "q_q1.webm").write_bytes(b"fake-audio-data")

        import api.routes.sessions as sess_mod
        with patch.object(sess_mod, "UPLOADS_DIR", tmp_path / "uploads"):
            with patch("app.engine.stt.transcribe", side_effect=RuntimeError("Model init failed")):
                resp = public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q1"},
                    files={"audio": ("q1.webm", b"fake-audio-data", "audio/webm")},
                )

        assert resp.status_code == 500
        assert "Transcription failed" in resp.json()["detail"]

    def test_empty_transcript_returns_422(self, public_client, tmp_path):
        _candidate_and_session()
        token = _token_for()
        audio_dir = tmp_path / "uploads" / "sess-stt"
        audio_dir.mkdir(parents=True)
        (audio_dir / "q_q1.webm").write_bytes(b"fake-audio-data")

        import api.routes.sessions as sess_mod
        with patch.object(sess_mod, "UPLOADS_DIR", tmp_path / "uploads"):
            with patch("app.engine.stt.transcribe", return_value=""):
                resp = public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q1"},
                    files={"audio": ("q1.webm", b"fake-audio-data", "audio/webm")},
                )

        assert resp.status_code == 422
        assert "empty" in resp.json()["detail"].lower()

    def test_transcript_persists_and_is_queryable(self, public_client, tmp_path):
        _candidate_and_session()
        token = _token_for()
        audio_dir = tmp_path / "uploads" / "sess-stt"
        audio_dir.mkdir(parents=True)
        (audio_dir / "q_q1.webm").write_bytes(b"fake-audio-data")
        (audio_dir / "q_q2.webm").write_bytes(b"fake-audio-data-2")

        import api.routes.sessions as sess_mod
        with patch.object(sess_mod, "UPLOADS_DIR", tmp_path / "uploads"):
            with patch("app.engine.stt.transcribe", return_value="First answer"):
                resp1 = public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q1"},
                    files={"audio": ("q1.webm", b"fake-audio-data", "audio/webm")},
                )
            with patch("app.engine.stt.transcribe", return_value="Second answer"):
                resp2 = public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q2"},
                    files={"audio": ("q2.webm", b"fake-audio-data-2", "audio/webm")},
                )

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        transcripts = db.get_question_transcripts("sess-stt")
        assert len(transcripts) == 2
        q_ids = {t["question_id"] for t in transcripts}
        assert q_ids == {"q1", "q2"}

    def test_submit_answer_with_transcript_works(self, public_client):
        _candidate_and_session()
        token = _token_for()

        resp = public_client.post("/api/candidate/submit-answer", json={
            "session_id": "sess-stt",
            "question_id": "q1",
            "category": "technical",
            "transcript": "This is the STT transcript from audio.",
            "interview_token": token,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert 0 <= body["score"]["score"] <= 100

    def test_typed_answer_fallback_still_works(self, public_client):
        _candidate_and_session()
        token = _token_for()

        resp = public_client.post("/api/candidate/submit-answer", json={
            "session_id": "sess-stt",
            "question_id": "q1",
            "category": "technical",
            "transcript": "This is a typed answer without STT.",
            "interview_token": token,
        })
        assert resp.status_code == 200
        assert 0 <= resp.json()["score"]["score"] <= 100

    def test_retranscribing_overwrites_previous(self, public_client, tmp_path):
        _candidate_and_session()
        token = _token_for()
        audio_dir = tmp_path / "uploads" / "sess-stt"
        audio_dir.mkdir(parents=True)
        (audio_dir / "q_q1.webm").write_bytes(b"fake-audio-data")

        import api.routes.sessions as sess_mod
        with patch.object(sess_mod, "UPLOADS_DIR", tmp_path / "uploads"):
            with patch("app.engine.stt.transcribe", return_value="First transcript"):
                public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q1"},
                    files={"audio": ("q1.webm", b"fake-audio-data", "audio/webm")},
                )
            with patch("app.engine.stt.transcribe", return_value="Updated transcript"):
                resp = public_client.post(
                    "/api/sessions/sess-stt/transcribe",
                    headers={"X-Interview-Token": token},
                    data={"question_id": "q1"},
                    files={"audio": ("q1.webm", b"fake-audio-data", "audio/webm")},
                )

        assert resp.status_code == 200
        assert resp.json()["transcript"] == "Updated transcript"
        stored = db.get_question_transcript("sess-stt", "q1")
        assert stored["transcript"] == "Updated transcript"

    def test_empty_audio_rejected(self, public_client, tmp_path):
        _candidate_and_session()
        token = _token_for()
        audio_dir = tmp_path / "uploads" / "sess-stt"
        audio_dir.mkdir(parents=True)

        import api.routes.sessions as sess_mod
        with patch.object(sess_mod, "UPLOADS_DIR", tmp_path / "uploads"):
            resp = public_client.post(
                "/api/sessions/sess-stt/transcribe",
                headers={"X-Interview-Token": token},
                data={"question_id": "q1"},
                files={"audio": ("q1.webm", b"", "audio/webm")},
            )
        assert resp.status_code == 400

    def test_question_transcripts_table_created(self, fresh_db):
        conn = db.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "question_transcripts" in tables
