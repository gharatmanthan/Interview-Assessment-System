import io

from app.core import db
from app.core.models import (
    Candidate,
    CompetencyScore,
    InterviewSession,
    JobPosting,
)


def register_and_login(client):
    client.post("/api/auth/register", json={
        "username": "alice", "password": "secret123", "full_name": "Alice",
    })
    return client.post("/api/auth/login", json={"username": "alice", "password": "secret123"})


def create_job(client, job_id="job-1", title="Backend Engineer", **overrides):
    payload = {
        "job_id": job_id,
        "title": title,
        "description": overrides.get("description", "Build APIs with Python and SQL."),
        "required_skills": overrides.get("required_skills", ["Python", "SQL"]),
        "experience_level": "Junior",
        "department": "Engineering",
    }
    payload.update(overrides)
    return client.post("/api/jobs", json=payload)


def create_candidate(client, candidate_id="cand-1", job_id="job-1"):
    return client.post("/api/candidates", json={
        "candidate_id": candidate_id,
        "job_id": job_id,
        "name": "Jane Doe",
        "email": "jane@example.com",
    })


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestAuthApi:
    def test_register_then_login(self, client):
        registered = client.post("/api/auth/register", json={
            "username": "alice", "password": "secret123", "full_name": "Alice",
        })
        assert registered.status_code == 200
        assert registered.json()["success"] is True

        login = register_and_login(client)
        assert login.status_code == 200
        body = login.json()
        assert body["success"] is True
        assert body["username"] == "alice"

    def test_login_wrong_password(self, client):
        client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "nope"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["username"] is None

    def test_register_short_password_rejected(self, client):
        resp = client.post("/api/auth/register", json={"username": "bob", "password": "abc"})
        assert resp.json()["success"] is False


class TestJobsApi:
    def test_create_list_update_delete_cycle(self, client):
        created = create_job(client)
        assert created.status_code == 200
        assert created.json()["title"] == "Backend Engineer"

        listed = client.get("/api/jobs").json()
        assert [j["job_id"] for j in listed] == ["job-1"]
        assert listed[0]["required_skills"] == ["Python", "SQL"]
        assert listed[0]["adaptive_difficulty"] is True

        updated = client.put("/api/jobs/job-1", json={
            "job_id": "ignored-on-update",
            "title": "Senior Backend Engineer",
            "description": "Deep systems work.",
            "required_skills": ["Python", "Go"],
            "experience_level": "Senior",
            "department": "Platform",
        })
        assert updated.status_code == 200

        listed = client.get("/api/jobs").json()
        assert listed[0]["title"] == "Senior Backend Engineer"
        assert listed[0]["experience_level"] == "Senior"

        deleted = client.delete("/api/jobs/job-1")
        assert deleted.json() == {"success": True}
        assert client.get("/api/jobs").json() == []


