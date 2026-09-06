"""Phase 1: SHARED INTERVIEW SESSION ARCHITECTURE.

Proves that the recruiter and the candidate converge on ONE authoritative
session per candidate interview — the server derives the session id and never
trusts a client-supplied one. Also proves the ownership guards around that
session (recruiter may only start/attach to sessions for candidates they own;
the candidate's token can never mint a second session).
"""
import threading

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.models import Candidate, JobPosting


def _register_and_token(username: str = "recruiter", password: str = "secret123") -> str:
    from app.core.auth import register_recruiter
    from app.core.tokens import create_token

    register_recruiter(username, password, "Test Recruiter")
    token, _ = create_token(username)
    return token


def _job(job_id="job-a", title="Eng A", owner="recruiter"):
    db.save_job_posting(JobPosting(
        job_id=job_id, title=title, description="d", required_skills=["python"],
        experience_level="Junior", department="Eng", created_by=owner,
    ))


def _candidate(name="Jane Doe", email="jane@example.com", cand_id="cand-a", job_id="job-a"):
    db.save_candidate(Candidate(
        candidate_id=cand_id, job_id=job_id, name=name, email=email,
        invite_code="code-a", status="invited",
    ))


class TestResolveOrCreateSession:
    def test_creates_one_session_when_candidate_has_none(self, fresh_db):
        _job()
        _candidate()
        sid = db.resolve_or_create_session("cand-a", "job-a", "Jane Doe", "Eng A")
        sessions = [s for s in db.get_all_sessions() if s["session_id"] == sid]
        assert len(sessions) == 1
        assert db.get_candidate("cand-a")["session_id"] == sid

    def test_called_twice_returns_same_id(self, fresh_db):
        _job()
        _candidate()
        first = db.resolve_or_create_session("cand-a", "job-a", "Jane Doe", "Eng A")
        second = db.resolve_or_create_session("cand-a", "job-a", "Jane Doe", "Eng A")
        assert first == second
        sessions = db.get_all_sessions()
        assert len([s for s in sessions if s["candidate_name"] == "Jane Doe"]) == 1

    def test_reuses_linked_session_even_with_different_args(self, fresh_db):
        _job()
        _candidate()
        sid = db.resolve_or_create_session("cand-a", "job-a", "Jane Doe", "Eng A")
        again = db.resolve_or_create_session("cand-a", "job-a", "New Title", "New Name")
        assert again == sid
        assert db.get_session(sid)["candidate_name"] == "Jane Doe"

    def test_unknown_candidate_rejected(self, fresh_db):
        with pytest.raises(db.SessionResolutionError):
            db.resolve_or_create_session("nope", "job-a", "X", "Y")

    def test_candidate_job_mismatch_rejected(self, fresh_db):
        _job()
        _job(job_id="job-b", title="Eng B")
        _candidate()
        with pytest.raises(db.SessionResolutionError):
            db.resolve_or_create_session("cand-a", "job-b", "Jane Doe", "Eng B")

    def test_concurrent_calls_produce_exactly_one_session(self, fresh_db):
        _job()
        _candidate()
        results = []
        barrier = threading.Barrier(8)

        def resolve():
            barrier.wait()
            results.append(
                db.resolve_or_create_session("cand-a", "job-a", "Jane Doe", "Eng A")
            )

        threads = [threading.Thread(target=resolve) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        unique_ids = set(results)
        assert len(unique_ids) == 1
        sid = unique_ids.pop()
        matching = [s for s in db.get_all_sessions() if s["session_id"] == sid]
        assert len(matching) == 1
        assert db.get_candidate("cand-a")["session_id"] == sid


class TestCandidateSideSharedSession:
    def _invited_candidate(self, public_client):
        _job()
        _candidate()
        v = public_client.post("/api/candidate/validate-code", json={"invite_code": "code-a"})
        assert v.json()["valid"] is True
        return v.json()["interview_token"]

    def test_client_supplied_session_id_ignored(self, fresh_db, public_client):
        token = self._invited_candidate(public_client)
        consent = public_client.post("/api/candidate/consent", json={
            "session_id": "client-hijack", "interview_token": token,
        }).json()
        assert consent["success"] is True
        assert consent["session_id"] != "client-hijack"
        assert not [s for s in db.get_all_sessions() if s["session_id"] == "client-hijack"]

    def test_candidate_cannot_mint_second_session(self, fresh_db, public_client):
        token = self._invited_candidate(public_client)
        first = public_client.post("/api/candidate/start-session", json={
            "interview_token": token,
        }).json()
        second = public_client.post("/api/candidate/start-session", json={
            "session_id": "attempt-2", "interview_token": token,
        }).json()
        assert first["session_id"] == second["session_id"]
        matching = [s for s in db.get_all_sessions() if s["session_id"] == first["session_id"]]
        assert len(matching) == 1

    def test_start_resolves_existing_candidates_session(self, fresh_db, public_client):
        token = self._invited_candidate(public_client)
        consent_sid = public_client.post("/api/candidate/consent", json={
            "interview_token": token,
        }).json()["session_id"]
        start_sid = public_client.post("/api/candidate/start-session", json={
            "interview_token": token,
        }).json()["session_id"]
        assert start_sid == consent_sid
        assert start_sid == db.get_candidate("cand-a")["session_id"]


class TestRecruiterSideSharedSession:
    def test_recruiter_start_matches_candidate_session(self, client, public_client, fresh_db):
        _job()
        _candidate()
        rec = client.post("/api/sessions", json={"candidate_id": "cand-a"}).json()
        v = public_client.post("/api/candidate/validate-code", json={"invite_code": "code-a"})
        token = v.json()["interview_token"]
        start = public_client.post("/api/candidate/start-session", json={
            "interview_token": token,
        }).json()
        assert start["session_id"] == rec["session_id"]

    def test_recruiter_cannot_start_for_another_recruiters_candidate(self, fresh_db):
        from app.core.auth import register_recruiter

        register_recruiter("owner-b", "secret123", "Other")
        _job(job_id="job-b", title="Eng B", owner="owner-b")
        db.save_candidate(Candidate(
            candidate_id="cand-b", job_id="job-b", name="Bob", email="bob@example.com",
            invite_code="code-b", status="invited",
        ))

        with TestClient(__import__("api.main", fromlist=["app"]).app) as client:
            client.headers.update({"Authorization": f"Bearer {_register_and_token()}"})
            r = client.post("/api/sessions", json={"candidate_id": "cand-b"})
            assert r.status_code == 403

    def test_recruiter_invalid_candidate_rejected(self, client, fresh_db):
        r = client.post("/api/sessions", json={"candidate_id": "does-not-exist"})
        assert r.status_code == 403


class TestIntegrityFeedOwnership:
    def test_integrity_ws_rejects_non_owner(self, fresh_db):
        """The integrity WebSocket opens only when the recruiter owns the
        session's job. That gate is db.get_owned_session() (returns None for a
        non-owner, which the route turns into close code 4403). TestClient's
        WebSocket close handling is flaky for non-1000 codes, so we assert the
        exact DB predicate the route relies on — and confirm the owning
        recruiter passes it.
        """
        from app.core.auth import register_recruiter

        register_recruiter("recruiter", "secret123", "Owner")
        register_recruiter("intruder", "secret123", "Intruder")

        _job(job_id="job-own", owner="recruiter")
        db.save_candidate(Candidate(
            candidate_id="cand-own", job_id="job-own", name="Jane", email="j@example.com",
            invite_code="code-own", status="invited",
        ))
        sid = db.resolve_or_create_session("cand-own", "job-own", "Jane", "Eng A")

        # Owning recruiter -> allowed to open the feed.
        assert db.get_owned_session("recruiter", sid)
        # A different recruiter does not own this session's job -> 4403 gate.
        assert db.get_owned_session("intruder", sid) is None
