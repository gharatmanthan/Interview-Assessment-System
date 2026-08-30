from datetime import datetime

from app.core.models import (
    Candidate,
    CompetencyScore,
    ExplanationItem,
    FairnessFlag,
    IntegrityFlag,
    InterviewSession,
    JobPosting,
    RecruiterUser,
)


def make_job(job_id="job-1", title="Backend Engineer"):
    return JobPosting(
        job_id=job_id,
        title=title,
        description="Builds APIs with Python and SQL.",
        required_skills=["Python", "SQL"],
        experience_level="Junior",
        department="Engineering",
    )


def make_candidate(candidate_id="cand-1", job_id="job-1", invite_code="CODE123"):
    return Candidate(
        candidate_id=candidate_id,
        job_id=job_id,
        name="Jane Doe",
        email=f"{candidate_id}@example.com",
        invite_code=invite_code,
    )


def test_init_db_creates_all_tables(fresh_db):
    conn = fresh_db.get_connection()
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    expected = {
        "recruiter_users",
        "candidates",
        "job_postings",
        "sessions",
        "integrity_flags",
        "competency_scores",
        "explanations",
        "fairness_flags",
        "candidate_accounts",
        "live_interviews",
    }
    assert expected.issubset(tables)


def test_recruiter_user_round_trip(fresh_db):
    user = RecruiterUser(username="alice", password_hash="salt$abc", full_name="Alice A")
    fresh_db.save_recruiter_user(user)

    loaded = fresh_db.get_recruiter_user("alice")
    assert loaded["username"] == "alice"
    assert loaded["password_hash"] == "salt$abc"
    assert loaded["full_name"] == "Alice A"

    assert fresh_db.get_recruiter_user("nobody") is None


def test_candidate_round_trip_decodes_skill_lists(fresh_db):
    candidate = make_candidate()
    candidate.resume_skills = ["Python", "SQL"]
    candidate.matched_skills = ["Python"]
    candidate.missing_skills = ["Docker"]
    candidate.match_score = 50.0
    candidate.experience_years = 3.0
    fresh_db.save_candidate(candidate)

    loaded = fresh_db.get_candidate_by_invite_code("CODE123")
    assert loaded["name"] == "Jane Doe"
    assert loaded["resume_skills"] == ["Python", "SQL"]
    assert loaded["matched_skills"] == ["Python"]
    assert loaded["missing_skills"] == ["Docker"]
    assert loaded["match_score"] == 50.0
    assert loaded["experience_years"] == 3.0
    assert loaded["status"] == "invited"


def test_get_candidates_for_job_orders_by_invited_at_desc(fresh_db):
    first = make_candidate(candidate_id="cand-1", invite_code="A")
    second = make_candidate(candidate_id="cand-2", invite_code="B")
    second.invited_at = datetime(2030, 1, 1)
    fresh_db.save_candidate(first)
    fresh_db.save_candidate(second)

    rows = fresh_db.get_candidates_for_job("job-1")
    assert [r["candidate_id"] for r in rows] == ["cand-2", "cand-1"]
    assert fresh_db.get_candidates_for_job("other-job") == []


def test_get_all_candidates_joins_job_title(fresh_db):
    fresh_db.save_job_posting(make_job())
    fresh_db.save_candidate(make_candidate())

    rows = fresh_db.get_all_candidates()
    assert len(rows) == 1
    assert rows[0]["job_title"] == "Backend Engineer"


def test_update_candidate_status_with_and_without_session(fresh_db):
    fresh_db.save_candidate(make_candidate())

    fresh_db.update_candidate_status("cand-1", "in_progress", session_id="sess-9")
    row = fresh_db.get_candidate_by_invite_code("CODE123")
    assert row["status"] == "in_progress"
    assert row["session_id"] == "sess-9"

    fresh_db.update_candidate_status("cand-1", "completed")
    row = fresh_db.get_candidate_by_invite_code("CODE123")
    assert row["status"] == "completed"
    assert row["session_id"] == "sess-9"


def test_regenerate_invite_code_resets_status_to_invited(fresh_db):
    candidate = make_candidate()
    candidate.status = "expired"
    fresh_db.save_candidate(candidate)

    fresh_db.regenerate_invite_code("cand-1", "NEWCODE")
    row = fresh_db.get_candidate_by_invite_code("NEWCODE")
    assert row is not None
    assert row["status"] == "invited"
    assert fresh_db.get_candidate_by_invite_code("CODE123") is None


def test_delete_candidate(fresh_db):
    fresh_db.save_candidate(make_candidate())
    fresh_db.delete_candidate("cand-1")
    assert fresh_db.get_candidate_by_invite_code("CODE123") is None