class TestCandidatesApi:
    def test_create_assigns_invite_code_and_lists(self, client):
        created = create_candidate(client)
        assert created.status_code == 200
        code = created.json()["invite_code"]
        assert len(code) > 0

        listed = client.get("/api/candidates").json()
        assert listed[0]["invite_code"] == code
        assert listed[0]["status"] == "invited"

    def test_list_candidates_for_job_filter(self, client):
        create_job(client)
        create_job(client, job_id="job-2", title="Other Role")
        create_candidate(client, candidate_id="cand-1", job_id="job-1")
        create_candidate(client, candidate_id="cand-2", job_id="job-2")

        rows = client.get("/api/candidates/job/job-2").json()
        assert [r["candidate_id"] for r in rows] == ["cand-2"]

    def test_resend_invite_rotates_code(self, client):
        original = create_candidate(client).json()["invite_code"]

        resent = client.post("/api/candidates/cand-1/resend")
        assert resent.status_code == 200
        new_code = resent.json()["invite_code"]
        assert new_code != original

        stored = db.get_candidate_by_invite_code(new_code)
        assert stored["status"] == "invited"

    def test_delete_candidate(self, client):
        create_candidate(client)
        client.delete("/api/candidates/cand-1")
        assert client.get("/api/candidates").json() == []

    def test_upload_resume_parses_and_matches_against_job(self, client):
        create_job(client, description="We need python and sql skills; kubernetes a plus.")
        create_candidate(client)

        resume_bytes = b"Jane Doe\nSkills: Python, SQL\n3+ years of experience\n"
        resp = client.post(
            "/api/candidates/cand-1/resume",
            files={"file": ("resume.txt", io.BytesIO(resume_bytes), "text/plain")},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert set(body["resume_skills"]) == {"python", "sql"}
        assert body["experience_years"] == 3.0
        assert body["matched_skills"] == ["python", "sql"]
        assert body["missing_skills"] == ["kubernetes"]
        assert body["match_score"] == round(2 / 3 * 100, 1)

        stored = db.get_all_candidates()[0]
        assert stored["match_score"] == round(2 / 3 * 100, 1)


class TestCandidateFlowApi:
    def seed_invited_candidate(self, client):
        create_job(client)
        return create_candidate(client).json()["invite_code"]

    def test_validate_code_rejects_unknown_and_empty(self, client):
        resp = client.post("/api/candidate/validate-code", json={"invite_code": ""})
        assert resp.json()["valid"] is False

        resp = client.post("/api/candidate/validate-code", json={"invite_code": "BOGUS"})
        assert resp.json() == {"valid": False, "message": "Invalid invite code"}

    def test_validate_code_accepts_fresh_invite(self, client):
        code = self.seed_invited_candidate(client)

        resp = client.post("/api/candidate/validate-code", json={"invite_code": code})
        body = resp.json()
        assert body["valid"] is True
        assert body["candidate"]["name"] == "Jane Doe"
        assert body["job"]["title"] == "Backend Engineer"

    def test_validate_code_rejects_completed_and_expired(self, client):
        code = self.seed_invited_candidate(client)

        db.update_candidate_status("cand-1", "completed")
        resp = client.post("/api/candidate/validate-code", json={"invite_code": code})
        assert resp.json()["valid"] is False

        db.update_candidate_status("cand-1", "expired")
        resp = client.post("/api/candidate/validate-code", json={"invite_code": code})
        assert resp.json()["valid"] is False

    def test_consent_requires_fields_then_marks_in_progress(self, client):
        self.seed_invited_candidate(client)

        missing = client.post("/api/candidate/consent", json={"session_id": "s1"})
        assert missing.json() == {"success": False, "message": "Missing required fields"}

        ok = client.post("/api/candidate/consent", json={
            "session_id": "s1", "candidate_id": "cand-1",
        })
        assert ok.json() == {"success": True}
        assert db.get_all_candidates()[0]["status"] == "in_progress"

    def test_start_session_resolves_names_and_links_candidate(self, client):
        self.seed_invited_candidate(client)

        resp = client.post("/api/candidate/start-session", json={
            "session_id": "sess-1", "candidate_id": "cand-1", "job_id": "job-1",
        })
        body = resp.json()
        assert body["candidate_name"] == "Jane Doe"
        assert body["job_title"] == "Backend Engineer"
        assert body["status"] == "in_progress"

        candidate = db.get_all_candidates()[0]
        assert candidate["status"] == "in_progress"
        assert candidate["session_id"] == "sess-1"

    def test_submit_answer_scores_explains_and_persists(self, client):
        transcript = (
            "I would discuss time complexity first, then handle edge cases "
            "before describing the optimal approach with a concrete example."
        )
        resp = client.post("/api/candidate/submit-answer", json={
            "session_id": "sess-1",
            "question_id": "q1",
            "category": "dsa",
            "transcript": transcript,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert 0 <= body["score"]["score"] <= 100
        assert "No LLM key is configured" in body["explanation"]["summary"]
        assert body["fairness"]["score_delta"] == 0.0

        assert len(db.get_session_scores("sess-1")) == 1
        assert len(db.get_session_explanations("sess-1")) == 1
        assert len(db.get_all_fairness_flags()) == 1

    def test_complete_session_marks_session_and_candidate_done(self, client):
        self.seed_invited_candidate(client)
        client.post("/api/candidate/start-session", json={
            "session_id": "sess-1", "candidate_id": "cand-1", "job_id": "job-1",
        })

        missing = client.post("/api/candidate/complete-session", json={})
        assert missing.json() == {"success": False, "message": "Missing session_id"}

        done = client.post("/api/candidate/complete-session", json={"session_id": "sess-1"})
        assert done.json() == {"success": True}

        session = db.get_all_sessions()[0]
        assert session["status"] == "completed"
        assert session["completed_at"] is not None
        assert db.get_all_candidates()[0]["status"] == "completed"


class TestSessionsAndScoringApi:
    def test_create_and_list_sessions(self, client):
        client.post("/api/sessions", json={
            "session_id": "sess-1", "candidate_name": "Jane", "job_title": "BE",
        })
        rows = client.get("/api/sessions").json()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess-1"
        assert rows[0]["status"] == "in_progress"

    def test_scoring_run_persists_all_three_outputs(self, client):
        transcript = (
            "The optimal approach uses a hash map; time complexity is linear "
            "and I covered edge cases like empty input."
        )
        resp = client.post("/api/scoring/run", json={
            "session_id": "sess-1",
            "question_id": "q1",
            "category": "dsa",
            "transcript": transcript,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert 0 <= body["score"]["score"] <= 100
        assert body["fairness"]["note"] != ""

        assert len(db.get_session_scores("sess-1")) == 1
        assert len(db.get_session_explanations("sess-1")) == 1
        assert len(db.get_all_fairness_flags()) == 1


class TestReportsApi:
    def seed_two_scored_sessions(self, client):
        db.save_job_posting(JobPosting(
            job_id="job-1", title="Backend Engineer", description="d",
            required_skills=["Python"], experience_level="Junior", department="Eng",
        ))
        for sess_id, name, score in [("s-low", "Ann", 40.0), ("s-high", "Bob", 80.0)]:
            db.save_session(InterviewSession(
                session_id=sess_id, candidate_name=name,
                job_title="Backend Engineer", job_id="job-1",
            ))
            db.save_competency_score(CompetencyScore(
                session_id=sess_id, question_id="q1", category="DSA", score=score,
            ))

    def test_dashboard_stats_counts_everything(self, client):
        self.seed_two_scored_sessions(client)
        db.save_candidate(Candidate(
            candidate_id="c1", job_id="job-1", name="A", email="a@x.com",
            invite_code="C1", status="invited",
        ))

        stats = client.get("/api/reports/dashboard").json()

        assert stats["interviews_conducted"] == 2
        assert stats["avg_explainability_score"] == 60.0
        assert stats["candidates_by_status"]["invited"] == 1

    def test_candidate_report_averages_scores(self, client):
        self.seed_two_scored_sessions(client)

        report = client.get("/api/reports/candidate/s-high").json()

        assert report["overall_score"] == 80.0
        assert report["session"]["session_id"] == "s-high"
        assert len(report["scores"]) == 1

    def test_compare_ranks_descending_and_filters_by_job(self, client):
        self.seed_two_scored_sessions(client)

        rows = client.get("/api/reports/compare").json()
        assert [r["session_id"] for r in rows] == ["s-high", "s-low"]

        filtered = client.get("/api/reports/compare", params={"job_id": "job-1"}).json()
        assert [r["session_id"] for r in filtered] == ["s-high", "s-low"]

        empty = client.get("/api/reports/compare", params={"job_id": "missing"}).json()
        assert empty == []

    def test_export_csv_streams_rows(self, client):
        self.seed_two_scored_sessions(client)

        resp = client.get("/api/reports/export/csv")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]

        lines = resp.text.strip().splitlines()
        assert lines[0] == "Candidate,Job Title,Overall Score,DSA"
        assert lines[1] == "Bob,Backend Engineer,80.0,80.0"
        assert lines[2] == "Ann,Backend Engineer,40.0,40.0"


class TestSettingsApi:
    def test_defaults_before_any_update(self, client):
        settings = client.get("/api/settings").json()
        assert settings["camera_index"] == 0
        assert settings["llm_provider"] == "Groq"
        assert settings["llm_api_key"] == ""

    def test_partial_update_merges_with_existing(self, client):
        resp = client.put("/api/settings", json={"camera_index": 2})
        assert resp.status_code == 200
        assert resp.json()["camera_index"] == 2

        settings = client.get("/api/settings").json()
        assert settings["camera_index"] == 2
        assert settings["llm_provider"] == "Groq"


class TestDevicesApi:
    def test_returns_list_without_crashing(self, client):
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
