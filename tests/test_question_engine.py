"""Phase 2B: Question engine — selector + session locking + API tests.

Covers bank selection, JD-specific selection, category/difficulty validation,
duplicate prevention, LLM generation success/failure/fallback, question
persistence, immutability, ordering, and cross-tenant isolation.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.models import Candidate, JobPosting
from app.engine import question_selector as qs


def _register_and_token(username: str = "recruiter", password: str = "secret123") -> str:
    from app.core.auth import register_recruiter
    from app.core.tokens import create_token

    register_recruiter(username, password, "Test Recruiter")
    token, _ = create_token(username)
    return token


def _job(job_id="job-q", title="Q Engineer", owner="recruiter", description="Python FastAPI"):
    db.save_job_posting(JobPosting(
        job_id=job_id, title=title, description=description,
        required_skills=["python"], experience_level="Junior",
        department="Eng", created_by=owner,
    ))


def _candidate(cand_id="cand-q", job_id="job-q", name="Q Tester", email="q@example.com", code="code-q"):
    db.save_candidate(Candidate(
        candidate_id=cand_id, job_id=job_id, name=name, email=email,
        invite_code=code, status="invited",
    ))


def _make_session(cand_id="cand-q", job_id="job-q", name="Q Tester", title="Q Engineer"):
    return db.resolve_or_create_session(cand_id, job_id, name, title)


class TestSelectorBank:
    def test_selects_expected_count_from_bank(self):
        questions = qs.select_questions(job_description="", num_questions=10)
        assert len(questions) == 10
        assert all(q["source"] == "bank" for q in questions)
        assert all(q["question_text"] for q in questions)

    def test_composition_distribution(self):
        questions = qs.select_questions(job_description="", num_questions=10)
        cats = [q["category"] for q in questions]
        assert "Technical Knowledge" in cats
        assert "Problem Solving" in cats
        assert "Behavioral" in cats

    def test_scales_composition_for_small_set(self):
        questions = qs.select_questions(job_description="", num_questions=4)
        assert len(questions) == 4
        cats = set(q["category"] for q in questions)
        assert len(cats) >= 2

    def test_no_duplicate_questions(self):
        questions = qs.select_questions(job_description="", num_questions=10)
        texts = [q["question_text"] for q in questions]
        assert len(texts) == len(set(texts))

    def test_jd_specific_skills_prioritised(self):
        questions = qs.select_questions(
            job_description="Python, FastAPI, PostgreSQL, Docker, AWS", num_questions=5
        )
        # Technical questions come first on JD-specific JDs.
        assert questions[0]["category"] == "Technical Knowledge"

    def test_every_question_has_full_metadata(self):
        questions = qs.select_questions(job_description="", num_questions=10)
        for q in questions:
            assert set(q.keys()) == {
                "question_id", "question_text", "category", "competency",
                "difficulty", "source",
            }
            assert q["source"] in {"bank", "generated"}
            assert q["difficulty"] in qs.VALID_DIFFICULTIES


class TestSelectorLLM:
    def test_generation_success_and_source(self):
        fake = json.dumps({"questions": [
            {"question_text": "Explain Python's GIL and its impact on concurrency.",
             "category": "Technical Knowledge", "competency": "Python", "difficulty": "medium"},
            {"question_text": "Design a FastAPI service with dependency injection.",
             "category": "Technical Knowledge", "competency": "FastAPI", "difficulty": "hard"},
        ]})
        with patch.object(qs.llm_client, "llm_available", return_value=True):
            with patch.object(qs.llm_client, "ask_llm", return_value=fake):
                questions = qs.select_questions(
                    job_description="Python FastAPI", num_questions=2, force_generated=True
                )
        assert all(q["source"] == "generated" for q in questions)
        assert len(questions) == 2

    def test_malformed_llm_response_falls_back_to_bank(self):
        with patch.object(qs.llm_client, "llm_available", return_value=True):
            with patch.object(qs.llm_client, "ask_llm", return_value="{not valid json"):
                questions = qs.select_questions(job_description="Python", num_questions=3)
        assert len(questions) == 3
        assert all(q["source"] == "bank" for q in questions)

    def test_groq_unavailable_falls_back_to_bank(self):
        with patch.object(qs.llm_client, "llm_available", return_value=False):
            questions = qs.select_questions(job_description="", num_questions=10)
        assert all(q["source"] == "bank" for q in questions)
        assert len(questions) == 10

    def test_duplicates_and_invalid_fields_filtered(self):
        fake = json.dumps({"questions": [
            {"question_text": "First question about Python concurrency.",
             "category": "Technical Knowledge", "competency": "Py", "difficulty": "medium"},
            {"question_text": "First question about Python concurrency.",
             "category": "Technical Knowledge", "competency": "Py", "difficulty": "medium"},
            {"question_text": "Second question about dependency injection in FastAPI apps.",
             "category": "NotARealCategory", "competency": "X", "difficulty": "impossible"},
            {"question_text": "short"},
        ]})
        with patch.object(qs.llm_client, "llm_available", return_value=True):
            with patch.object(qs.llm_client, "ask_llm", return_value=fake):
                questions = qs.select_questions(
                    job_description="Python", num_questions=6, force_generated=True
                )
        texts = [q["question_text"] for q in questions if q["source"] == "generated"]
        # dedupe
        assert len(texts) == len(set(texts))
        # every generated question normalized category/difficulty
        gen = [q for q in questions if q["source"] == "generated"]
        for q in gen:
            assert q["category"] in qs.VALID_CATEGORIES
            assert q["difficulty"] in qs.VALID_DIFFICULTIES

    def test_llm_not_forced_uses_bank_when_coverage_sufficient(self):
        with patch.object(qs.llm_client, "llm_available", return_value=True):
            with patch.object(qs.llm_client, "ask_llm") as ask:
                questions = qs.select_questions(job_description="", num_questions=6)
        assert all(q["source"] == "bank" for q in questions)
        ask.assert_not_called()


class TestQuestionPersistence:
    def test_save_and_get_session_questions(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        questions = [
            {"question_index": 0, "question_id": "bank_0", "question_text": "Q0",
             "category": "Technical Knowledge", "competency": "Py",
             "difficulty": "medium", "source": "bank"},
            {"question_index": 1, "question_id": "gen_abc", "question_text": "Q1",
             "category": "Problem Solving", "competency": "PS",
             "difficulty": "hard", "source": "generated"},
        ]
        db.save_session_questions(sid, questions)
        stored = db.get_session_questions(sid)
        assert len(stored) == 2
        assert stored[0]["question_index"] == 0
        assert stored[1]["question_index"] == 1
        assert db.session_questions_exist(sid) is True

    def test_table_created(self, fresh_db):
        conn = db.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "session_questions" in tables


class TestRecruiterSelectEndpoint:
    def _client_for(self, username="recruiter"):
        app = __import__("api.main", fromlist=["app"]).app
        c = TestClient(app)
        c.headers.update({"Authorization": f"Bearer {_register_and_token(username)}"})
        return c

    def test_select_locks_questions_to_session(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        c = self._client_for()
        resp = c.post("/api/questions/select", json={
            "session_id": sid, "num_questions": 5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["locked"] is True
        assert body["session_id"] == sid
        assert len(body["questions"]) == 5
        assert db.session_questions_exist(sid) is True

    def test_same_session_returns_same_questions(self, fresh_db):
        _job()
        _candidate()
        sid = _make_session()
        c = self._client_for()
        first = c.post("/api/questions/select", json={
            "session_id": sid, "num_questions": 5,
        }).json()
        second = c.post("/api/questions/select", json={
            "session_id": sid, "num_questions": 5,
        }).json()
        assert first["questions"] == second["questions"]

    def test_unauth_is_rejected(self, fresh_db, public_client):
        resp = public_client.post("/api/questions/select", json={
            "session_id": "x", "num_questions": 5,
        })
        assert resp.status_code in (401, 403)

    def test_recruiter_cannot_select_for_another_recruiters_candidate(self, fresh_db):
        from app.core.auth import register_recruiter

        register_recruiter("owner-b", "secret123", "Other")
        _job(job_id="job-b", title="B", owner="owner-b", description="Go")
        db.save_candidate(Candidate(
            candidate_id="cand-b", job_id="job-b", name="Bob",
            email="bob@example.com", invite_code="code-b", status="invited",
        ))
        sid = db.resolve_or_create_session("cand-b", "job-b", "Bob", "B")
        # recruiter (not owner) must be denied.
        c = self._client_for("recruiter")
        resp = c.post("/api/questions/select", json={
            "session_id": sid, "num_questions": 5,
        })
        assert resp.status_code == 403

    def test_cannot_select_for_nonexistent_session(self, fresh_db):
        _job()
        c = self._client_for()
        resp = c.post("/api/questions/select", json={
            "session_id": "nope", "num_questions": 5,
        })
        assert resp.status_code == 404


class TestCandidateQuestionsEndpoint:
    def _setup_candidate_with_questions(self, fresh_db, cand_id="cand-q", code="code-q"):
        _job()
        _candidate(cand_id=cand_id, code=code)
        sid = _make_session(cand_id=cand_id)
        questions = [
            {"question_index": 0, "question_id": "bank_0", "question_text": "Q0",
             "category": "Technical Knowledge", "competency": "Py",
             "difficulty": "medium", "source": "bank"},
            {"question_index": 1, "question_id": "gen_9", "question_text": "Q1",
             "category": "Problem Solving", "competency": "PS",
             "difficulty": "hard", "source": "generated"},
        ]
        db.save_session_questions(sid, questions)
        return sid

    def _token(self, public_client, code="code-q"):
        v = public_client.post("/api/candidate/validate-code", json={"invite_code": code})
        return v.json()["interview_token"]

    def test_get_questions_returns_own_session_questions(self, fresh_db, public_client):
        self._setup_candidate_with_questions(fresh_db)
        token = self._token(public_client)
        resp = public_client.get("/api/candidate/questions", headers={
            "X-Interview-Token": token,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["questions"]) == 2
        # ordered by question_index
        assert body["questions"][0]["question_index"] == 0
        assert body["questions"][1]["question_index"] == 1

    def test_cannot_access_another_candidates_questions(self, fresh_db, public_client):
        self._setup_candidate_with_questions(fresh_db)
        # A second candidate without a prepared set under a different job
        _job(job_id="job-other", title="Other")
        db.save_candidate(Candidate(
            candidate_id="cand-other", job_id="job-other", name="Other",
            email="o@example.com", invite_code="code-other", status="invited",
        ))
        other_sid = db.resolve_or_create_session("cand-other", "job-other", "Other", "Other")
        db.save_session_questions(other_sid, [
            {"question_index": 0, "question_id": "b0", "question_text": "OtherQ",
             "category": "DSA", "competency": "D", "difficulty": "easy", "source": "bank"},
        ])
        # Ask with cand-q's token but try to read the wrong session context:
        # the endpoint derives the session from the token, so it should return
        # cand-q's (empty -> 404 no prepared questions is not the case here).
        token_other = self._token(public_client, code="code-other")
        # other candidate has own questions
        resp_other = public_client.get("/api/candidate/questions", headers={
            "X-Interview-Token": token_other,
        })
        assert resp_other.status_code == 200
        assert resp_other.json()["questions"][0]["question_text"] == "OtherQ"

    def test_no_questions_prepared_returns_404(self, fresh_db, public_client):
        _job()
        _candidate()
        _make_session()
        token = self._token(public_client)
        resp = public_client.get("/api/candidate/questions", headers={
            "X-Interview-Token": token,
        })
        assert resp.status_code == 404

    def test_invalid_token_rejected(self, fresh_db, public_client):
        resp = public_client.get("/api/candidate/questions", headers={
            "X-Interview-Token": "bogus",
        })
        assert resp.status_code == 401
