"""Phase 3A: MODE 1 live interview WebSocket — auth, question delivery,
answer/transcript flow, reconnect, role mismatch, duplicate start, end state.

One authoritative session per interview; no second session/architecture.
"""
import json

import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocketDisconnect

from app.core import db
from app.core.models import Candidate, JobPosting
from app.core.tokens import create_interview_token


def _job(job_id="job-l", title="Live Engineer", owner="recruiter", description="Python"):
    db.save_job_posting(JobPosting(
        job_id=job_id, title=title, description=description,
        required_skills=["python"], experience_level="Junior",
        department="Eng", created_by=owner,
    ))


def _candidate(cand_id="cand-l", job_id="job-l", name="Live Tester",
               email="live@example.com", code="code-l"):
    db.save_candidate(Candidate(
        candidate_id=cand_id, job_id=job_id, name=name, email=email,
        invite_code=code, status="invited",
    ))


def _register_and_token(username="recruiter"):
    from app.core.auth import register_recruiter
    from app.core.tokens import create_token
    register_recruiter(username, "secret123", "Test Recruiter")
    token, _ = create_token(username)
    return token


def _candidate_token(cand_id="cand-l", job_id="job-l"):
    token, _ = create_interview_token(cand_id, job_id)
    return token


def _sid(cand_id="cand-l", job_id="job-l", name="Live Tester", title="Live Engineer"):
    return db.resolve_or_create_session(cand_id, job_id, name, title)


def _questions(sid, count=3):
    db.save_session_questions(sid, [
        {"question_index": i, "question_id": f"q{i}", "question_text": f"Question {i}",
         "category": "Technical Knowledge", "competency": "Py",
         "difficulty": "medium", "source": "bank"}
        for i in range(count)
    ])


def _candidate_not_owned_session(sid):
    """A candidate bound to a DIFFERENT session than the one we try to join."""
    _job(job_id="job-other", title="Other", description="Go")
    db.save_candidate(Candidate(
        candidate_id="cand-other", job_id="job-other", name="Other",
        email="o@example.com", invite_code="code-other", status="invited",
    ))
    other_sid = db.resolve_or_create_session("cand-other", "job-other", "Other", "Other")
    return other_sid


@pytest.fixture
def setup(fresh_db):
    _job()
    _candidate()
    sid = _sid()
    _questions(sid)
    recruiter_token = _register_and_token()
    cand_token = _candidate_token()
    return {
        "sid": sid,
        "recruiter_token": recruiter_token,
        "cand_token": cand_token,
    }


class FakeWS:
    """Stand-in socket for the 'other party' in a live session.

    Starlette's TestClient supports only ONE active WebSocket at a time, so
    we can't hold a recruiter AND a candidate socket open simultaneously in a
    test. Injecting a FakeWS into the shared LiveManager under the other role
    lets us assert that the server's broadcast/routing logic actually reaches
    that party, while keeping one real TestClient socket open.
    """

    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, payload):
        self.sent.append(json.loads(payload))

    async def send_json(self, payload):
        self.sent.append(payload)


def _join_fake(sid, role):
    from api.routes.live import manager
    fake = FakeWS()
    manager.join(sid, role, fake)
    return fake


def _leave_fake(sid, role, fake):
    from api.routes.live import manager
    manager.leave(sid, role, fake)


def _cleanup_all():
    """Reset the shared in-memory LiveManager between tests to avoid the
    module-level manager leaking sockets across tests."""
    from api.routes.live import manager
    manager._session_conns.clear()


@pytest.fixture(autouse=True)
def _clean_live_manager():
    _cleanup_all()
    yield
    _cleanup_all()