def test_save_candidate_resume_updates_resume_fields(fresh_db):
    fresh_db.save_candidate(make_candidate())

    fresh_db.save_candidate_resume(
        "cand-1",
        "/tmp/resume.pdf",
        ["Python"],
        4.0,
        75.0,
        ["Python"],
        ["Kubernetes"],
    )
    row = fresh_db.get_candidate_by_invite_code("CODE123")
    assert row["resume_path"] == "/tmp/resume.pdf"
    assert row["resume_skills"] == ["Python"]
    assert row["experience_years"] == 4.0
    assert row["match_score"] == 75.0
    assert row["matched_skills"] == ["Python"]
    assert row["missing_skills"] == ["Kubernetes"]


def test_job_posting_round_trip_converts_types(fresh_db):
    job = make_job()
    job.adaptive_difficulty = True
    job.competency_weights = {"dsa": 60, "communication": 40}
    fresh_db.save_job_posting(job)

    loaded = fresh_db.get_all_job_postings()[0]
    assert loaded["title"] == "Backend Engineer"
    assert loaded["required_skills"] == ["Python", "SQL"]
    assert loaded["competency_weights"] == {"dsa": 60, "communication": 40}
    assert loaded["adaptive_difficulty"] is True


def test_delete_job_posting(fresh_db):
    fresh_db.save_job_posting(make_job())
    fresh_db.delete_job_posting("job-1")
    assert fresh_db.get_all_job_postings() == []


def test_session_round_trip(fresh_db):
    session = InterviewSession(
        session_id="sess-1",
        candidate_name="Jane Doe",
        job_title="Backend Engineer",
        job_id="job-1",
    )
    fresh_db.save_session(session)

    rows = fresh_db.get_all_sessions()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-1"
    assert rows[0]["status"] == "in_progress"


def test_integrity_flag_join_includes_session_info(fresh_db):
    session = InterviewSession(session_id="sess-1", candidate_name="Jane", job_title="BE")
    fresh_db.save_session(session)
    flag = IntegrityFlag(
        session_id="sess-1",
        flag_type="vm_detected",
        detail="VirtualBox running",
        severity="high",
    )
    fresh_db.save_integrity_flag(flag)

    rows = fresh_db.get_all_integrity_flags()
    assert len(rows) == 1
    assert rows[0]["candidate_name"] == "Jane"
    assert rows[0]["job_title"] == "BE"
    assert rows[0]["flag_type"] == "vm_detected"
    assert rows[0]["severity"] == "high"


def test_competency_score_round_trip(fresh_db):
    score = CompetencyScore(
        session_id="sess-1", question_id="q1", category="DSA", score=82.5, confidence=0.7
    )
    fresh_db.save_competency_score(score)

    rows = fresh_db.get_session_scores("sess-1")
    assert rows == [
        {
            "id": 1,
            "session_id": "sess-1",
            "question_id": "q1",
            "category": "DSA",
            "score": 82.5,
            "confidence": 0.7,
        }
    ]
    assert fresh_db.get_session_scores("missing") == []


def test_explanation_round_trip_decodes_phrases(fresh_db):
    item = ExplanationItem(
        session_id="sess-1",
        question_id="q1",
        summary="Good depth.",
        supporting_phrases=["used memoization", "covered edge cases"],
    )
    fresh_db.save_explanation(item)

    rows = fresh_db.get_session_explanations("sess-1")
    assert rows[0]["summary"] == "Good depth."
    assert rows[0]["supporting_phrases"] == ["used memoization", "covered edge cases"]


def test_fairness_flag_join_includes_session_info(fresh_db):
    session = InterviewSession(session_id="sess-1", candidate_name="Jane", job_title="BE")
    fresh_db.save_session(session)
    flag = FairnessFlag(session_id="sess-1", question_id="q1", score_delta=-6.2, note="shift")
    fresh_db.save_fairness_flag(flag)

    rows = fresh_db.get_all_fairness_flags()
    assert len(rows) == 1
    assert rows[0]["score_delta"] == -6.2
    assert rows[0]["candidate_name"] == "Jane"


def test_duplicate_submit_upserts_competency_score(fresh_db):
    """Recruiters route /scoring/run and candidates /submit-answer can fire for
    the same (session, question) when a retry occurs. One row per
    (session_id, question_id) must be kept, not a growing pile of duplicates,
    and the latest score must win."""
    from app.core.models import CompetencyScore

    fresh_db.save_competency_score(CompetencyScore(
        session_id="sess-1", question_id="q1", category="DSA", score=60.0, confidence=0.5,
    ))
    fresh_db.save_competency_score(CompetencyScore(
        session_id="sess-1", question_id="q1", category="DSA", score=90.0, confidence=0.9,
    ))
    rows = fresh_db.get_session_scores("sess-1")
    assert len(rows) == 1
    assert rows[0]["score"] == 90.0


