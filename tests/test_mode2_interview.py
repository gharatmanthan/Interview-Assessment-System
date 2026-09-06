"""Phase 3B: MODE 2 self-serve AI interview lifecycle.

Covers the complete recruiter-prepares -> candidate-answers-sequentially ->
scoring -> completed flow, server-authoritative progression, refresh recovery,
idempotent transcript/scoring persistence, STT retry, forged-completion
prevention, and cross-candidate/recruiter isolation.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import db
from app.core.models import Candidate, JobPosting

from api.main import app


def _client(bearer: str | None = None):
    c = TestClient(app)
    if bearer:
        c.headers.update({"Authorization": f"Bearer {bearer}"})
    return c


def _register_and_token(username: str = "recruiter", password: str = "secret123") -> str:
    from app.core.auth import register_recruiter
    from app.core.tokens import create_token

    register_recruiter(username, password, "Test Recruiter")
    token, _ = create_token(username)
    return token


def _job(job_id="job-m2", title="M2 Engineer", owner="recruiter", description="Python FastAPI SQL"):
    db.save_job_posting(JobPosting(
        job_id=job_id, title=title, description=description,
        required_skills=["python"], experience_level="Junior",
        department="Eng", created_by=owner,
    ))


def _candidate(cand_id="cand-m2", job_id="job-m2", name="M2 Tester", email="m2@example.com", code="code-m2"):
    db.save_candidate(Candidate(
        candidate_id=cand_id, job_id=job_id, name=name, email=email,
        invite_code=code, status="invited",
    ))


def _make_session(cand_id="cand-m2", job_id="job-m2", name="M2 Tester", title="M2 Engineer"):
    return db.resolve_or_create_session(cand_id, job_id, name, title)


def _prepare_questions(sid, count=3, prefix="m2_"):
    questions = [
        {"question_index": i, "question_id": f"{prefix}{i}", "question_text": f"Question {prefix}{i}",
         "category": "Technical Knowledge", "competency": "Py",
         "difficulty": "medium", "source": "bank"}
        for i in range(count)
    ]
    db.save_session_questions(sid, questions)
    return questions


def _candidate_token(cand_code="code-m2"):
    v = _client()
    return v.post("/api/candidate/validate-code", json={"invite_code": cand_code}).json()["interview_token"]


class TestMode2Lifecycle:
    def test_recruiter_prepares_locks_and_candidate_sees_exact_set(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        c = _client(_register_and_token())
        prepared = c.post("/api/questions/select", json={"session_id": sid, "num_questions": 3}).json()
        assert prepared["locked"] is True
        assert len(prepared["questions"]) == 3

        body = _client().get("/api/candidate/questions", headers={
            "X-Interview-Token": _candidate_token(),
        }).json()
        assert len(body["questions"]) == 3
        assert body["questions"][0]["question_index"] == 0

    def test_candidate_cannot_start_session_before_prepared(self, fresh_db):
        _job()
        _candidate()
        _make_session()
        resp = _client().get("/api/candidate/questions", headers={
            "X-Interview-Token": _candidate_token(),
        })
        assert resp.status_code == 404

    def test_first_question_is_current_and_ordered(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=3)
        prog = _client().get("/api/candidate/progress", headers={
            "X-Interview-Token": _candidate_token(),
        }).json()
        assert prog["interview_status"] == "ready"
        assert prog["total_questions"] == 3
        assert prog["answered_questions"] == 0
        assert prog["remaining_questions"] == 3
        assert prog["current_question"]["question_id"] == "m2_0"

    def test_answer_persists_transcript_and_score_derived_from_jd(self, fresh_db):
        _job(description="Python FastAPI PostgreSQL rigorous")
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=1)
        v = _client()
        token = _candidate_token()

        captured = {}

        def fake_retrieve(comp, cat, jd):
            captured["comp"] = comp
            captured["cat"] = cat
            captured["jd"] = jd
            return {"rubric": "JD-grounded", "category": cat}

        with patch("app.engine.rag.retrieve_rubric", side_effect=fake_retrieve):
            resp = v.post("/api/candidate/submit-answer", json={
                "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
                "transcript": "I would model the data with SQL and serve via FastAPI.",
                "interview_token": token,
            })
        assert resp.status_code == 200
        assert captured["comp"] == "M2 Engineer"
        assert "Python FastAPI PostgreSQL rigorous" in captured["jd"]

        transcripts = db.get_question_transcripts(sid)
        assert [t["transcript"] for t in transcripts if t["question_id"] == "m2_0"] == [
            "I would model the data with SQL and serve via FastAPI."
        ]
        scores = db.get_session_scores(sid)
        assert len(scores) == 1
        assert scores[0]["question_id"] == "m2_0"

    def test_progression_is_server_authoritative_and_advanced_after_score(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=3)
        v = _client()
        token = _candidate_token()

        def prog():
            return v.get("/api/candidate/progress", headers={"X-Interview-Token": token}).json()

        assert prog()["current_question"]["question_id"] == "m2_0"
        v.post("/api/candidate/submit-answer", json={
            "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
            "transcript": "A0", "interview_token": token,
        })
        p = prog()
        assert p["answered_questions"] == 1
        assert p["current_question"]["question_id"] == "m2_1"

    def test_refresh_recovery_returns_true_server_position(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=3)
        token = _candidate_token()
        _client().post("/api/candidate/submit-answer", json={
            "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
            "transcript": "A0", "interview_token": token,
        })
        p = _client().get("/api/candidate/progress", headers={"X-Interview-Token": token}).json()
        assert p["answered_questions"] == 1
        assert p["current_question"]["question_id"] == "m2_1"
        assert p["interview_status"] == "in_progress"

    def test_retry_does_not_duplicate_score_or_transcript(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=1)
        v = _client()
        token = _candidate_token()
        payload = {
            "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
            "transcript": "Robust answer", "interview_token": token,
        }
        assert v.post("/api/candidate/submit-answer", json=payload).status_code == 200
        assert v.post("/api/candidate/submit-answer", json=payload).status_code == 200
        assert len(db.get_session_scores(sid)) == 1
        assert len(db.get_session_explanations(sid)) == 1
        assert len(db.get_question_transcripts(sid)) == 1

    def test_cannot_submit_another_sessions_question(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=1)
        _job(job_id="job-other", title="Other", owner="recruiter", description="Go")
        db.save_candidate(Candidate(
            candidate_id="cand-other", job_id="job-other", name="Other",
            email="o@x.com", invite_code="code-other", status="invited",
        ))
        other_sid = db.resolve_or_create_session("cand-other", "job-other", "Other", "Other")
        _prepare_questions(other_sid, count=1, prefix="o_")

        v = _client()
        token = _candidate_token()
        other_q = db.get_session_questions(other_sid)[0]["question_id"]
        resp = v.post("/api/candidate/submit-answer", json={
            "session_id": sid, "question_id": other_q, "category": "Technical Knowledge",
            "transcript": "wrong", "interview_token": token,
        })
        assert resp.status_code == 403
        assert len(db.get_session_scores(sid)) == 0

    def test_candidate_cannot_modify_locked_questions(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=2)
        read_client = _client()
        token = _candidate_token()

        # Candidate sees exactly the recruiter's locked set.
        seen = read_client.get("/api/candidate/questions", headers={
            "X-Interview-Token": token,
        }).json()["questions"]
        assert len(seen) == 2

        # Answering (the only write a candidate ever performs) never mutates the
        # locked question set — no candidate endpoint can add/replace questions.
        read_client.post("/api/candidate/submit-answer", json={
            "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
            "transcript": "A0", "interview_token": token,
        })
        locked = db.get_session_questions(sid)
        assert len(locked) == 2
        assert locked[0]["question_text"].startswith("Question ")
        # The same locked set is still served verbatim.
        again = read_client.get("/api/candidate/questions", headers={
            "X-Interview-Token": token,
        }).json()["questions"]
        assert [q["question_text"] for q in again] == [q["question_text"] for q in seen]

    def test_final_question_completes_session(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=2)
        v = _client()
        token = _candidate_token()

        for qi in (0, 1):
            v.post("/api/candidate/submit-answer", json={
                "session_id": sid, "question_id": f"m2_{qi}", "category": "Technical Knowledge",
                "transcript": f"A{qi}", "interview_token": token,
            })

        done = v.post("/api/candidate/complete-session", json={
            "session_id": sid, "interview_token": token,
        })
        assert done.json() == {"success": True}
        assert db.get_session(sid)["status"] == "completed"
        assert db.get_candidate("cand-m2")["status"] == "completed"

    def test_cannot_forge_completion_with_unanswered_questions(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=3)
        v = _client()
        token = _candidate_token()
        v.post("/api/candidate/submit-answer", json={
            "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
            "transcript": "A0", "interview_token": token,
        })
        resp = v.post("/api/candidate/complete-session", json={
            "session_id": sid, "interview_token": token,
        })
        assert resp.status_code == 409
        assert db.get_session(sid)["status"] != "completed"


class TestMode2RecruiterStatus:
    def test_recruiter_sees_server_status_and_question_set_summary(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        _prepare_questions(sid, count=3)
        c = _client(_register_and_token())

        body = c.get("/api/candidates/cand-m2/interview-status").json()
        assert body["interview_status"] == "ready"
        assert body["locked"] is True
        assert body["total_questions"] == 3
        assert body["answered_questions"] == 0
        assert "Technical Knowledge" in body["categories"]

        v = _client()
        token = _candidate_token()
        v.post("/api/candidate/submit-answer", json={
            "session_id": sid, "question_id": "m2_0", "category": "Technical Knowledge",
            "transcript": "A0", "interview_token": token,
        })
        body = c.get("/api/candidates/cand-m2/interview-status").json()
        assert body["interview_status"] == "in_progress"
        assert body["answered_questions"] == 1

        for qi in (1, 2):
            v.post("/api/candidate/submit-answer", json={
                "session_id": sid, "question_id": f"m2_{qi}", "category": "Technical Knowledge",
                "transcript": f"A{qi}", "interview_token": token,
            })
        v.post("/api/candidate/complete-session", json={"session_id": sid, "interview_token": token})
        body = c.get("/api/candidates/cand-m2/interview-status").json()
        assert body["interview_status"] == "completed"

    def test_recruiter_cannot_access_other_recruiters_candidate(self, fresh_db):
        _job(owner="owner-a")
        _candidate()
        _make_session()
        _prepare_questions(db.get_candidate("cand-m2")["session_id"], count=1)
        c = _client(_register_and_token("owner-b"))
        resp = c.get("/api/candidates/cand-m2/interview-status")
        assert resp.status_code == 403

    def test_recruiter_sees_not_ready_for_unprepared_candidate(self, fresh_db):
        _job()
        _candidate()
        _make_session()
        c = _client(_register_and_token())
        body = c.get("/api/candidates/cand-m2/interview-status").json()
        assert body["interview_status"] == "not_ready"
        assert body["locked"] is False