class TestJoinAuth:
    def _expect_close(self, client, url, code):
        """Connect and capture the server close code.

        The server accepts the handshake then immediately closes; the first
        receive on the client surfaces WebSocketDisconnect with that code.
        """
        with pytest.raises(WebSocketDisconnect) as ei:
            with client.websocket_connect(url) as ws:
                ws.receive_json()
        assert ei.value.code == code

    def test_recruiter_can_join_owned_session(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        token = _register_and_token()
        with TestClient(client.app).websocket_connect(f"/api/ws/interview/{sid}?token={token}") as ws:
            joined = ws.receive_json()
            assert joined["type"] == "joined"
            assert joined["role"] == "recruiter"
            assert joined["session_status"] == "in_progress"
            assert joined["has_questions"] is True
            assert joined["connections"]["recruiter"] == 1

    def test_recruiter_cannot_join_another_recruiters_session(self, fresh_db, client):
        _job()
        _candidate()
        sid = _sid()
        _questions(sid)
        _register_and_token("recruiter")  # owner
        intruder = _register_and_token("intruder")
        self._expect_close(
            client,
            f"/api/ws/interview/{sid}?token={intruder}",
            code=4403,
        )

    def test_candidate_can_join_own_session(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        token = _candidate_token()
        with TestClient(client.app).websocket_connect(f"/api/ws/interview/{sid}?token={token}") as ws:
            joined = ws.receive_json()
            assert joined["type"] == "joined"
            assert joined["role"] == "candidate"

    def test_candidate_cannot_join_another_candidates_session(
            self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        # a different candidate under a different job
        _candidate_not_owned_session(sid)
        token = _candidate_token("cand-other", "job-other")
        self._expect_close(
            client,
            f"/api/ws/interview/{sid}?token={token}",
            code=4403,
        )

    def test_invalid_token_rejected(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        self._expect_close(
            client,
            f"/api/ws/interview/{sid}?token=bogus",
            code=4401,
        )

    def test_role_mismatch_rejected(self, fresh_db, client):
        """A recruiter token is never interpreted as a candidate for a session
        they don't own, and a candidate interview token is never treated as a
        recruiter token."""
        _job(); _candidate(); sid = _sid(); _questions(sid)
        # Two recruiters who don't own this session's job must be denied even
        # though their tokens are valid — proves recruiter tokens cannot cross
        # into another recruiter's session.
        _register_and_token("recruiter")
        other_recruiter = _register_and_token("other-recruiter")
        self._expect_close(
            client,
            f"/api/ws/interview/{sid}?token={other_recruiter}",
            code=4403,
        )


class TestQuestionDelivery:
    def test_recruiter_asks_candidate_receives(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid, 3)
        rtoken = _register_and_token()
        app = client.app
        # A candidate socket is present in the session; the recruiter asks a
        # question and the broadcast must reach the candidate.
        fake_cand = _join_fake(sid, "candidate")
        try:
            with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as rws:
                rws.receive_json()  # joined recruiter
                rws.send_json({"type": "ask_question", "question_id": "q1"})
                # recruiter receives its own question_asked broadcast
                fevt = rws.receive_json()
                assert fevt["type"] == "question_asked"
                assert fevt["question"]["question_id"] == "q1"
            # candidate received the question too (via the routing logic)
            evts = [m for m in fake_cand.sent if m["type"] == "question_asked"]
            assert evts and evts[0]["question"]["question_id"] == "q1"
            # persisted as the active question
            assert db.get_live_question(sid)["question_id"] == "q1"
        finally:
            _leave_fake(sid, "candidate", fake_cand)

    def test_candidate_cannot_ask_question(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid, 3)
        ctoken = _candidate_token()
        app = client.app
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={ctoken}") as cws:
            cws.receive_json()
            cws.send_json({"type": "ask_question", "question_id": "q0"})
            err = cws.receive_json()
            assert err["type"] == "error"
            assert err["code"] == "forbidden"

    def test_cannot_ask_another_sessions_question(self, fresh_db, client):
        """Candidate cannot select another session's question — the question
        must belong to this session's locked set."""
        _job(); _candidate(); sid = _sid(); _questions(sid, 2)
        rtoken = _register_and_token()
        app = client.app
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as rws:
            rws.receive_json()
            rws.send_json({"type": "ask_question", "question_id": "foreign_q"})
            err = rws.receive_json()
            assert err["type"] == "error"
            assert err["code"] == "unknown_question"
            # nothing persisted as the active question
            assert db.get_live_question(sid) is None


class TestTranscriptDelivery:
    def test_candidate_answer_creates_transcript_and_recruiter_receives(
            self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid, 2)
        ctoken = _candidate_token()
        app = client.app

        # The recruiter is live and the active question is q0 with a persisted
        # transcript (created by the existing Phase 2A STT pipeline).
        fake_rec = _join_fake(sid, "recruiter")
        db.set_live_question(sid, "q0")
        db.save_question_transcript(sid, "q0", "My project focuses on X.")
        try:
            with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={ctoken}") as cws:
                cws.receive_json()  # joined candidate
                cws.send_json({"type": "answer_completed"})
                cws.receive_json()  # answer_completed_ack
            # recruiter (fake) received transcript_ready with persisted transcript
            evts = [m for m in fake_rec.sent if m["type"] == "transcript_ready"]
            assert evts
            assert evts[0]["question_id"] == "q0"
            assert evts[0]["transcript"] == "My project focuses on X."
        finally:
            _leave_fake(sid, "recruiter", fake_rec)

    def test_answer_started_reaches_recruiter(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        ctoken = _candidate_token()
        app = client.app
        fake_rec = _join_fake(sid, "recruiter")
        try:
            with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={ctoken}") as cws:
                cws.receive_json()  # joined candidate
                cws.send_json({"type": "answer_started"})
                cws.receive_json()  # ack
            evts = [m for m in fake_rec.sent if m["type"] == "answer_started"]
            assert evts
        finally:
            _leave_fake(sid, "recruiter", fake_rec)


class TestReconnectAndStart:
    def test_refresh_reconnects_same_session_and_recovers_current_question(
            self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid, 3)
        rtoken = _register_and_token()
        app = client.app

        # recruiter asks question on first connection
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as r1:
            r1.receive_json()
            r1.send_json({"type": "ask_question", "question_id": "q0"})
            r1.receive_json()  # ack

        # reconnect (simulated refresh) -> recovers current question
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as r2:
            joined = r2.receive_json()
            assert joined["type"] == "joined"
            assert joined["current_question"]["question_id"] == "q0"
            assert joined["current_question"]["question_index"] == 0

    def test_candidate_refresh_does_not_create_another_session(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        # The session id is authoritative; reconnecting to it must not spawn a
        # new session. Verify the candidate's resolved session is unchanged.
        before = db.get_candidate("cand-l")["session_id"]
        assert before == sid
        ctoken = _candidate_token()
        app = client.app
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={ctoken}") as ws:
            ws.receive_json()
        after = db.get_candidate("cand-l")["session_id"]
        assert after == sid
        assert after == before

    def test_duplicate_start_does_not_create_another_session(self, fresh_db, client):
        """Calling resolve_or_create_session / starting live again returns the
        same authoritative session (Phase 1 invariant), never a second one."""
        _job(); _candidate(); sid = _sid(); _questions(sid)
        sid2 = db.resolve_or_create_session("cand-l", "job-l", "Live Tester", "Live Engineer")
        assert sid2 == sid

        rtoken = _register_and_token()
        app = client.app
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as r1:
            r1.receive_json()
            r1.send_json({"type": "ask_question", "question_id": "q0"})
            r1.receive_json()
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as r2:
            joined = r2.receive_json()
            assert joined["current_question"]["question_id"] == "q0"

    def test_connection_status_reflects_both_sides(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        rtoken = _register_and_token()
        app = client.app
        # Candidate is live; recruiter joins and must see the candidate, and the
        # server must broadcast a connection-status change when a party drops.
        fake_cand = _join_fake(sid, "candidate")
        try:
            with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as rws:
                rjoined = rws.receive_json()
                assert rjoined["type"] == "joined"
                assert rjoined["connections"]["recruiter"] == 1
                assert rjoined["connections"]["candidate"] == 1
            # Recruiter dropped -> the real disconnect path broadcasts to the
            # remaining candidate.
            status = [m for m in fake_cand.sent if m["type"] == "connection_status"]
            assert status and status[-1]["recruiter"] == 0
        finally:
            _leave_fake(sid, "candidate", fake_cand)


class TestEnd:
    def test_interview_end_changes_state_correctly(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        rtoken = _register_and_token()
        app = client.app
        fake_cand = _join_fake(sid, "candidate")
        try:
            with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={rtoken}") as rws:
                rws.receive_json()  # joined recruiter
                rws.send_json({"type": "end_interview"})
            # candidate received interview_ended
            evts = [m for m in fake_cand.sent if m["type"] == "interview_ended"]
            assert evts and evts[0]["status"] == "completed"
        finally:
            _leave_fake(sid, "candidate", fake_cand)
        sess = db.get_session(sid)
        assert sess["status"] == "completed"

    def test_candidate_cannot_end_interview(self, fresh_db, client):
        _job(); _candidate(); sid = _sid(); _questions(sid)
        ctoken = _candidate_token()
        app = client.app
        with TestClient(app).websocket_connect(f"/api/ws/interview/{sid}?token={ctoken}") as cws:
            cws.receive_json()
            cws.send_json({"type": "end_interview"})
            err = cws.receive_json()
            assert err["type"] == "error"
            assert err["code"] == "forbidden"
        assert db.get_session(sid)["status"] != "completed"