def test_duplicate_submit_upserts_explanation(fresh_db):
    from app.core.models import ExplanationItem

    fresh_db.save_explanation(ExplanationItem(
        session_id="sess-1", question_id="q1", summary="old", supporting_phrases=["a"],
    ))
    fresh_db.save_explanation(ExplanationItem(
        session_id="sess-1", question_id="q1", summary="new", supporting_phrases=["a", "b"],
    ))
    rows = fresh_db.get_session_explanations("sess-1")
    assert len(rows) == 1
    assert rows[0]["summary"] == "new"


def test_duplicate_submit_upserts_fairness_flag(fresh_db):
    from app.core.models import FairnessFlag

    fresh_db.save_fairness_flag(FairnessFlag(
        session_id="sess-1", question_id="q1", score_delta=0.0, note="old",
    ))
    fresh_db.save_fairness_flag(FairnessFlag(
        session_id="sess-1", question_id="q1", score_delta=-5.5, note="new",
    ))
    rows = [r for r in fresh_db.get_all_fairness_flags() if r["session_id"] == "sess-1"]
    assert len(rows) == 1
    assert rows[0]["score_delta"] == -5.5


# --- candidate accounts (teammate login flow) ---

def test_demo_candidate_account_seeded(fresh_db):
    account = fresh_db.authenticate_candidate("candidate01", "interview123")
    assert account == {"candidate_id": "candidate01", "full_name": "Demo Candidate"}


def test_authenticate_candidate_success_and_failure(fresh_db):
    fresh_db.save_candidate_account("cand-42", "s3cret!", "Jane Doe")

    assert fresh_db.authenticate_candidate("cand-42", "s3cret!") == {
        "candidate_id": "cand-42",
        "full_name": "Jane Doe",
    }
    assert fresh_db.authenticate_candidate("cand-42", "wrong") is None
    assert fresh_db.authenticate_candidate("nobody", "s3cret!") is None


def test_authenticate_candidate_rejects_corrupted_hash(fresh_db):
    conn = fresh_db.get_connection()
    conn.execute(
        "INSERT INTO candidate_accounts (candidate_id, password_hash, full_name) VALUES (?, ?, ?)",
        ("broken", "not-a-valid-hash", "Broken"),
    )
    conn.commit()
    conn.close()
    assert fresh_db.authenticate_candidate("broken", "anything") is None


# --- live interviews (recruiter Live Monitor sync) ---

def test_live_interview_round_trip(fresh_db):
    fresh_db.start_live_interview("sess-live-1", "cand-1", "Jane Doe", "What is REST?", 0)

    row = fresh_db.get_live_interview("sess-live-1")
    assert row["question"] == "What is REST?"
    assert row["status"] == "live"
    assert row["transcript"] == ""
    assert fresh_db.get_live_interviews()[0]["session_id"] == "sess-live-1"

    fresh_db.update_live_interview("sess-live-1", transcript="REST is...", question_index=1)
    row = fresh_db.get_live_interview("sess-live-1")
    assert row["transcript"] == "REST is..."
    assert row["question_index"] == 1

    fresh_db.update_live_interview("sess-live-1", status="completed")
    assert fresh_db.get_live_interviews() == []
    assert fresh_db.get_live_interview("sess-live-1")["status"] == "completed"


def test_update_live_interview_ignores_unknown_fields(fresh_db):
    fresh_db.start_live_interview("sess-live-1", "cand-1", "Jane Doe", "Q?", 0)
    fresh_db.update_live_interview("sess-live-1", evil_field="x", transcript="ok")
    assert fresh_db.get_live_interview("sess-live-1")["transcript"] == "ok"
    assert "evil_field" not in fresh_db.get_live_interview("sess-live-1")


def test_get_live_interview_missing_returns_none(fresh_db):
    assert fresh_db.get_live_interview("nope") is None


# --- active job postings + session partial update ---

def test_get_active_job_postings_filters_inactive(fresh_db):
    active = make_job(job_id="job-1", title="Active Role")
    inactive = make_job(job_id="job-2", title="Closed Role")
    fresh_db.save_job_posting(active)
    fresh_db.save_job_posting(inactive)
    fresh_db.set_job_posting_active("job-2", False)

    titles = [j["title"] for j in fresh_db.get_active_job_postings()]
    assert titles == ["Active Role"]
    # all-postings view still sees both
    assert len(fresh_db.get_all_job_postings()) == 2

    fresh_db.set_job_posting_active("job-2", True)
    assert {j["job_id"] for j in fresh_db.get_active_job_postings()} == {"job-1", "job-2"}


def test_update_session_partial_fields(fresh_db):
    session = InterviewSession(session_id="sess-1", candidate_name="Jane", job_title="BE")
    fresh_db.save_session(session)

    fresh_db.update_session("sess-1", transcript="spoken answer text")
    row = fresh_db.get_all_sessions()[0]
    assert row["transcript"] == "spoken answer text"
    assert row["status"] == "in_progress"

    fresh_db.update_session("sess-1", not_allowed="x")
    assert "not_allowed" not in fresh_db.get_all_sessions()[0]
