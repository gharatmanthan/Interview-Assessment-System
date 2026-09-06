"""Screening service + scoring + rules tests (candidate-first pipeline)."""
import pytest


@pytest.fixture
def make_job(fresh_db):
    from app.core.models import JobPosting

    def _make(**overrides):
        fields = dict(
            job_id="job-screen-1",
            title="Backend Engineer",
            description="Build REST services using python and sql.",
            required_skills=["python", "sql"],
            experience_level="Mid",
            department="Engineering",
            screening_threshold=50.0,
            minimum_experience_years=3,
            auto_invite_enabled=True,
            screening_enabled=True,
        )
        fields.update(overrides)
        if "required_education" in overrides and overrides["required_education"] is None:
            fields["required_education"] = ""
        elif "required_education" not in overrides:
            fields["required_education"] = ""
        job = JobPosting(**fields)
        fresh_db.save_job_posting(job)
        return fresh_db.get_job_posting(job.job_id)

    return _make


@pytest.fixture
def resume_txt(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text(
        "Backend engineer with python, sql and rest api experience. "
        "5 years of experience. B.Tech in Computer Science.",
        encoding="utf-8",
    )
    return str(path)


def _apply(db, job, resume_path, email="cand@example.com"):
    from app.screening.service import create_application_and_queue
    return create_application_and_queue(
        job=job, full_name="Ada Lovelace", email=email, phone="+1", resume_path=resume_path,
    )


# --- scoring: weights + redistribution ---

def test_component_scores_weighted(fresh_db):
    from app.screening.scoring import component_scores
    resume = {"skills": ["python", "sql"], "experience_years": 5.0, "education": ["B.Tech"]}
    job = {
        "required_skills": ["python", "sql"],
        "minimum_experience_years": 3.0,
        "required_education": "",
        "screening_weights": {"skills": 50, "experience": 25, "semantic": 25, "education": 10, "keyword": 10},
    }
    match = {"match_score": 100.0, "matched_skills": ["python", "sql"], "missing_skills": [], "matched_by": "keyword_overlap"}
    scored = component_scores(resume, job, match)
    assert scored["overall"] == 100.0
    assert scored["components"]["skills"]["value"] == 100.0
    assert scored["components"]["experience"]["value"] == 100.0


def test_component_scores_redistributes_na(fresh_db):
    """N/A criteria drop their weight; overall stays on 0-100 scale."""
    from app.screening.scoring import component_scores
    resume = {"skills": ["python"], "experience_years": None, "education": []}
    job = {
        "required_skills": ["python", "sql"],
        "minimum_experience_years": None,  # N/A experience
        "required_education": "",
        "screening_weights": {"skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10},
    }
    match = {"match_score": 50.0, "matched_skills": ["python", "sql"], "missing_skills": ["sql"], "matched_by": "keyword_overlap"}
    scored = component_scores(resume, job, match)
    assert scored["components"]["experience"]["value"] is None
    assert scored["overall"] is not None
    # skills 100 * (40/90 norm), keyword 50*... -> between 0-100
    assert 0.0 <= scored["overall"] <= 100.0


# --- hard requirements + decision engine ---

def test_hard_requirement_experience_gate():
    from app.screening.rules import eval_hard_requirements, decide
    job = {"minimum_experience_years": 5, "required_education": ""}
    r = eval_hard_requirements({"experience_years": 3.0, "education": []}, job)
    assert r["passed"] is False
    assert any("experience" in f for f in r["failures"])
    decision, reason = decide(90.0, r["passed"], 60.0)
    assert decision == "rejected"
    assert "hard" in reason


def test_decision_thresholds():
    from app.screening.rules import decide
    assert decide(80.0, True, 60.0)[0] == "passed"
    assert decide(55.0, True, 60.0)[0] == "manual_review"
    assert decide(30.0, True, 60.0)[0] == "rejected"
    assert decide(None, True, 60.0)[0] == "manual_review"


# --- application lifecycle ---

def test_screen_reuses_preexisting_candidate_and_links_application(fresh_db, make_job, resume_txt):
    """When a candidate row already exists for (email, job) — e.g. the recruiter
    manually pre-invited them — a later screening pass must reuse it AND link
    the new application to it, exactly like the race-adoption branch does.
    Otherwise application.candidate_id silently stays None."""
    from app.core.models import Candidate

    job = make_job()
    fresh_db.save_candidate(Candidate(
        candidate_id="manual-1", job_id=job["job_id"], name="Jane",
        email="cand@example.com", invite_code="manualcode",
    ))

    app = _apply(fresh_db, job, resume_txt)
    summary = _screen(fresh_db, app)

    assert summary["decision"] == "passed"
    assert summary["candidate_id"] == "manual-1"
    saved = fresh_db.get_application(app.application_id)
    assert saved["candidate_id"] == "manual-1", "application must be linked to the reused candidate"
    # exactly one candidate row for (email, job)
    assert len(fresh_db.get_candidates_for_job(job["job_id"])) == 1
    # the reused candidate is SHORTLISTED awaiting strategy confirmation (no
    # invite is enqueued during screening itself; no hr_email is configured
    # here so nothing else is on the outbox either).
    reused = fresh_db.get_candidate("manual-1")
    assert reused["mode_status"] == "SHORTLISTED"


def test_create_application_and_queue(fresh_db, make_job, resume_txt):
    from app.screening.service import DuplicateApplicationError
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    assert app.status == "received"
    saved = fresh_db.get_application(app.application_id)
    assert saved["job_id"] == job["job_id"]
    assert fresh_db.get_screening_job(app.application_id)["status"] == "queued"

    with pytest.raises(DuplicateApplicationError):
        _apply(fresh_db, job, resume_txt)


def test_duplicate_application_race_raised_as_duplicate_not_integrity_error(
        fresh_db, make_job, resume_txt, monkeypatch):
    """Two concurrent submissions pass the existence check together, then both
    insert — the loser hits the UNIQUE(email, job_id) index. That race must
    surface as DuplicateApplicationError (route maps it to 409), not a raw
    sqlite3.IntegrityError 500."""
    from app.screening import service as screening_service
    from app.screening.service import DuplicateApplicationError

    job = make_job()
    first = _apply(fresh_db, job, resume_txt)

    # Simulate the window where the second request's pre-check ran before the
    # first insert committed: it sees no existing row and attempts the INSERT.
    # Only the pre-check is "blind" — the concurrent row exists, so the
    # recovery lookup inside the fix must still find it (i.e. subsequent
    # calls delegate to the real function).
    real_lookup = screening_service.db.get_application_by_email_job
    calls = {"n": 0}

    def flaky_lookup(email, job_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_lookup(email, job_id)

    monkeypatch.setattr(screening_service.db, "get_application_by_email_job", flaky_lookup)
    with pytest.raises(DuplicateApplicationError):
        _apply(fresh_db, job, resume_txt)
    assert fresh_db.get_application(first.application_id)["email"] == "cand@example.com"


def test_screen_application_passed(fresh_db, make_job, resume_txt, monkeypatch):
    from app.core.settings_store import save_settings
    save_settings({"hr_email": "hr@acme.test", "backend_mode": "local"})
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    summary = _screen(fresh_db, app)
    assert summary["decision"] == "passed"
    assert fresh_db.get_application(app.application_id)["status"] == "invite_pending"

    candidates = fresh_db.get_candidates_for_job(job["job_id"])
    assert len(candidates) == 1
    assert candidates[0]["email"] == "cand@example.com"
    assert candidates[0]["screening_status"] == "passed_threshold"

    invites = fresh_db.get_interview_invites_for_candidate(candidates[0]["candidate_id"])
    assert len(invites) == 1
    assert invites[0]["status"] == "active"

    msgs = fresh_db.get_notifications_for_application(app.application_id)
    # The candidate is only SHORTLISTED here: the job-level interview-mode
    # strategy must be confirmed before any candidate invite is enqueued, so a
    # screening pass itself enqueues only the HR digest (never the invite).
    assert {m["notification_type"] for m in msgs} == {"hr_shortlist"}
    assert sum(1 for m in msgs if m["recipient"] == "hr@acme.test") == 1
    assert sum(1 for m in msgs if m["recipient"] == "cand@example.com") == 0
    # Cohort finalized + AUTO recommendation derived from the shortlist count.
    assert fresh_db.get_candidate(candidates[0]["candidate_id"])["mode_status"] == "SHORTLISTED"
    status = fresh_db.get_job_cohort_status(job["job_id"])
    assert status["cohort_finalized"] is True
    assert status["recommended_strategy"] == "MODE_1_ONLY"


def _screen(fresh_db, app):
    from app.screening.service import screen_application
    return screen_application(app.application_id)


def test_screen_application_rejected_by_hard_requirement(fresh_db, make_job, resume_txt):
    job = make_job(minimum_experience_years=10)
    app = _apply(fresh_db, job, resume_txt)
    summary = _screen(fresh_db, app)
    assert summary["decision"] == "rejected"
    assert fresh_db.get_application(app.application_id)["status"] == "rejected"
    assert fresh_db.get_candidates_for_job(job["job_id"]) == []
    assert fresh_db.get_notifications_for_application(app.application_id) == []


def test_screen_application_idempotent(fresh_db, make_job, resume_txt, monkeypatch):
    from app.core.settings_store import save_settings
    save_settings({"hr_email": "hr@acme.test", "backend_mode": "local"})
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    _screen(fresh_db, app)
    _screen(fresh_db, app)  # second run must not duplicate

    assert len(fresh_db.get_candidates_for_job(job["job_id"])) == 1
    candidate = fresh_db.get_candidates_for_job(job["job_id"])[0]
    assert len(fresh_db.get_interview_invites_for_candidate(candidate["candidate_id"])) == 1
    msgs = fresh_db.get_notifications_for_application(app.application_id)
    assert len(msgs) == 1  # hr_shortlist only: no invite enqueued at screening time
    assert fresh_db.get_screening_result(app.application_id)["decision"] == "passed"


def test_run_screening_jobs_processes_queue(fresh_db, make_job, resume_txt):
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    results = _run_worker(fresh_db)
    assert len(results) == 1
    assert results[0]["decision"] == "passed"
    assert fresh_db.get_screening_job(app.application_id)["status"] == "completed"


def test_stale_processing_job_is_reclaimed_after_worker_crash(fresh_db, make_job, resume_txt):
    """A job that crashed mid-'processing' (stale started_at) must be
    recovered by the next worker, not stuck forever."""
    from datetime import datetime, timedelta

    job = make_job()
    app = _apply(fresh_db, job, resume_txt)

    claimed = fresh_db.claim_next_screening_job()
    assert claimed["status"] == "processing"

    conn = fresh_db.get_connection()
    conn.execute(
        "UPDATE screening_jobs SET started_at = ? WHERE application_id = ?",
        (str(datetime.utcnow() - timedelta(minutes=30)), app.application_id),
    )
    conn.commit()
    conn.close()

    results = _run_worker(fresh_db)
    assert len(results) == 1
    assert results[0]["decision"] == "passed"
    assert fresh_db.get_screening_job(app.application_id)["status"] == "completed"


def test_fresh_processing_job_is_not_stolen_from_active_worker(fresh_db, make_job, resume_txt):
    """A job still within its processing window must NOT be re-queued: a
    concurrent worker is actively handling it."""
    job = make_job()
    app_a = _apply(fresh_db, job, resume_txt, email="a@example.com")
    app_b = _apply(fresh_db, job, resume_txt, email="b@example.com")

    fresh_db.claim_next_screening_job()
    assert fresh_db.get_screening_job(app_a.application_id)["status"] == "processing"

    claimed = fresh_db.claim_next_screening_job()
    assert claimed["application_id"] == app_b.application_id
    assert fresh_db.get_screening_job(app_a.application_id)["status"] == "processing"


def test_one_candidate_per_email_job_is_enforced(fresh_db, make_job, resume_txt):
    import sqlite3

    from app.core.models import Candidate

    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    _screen(fresh_db, app)
    candidate = fresh_db.get_candidates_for_job(job["job_id"])[0]

    # The worker vs email-intake race that once minted two candidate rows for
    # the same (email, job) is now blocked by the unique index.
    dup = Candidate(
        candidate_id="race-dup", job_id=job["job_id"], name="Duplicate",
        email=candidate["email"], invite_code="dupcode",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fresh_db.save_candidate(dup)

    # A later application from the same person reuses the existing candidate.
    _screen(fresh_db, app)  # re-screen: still one candidate
    assert len(fresh_db.get_candidates_for_job(job["job_id"])) == 1


def _run_worker(fresh_db):
    from app.screening.service import run_screening_jobs
    return run_screening_jobs(limit=10)


def test_workers_disabled_env_var_starts_nothing(monkeypatch):
    """INTERVIEWIQ_DISABLE_WORKERS=1 (set in the test conftest so tests stay
    deterministic) must prevent the daemon workers from starting. Without it,
    calling start_workers() spawns the daemon loops; with it, it returns empty
    and spawns nothing (they'd otherwise race explicitly-driven screening)."""
    import threading

    from app.screening import worker

    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    monkeypatch.setattr(worker, "_worker_threads", [dead])

    monkeypatch.setenv("INTERVIEWIQ_DISABLE_WORKERS", "1")
    assert worker.start_workers() == []

    monkeypatch.delenv("INTERVIEWIQ_DISABLE_WORKERS")
    started = worker.start_workers()
    assert len(started) == 2
    try:
        for t in started:
            t.join(timeout=0.1)
    finally:
        monkeypatch.setattr(worker, "_worker_threads", [])


# --- outbox / email worker (Gmail must never be a single point of failure) ---

def test_outbox_pending_when_gmail_disconnected(fresh_db, make_job, resume_txt, monkeypatch):
    from app.core.settings_store import save_settings
    save_settings({"hr_email": "hr@acme.test", "backend_mode": "local"})
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    _screen(fresh_db, app)

    from app.screening.email_worker import send_pending_notifications
    sent = send_pending_notifications()
    assert sent == []
    msgs = fresh_db.get_notifications_for_application(app.application_id)
    assert all(m["status"] == "pending" and m["attempts"] == 0 for m in msgs)


def test_outbox_retry_then_failed(fresh_db, make_job, resume_txt, monkeypatch):
    from app.core.settings_store import save_settings
    save_settings({"hr_email": "hr@acme.test", "backend_mode": "local"})
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    _screen(fresh_db, app)

    from app.screening import email_worker
    from app.screening.email_worker import send_pending_notifications, MAX_NOTIFICATION_ATTEMPTS

    class _Boom:
        def users(self):
            raise RuntimeError("Gmail send exploded")

    monkeypatch.setattr(email_worker, "get_gmail_service", lambda: _Boom())

    for i in range(MAX_NOTIFICATION_ATTEMPTS):
        send_pending_notifications()
    msgs = fresh_db.get_notifications_for_application(app.application_id)
    # every message is eventually failed after the attempt cap, never stuck retrying forever
    assert all(m["status"] == "failed" for m in msgs)
    assert all(m["attempts"] == MAX_NOTIFICATION_ATTEMPTS for m in msgs)
    candidate = fresh_db.get_candidates_for_job(job["job_id"])[0]
    assert candidate["invite_email_sent"] is False


def test_outbox_message_claimed_sending_is_not_resent_by_second_worker(
        fresh_db, make_job, resume_txt, monkeypatch):
    """A crash between 'email sent to Gmail' and 'mark sent' must not cause a
    duplicate send. The worker atomically claims a pending message as 'sending'
    before handing it to Gmail; a second worker must never see it."""
    from app.core.settings_store import save_settings
    save_settings({"hr_email": "hr@acme.test", "backend_mode": "local"})
    job = make_job()
    app = _apply(fresh_db, job, resume_txt)
    _screen(fresh_db, app)

    msgs = fresh_db.get_pending_notifications()
    assert msgs
    target = msgs[0]

    claimed = fresh_db.claim_pending_notification()
    assert claimed is not None
    assert claimed["id"] == target["id"]
    assert claimed["status"] == "sending"
    # A second worker cannot claim the same message while it is 'sending'.
    second = fresh_db.claim_pending_notification()
    assert second is None or second["id"] != target["id"]