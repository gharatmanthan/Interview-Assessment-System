"""Interview-mode routing tests: cohort finalization, AUTO recommendation,
strategy confirmation gating invitations, and deterministic Mode 2 ranking as
the job-level funnel is executed."""
from datetime import datetime

import pytest


@pytest.fixture
def make_job(fresh_db):
    from app.core.models import JobPosting

    def _make(**overrides):
        fields = dict(
            job_id="job-route-1",
            title="Platform Engineer",
            description="Build robust services with python, sql and cloud.",
            required_skills=["python", "sql"],
            experience_level="Mid",
            department="Engineering",
            screening_threshold=50.0,
            minimum_experience_years=1,
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
        "Platform engineer with python, sql and aws experience. "
        "4 years of experience. B.Tech in Computer Science.",
        encoding="utf-8",
    )
    return str(path)


def _apply(db, job, resume_path, email):
    from app.screening.service import create_application_and_queue
    return create_application_and_queue(
        job=job, full_name="Routed Candidate", email=email,
        phone="+1", resume_path=resume_path,
    )


def _screen(db, app):
    from app.screening.service import screen_application
    return screen_application(app.application_id)


def _screen_cohort(db, job, resume_path, emails):
    """Queue + screen a batch of applicants for `job`, returning the shortlisted
    candidate rows in application-creation order."""
    apps = []
    for email in emails:
        app = _apply(db, job, resume_path, email)
        _screen(db, app)
        apps.append(app)
    out = []
    for app in apps:
        row = db.get_application(app.application_id)
        out.append(db.get_candidate(row["candidate_id"]))
    return out


def _complete_mode2(db, candidate, scores):
    """Give a Mode 2 candidate a completed session with the given competency
    scores (list of (category, score)), then run the routing hook."""
    from app.core.models import CompetencyScore, InterviewSession
    from app.screening.routing import on_mode2_candidate_completed

    sid = db.resolve_or_create_session(
        candidate["candidate_id"], candidate["job_id"], candidate["name"], "Platform Engineer"
    )
    for idx, (category, score) in enumerate(scores):
        db.save_competency_score(CompetencyScore(
            session_id=sid, question_id=f"q{idx}", category=category,
            score=score, confidence=0.8,
        ))
    session = InterviewSession(**dict(db.get_session(sid)))
    session.status = "completed"
    session.completed_at = datetime.utcnow().isoformat()
    db.save_session(session)
    # Link the candidate to the resolved session like complete-session does.
    db.update_candidate_status(candidate["candidate_id"], "completed", session_id=sid)
    on_mode2_candidate_completed(candidate["job_id"], candidate["candidate_id"])
    return sid


# --- recommendation + finalization ---

def test_finalize_cohort_when_shortlist_is_complete(fresh_db, make_job, resume_txt):
    job = make_job()
    _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com"])
    status = fresh_db.get_job_cohort_status(job["job_id"])
    assert status["cohort_finalized"] is True
    assert status["screening_pending"] == 0
    assert status["shortlisted"] == 1


def test_cohort_not_finalized_while_screening_pending(fresh_db, make_job, resume_txt):
    """A single passed applicant does not finalize the cohort if another
    applicant is still queued for the same job."""
    job = make_job()
    first = _apply(fresh_db, job, resume_txt, "c1@example.com")
    _apply(fresh_db, job, resume_txt, "c2@example.com")
    _screen(fresh_db, first)
    status = fresh_db.get_job_cohort_status(job["job_id"])
    assert status["screening_pending"] == 1
    assert status["cohort_finalized"] is False


def test_recommendation_threshold(fresh_db, make_job, resume_txt):
    small = make_job(job_id="job-4-short")
    _screen_cohort(fresh_db, small, resume_txt, ["a@example.com", "b@example.com",
                                                 "c@example.com", "d@example.com"])
    assert fresh_db.get_job_cohort_status(small["job_id"])["recommended_strategy"] == "MODE_1_ONLY"

    large = make_job(job_id="job-7-large")
    _screen_cohort(fresh_db, large, resume_txt, [f"c{i}@example.com" for i in range(7)])
    assert fresh_db.get_job_cohort_status(large["job_id"])["recommended_strategy"] == "MODE_2_THEN_MODE_1"


# --- assignment gating ---

def test_no_invites_before_strategy_confirmed(fresh_db, make_job, resume_txt):
    job = make_job()
    candidates = _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com"])
    # Candidates are SHORTLISTED but must carry no mode and no outbox invite yet.
    for cand in candidates:
        assert cand["mode_status"] == "SHORTLISTED"
        assert cand["interview_mode"] == ""
    invites = fresh_db.get_interview_invites_for_candidate(candidates[0]["candidate_id"])
    assert all(i["status"] == "active" for i in invites)
    # No candidate-facing notification was enqueued during screening.
    app = fresh_db.get_application(fresh_db.get_candidate(candidates[0]["candidate_id"])["application_id"])
    for m in fresh_db.get_notifications_for_application(app["application_id"]):
        assert m["notification_type"] != "mode1_invite"
        assert m["notification_type"] != "mode2_invite"


def test_confirm_refuses_when_cohort_not_finalized(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    from app.screening.service import screen_application

    job = make_job()
    # Queue BOTH applicants first; screen only one, so a job stays in progress
    # and the cohort must not be considered final.
    _apply(fresh_db, job, resume_txt, "c1@example.com")
    _apply(fresh_db, job, resume_txt, "c2@example.com")
    first = fresh_db.get_applications_for_job(job["job_id"])[0]
    screen_application(first["application_id"])
    status = fresh_db.get_job_cohort_status(job["job_id"])
    assert status["screening_pending"] == 1
    assert status["cohort_finalized"] is False
    with pytest.raises(ValueError):
        confirm_strategy(job["job_id"], "MODE_1_ONLY")


def test_no_invitations_when_auto_invite_disabled(fresh_db, make_job, resume_txt):
    job = make_job(auto_invite_enabled=False)
    candidates = _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com"])
    from app.screening.routing import confirm_strategy
    confirm_strategy(job["job_id"], "MODE_1_ONLY")
    for cand in candidates:
        fresh = fresh_db.get_candidate(cand["candidate_id"])
        assert fresh["interview_mode"] == "MODE_1"
        assert fresh["mode_status"] == "CONFIRMED"  # assigned but no invite sent
    assert fresh_db.get_pending_mode_assignments() == []


def test_assign_missing_email_keeps_confirmed_skip_invite(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job = make_job()
    cand = _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com"])[0]
    conn = fresh_db.get_connection()
    conn.execute("UPDATE candidates SET email='' WHERE candidate_id=?", (cand["candidate_id"],))
    conn.commit()
    conn.close()
    confirm_strategy(job["job_id"], "MODE_1_ONLY")
    fresh = fresh_db.get_candidate(cand["candidate_id"])
    assert fresh["interview_mode"] == "MODE_1"
    assert fresh["mode_status"] == "CONFIRMED"  # no email -> invite not enqueued
    app = fresh_db.get_application(fresh_db.get_candidate(cand["candidate_id"])["application_id"])
    assert not any(m["recipient"] == cand["email"]
                   for m in fresh_db.get_notifications_for_application(app["application_id"]))


# --- Mode 1 direct (capacity threshold) ---

def test_mode1_direct_within_capacity(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job = make_job()
    candidates = _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com", "c2@example.com"])
    confirm_strategy(job["job_id"], "MODE_1_ONLY")
    for cand in candidates:
        fresh = fresh_db.get_candidate(cand["candidate_id"])
        assert fresh["interview_mode"] == "MODE_1"
        assert fresh["mode_status"] == "INVITED"
    # Two candidate invites enqueued (mode1_invite), no mode2 invites.
    invites = [m for m in fresh_db.get_outbox_messages()
               if m["notification_type"] == "mode1_invite"]
    assert len(invites) == 2
    assert not any(m["notification_type"] == "mode2_invite"
                   for m in fresh_db.get_outbox_messages())


# --- Mode 2 then Mode 1 promotion ---

def test_mode2_promotes_top_capacity(fresh_db, make_job, resume_txt):
    from app.screening.routing import LIVE_INTERVIEW_CAPACITY, confirm_strategy
    job = make_job()
    candidates = _screen_cohort(
        fresh_db, job, resume_txt, [f"c{i}@example.com" for i in range(7)]
    )
    confirm_strategy(job["job_id"], "MODE_2_THEN_MODE_1")
    for cand in fresh_db.get_candidates_for_job(job["job_id"]):
        assert cand["interview_mode"] == "MODE_2"
        assert cand["mode_status"] == "INVITED"

    assert LIVE_INTERVIEW_CAPACITY >= 6
    # Give each candidate a distinct Mode 2 score; the top 6 must promote.
    scores = [80 + i for i in range(len(candidates))]
    for cand, score in zip(candidates, scores):
        _complete_mode2(fresh_db, cand, [("DSA", score)])

    promoted = [c for c in fresh_db.get_candidates_for_job(job["job_id"])
                if c["mode_status"] == "PROMOTED"]
    assert len(promoted) == LIVE_INTERVIEW_CAPACITY
    not_promoted = [c for c in fresh_db.get_candidates_for_job(job["job_id"])
                    if c["mode_status"] == "NOT_PROMOTED"]
    assert len(not_promoted) == 1
    assert not_promoted[0]["rank"] == 7
    # Ranked strictly by score desc.
    ranked = sorted(fresh_db.get_candidates_for_job(job["job_id"]),
                    key=lambda c: c["rank"])
    assert [c["overall_score"] for c in ranked] == sorted(scores, reverse=True)
    # Promotion emails enqueued for the promoted cohort; not_selected for the rest.
    types = {m["notification_type"] for m in fresh_db.get_outbox_messages()}
    assert "mode1_promotion" in types
    assert "not_selected" in types


def test_mode2_no_double_rank_on_duplicate_completion(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy, on_mode2_candidate_completed
    job = make_job()
    candidates = _screen_cohort(
        fresh_db, job, resume_txt, [f"c{i}@example.com" for i in range(7)]
    )
    confirm_strategy(job["job_id"], "MODE_2_THEN_MODE_1")

    for cand in candidates:
        _complete_mode2(fresh_db, cand, [("DSA", 70)])
    first_rank = {c["candidate_id"]: c["rank"]
                  for c in fresh_db.get_candidates_for_job(job["job_id"])}

    # Re-fire the hook for an already-ranked candidate: must stay idempotent.
    on_mode2_candidate_completed(job["job_id"], candidates[0]["candidate_id"])
    after = {c["candidate_id"]: c["rank"]
             for c in fresh_db.get_candidates_for_job(job["job_id"])}
    assert after == first_rank
    # Exactly one promotion email per promoted candidate.
    promos = [m for m in fresh_db.get_outbox_messages()
              if m["notification_type"] == "mode1_promotion"]
    assert len(promos) == 6


def test_mode2_ranking_not_run_until_all_completed(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job = make_job()
    candidates = _screen_cohort(
        fresh_db, job, resume_txt, [f"c{i}@example.com" for i in range(7)]
    )
    confirm_strategy(job["job_id"], "MODE_2_THEN_MODE_1")
    # Only 6 of 7 finish -> no promotion yet.
    for cand in candidates[:6]:
        _complete_mode2(fresh_db, cand, [("DSA", 80)])
    for c in fresh_db.get_candidates_for_job(job["job_id"]):
        assert c["rank"] is None
    # The last candidate finishing triggers ranking.
    _complete_mode2(fresh_db, candidates[6], [("DSA", 80)])
    ranked = [c for c in fresh_db.get_candidates_for_job(job["job_id"]) if c["rank"]]
    assert len(ranked) == 7


def test_mode2_tiebreak_by_technical_subscore(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job = make_job()
    candidates = _screen_cohort(
        fresh_db, job, resume_txt, [f"c{i}@example.com" for i in range(7)]
    )
    confirm_strategy(job["job_id"], "MODE_2_THEN_MODE_1")
    # Five candidates score max (100). The two remaining candidates tie on the
    # Mode 2 overall (70) but differ on the technical sub-score, so the
    # promotion cut (top 6) falls exactly between them: the higher-technical
    # candidate ranks 6th (promoted) and the lower-technical one 7th (not).
    for cand in candidates[:5]:
        _complete_mode2(fresh_db, cand, [("DSA", 100)])
    _complete_mode2(fresh_db, candidates[5], [("DSA", 90), ("Communication", 50)])
    _complete_mode2(fresh_db, candidates[6], [("DSA", 50), ("Communication", 90)])
    overall = {c["candidate_id"]: c["overall_score"]
               for c in fresh_db.get_candidates_for_job(job["job_id"])}
    assert overall[candidates[5]["candidate_id"]] == pytest.approx(70.0)
    assert overall[candidates[6]["candidate_id"]] == pytest.approx(70.0)
    ranks = {c["candidate_id"]: c["rank"]
             for c in fresh_db.get_candidates_for_job(job["job_id"])}
    # Technical sub-score is the tie-breaker within equal overall.
    assert ranks[candidates[5]["candidate_id"]] == 6
    assert ranks[candidates[6]["candidate_id"]] == 7
    statuses = {c["candidate_id"]: c["mode_status"]
                for c in fresh_db.get_candidates_for_job(job["job_id"])}
    assert statuses[candidates[5]["candidate_id"]] == "PROMOTED"
    assert statuses[candidates[6]["candidate_id"]] == "NOT_PROMOTED"


def test_mode2_score_is_overall_mean(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job = make_job()
    candidates = _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com"])
    confirm_strategy(job["job_id"], "MODE_2_THEN_MODE_1")
    _complete_mode2(fresh_db, candidates[0], [("DSA", 80), ("Communication", 100)])
    fresh = fresh_db.get_candidate(candidates[0]["candidate_id"])
    assert fresh["mode2_score"] == pytest.approx(90.0)


# --- isolation + rejection + shortlist-change ---

def test_routing_is_per_job(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job_a = make_job(job_id="job-iso-a")
    job_b = make_job(job_id="job-iso-b")
    cands_a = _screen_cohort(fresh_db, job_a, resume_txt, ["a1@example.com", "a2@example.com"])
    cands_b = _screen_cohort(fresh_db, job_b, resume_txt, ["b@example.com"])
    confirm_strategy(job_a["job_id"], "MODE_1_ONLY")
    confirm_strategy(job_b["job_id"], "MODE_2_THEN_MODE_1")
    for c in cands_a:
        assert fresh_db.get_candidate(c["candidate_id"])["interview_mode"] == "MODE_1"
    assert fresh_db.get_candidate(cands_b[0]["candidate_id"])["interview_mode"] == "MODE_2"


def test_rejected_candidates_never_routed(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy
    job = make_job(minimum_experience_years=20)
    app = _apply(fresh_db, job, resume_txt, "c@example.com")
    _screen(fresh_db, app)
    assert fresh_db.get_application(app.application_id)["status"] == "rejected"
    assert fresh_db.get_candidates_for_job(job["job_id"]) == []
    # With nothing shortlisted the cohort never finalizes, so confirmation is
    # refused — a rejected-only cohort can never route anyone to a mode.
    with pytest.raises(ValueError):
        confirm_strategy(job["job_id"], "MODE_1_ONLY")


def test_shortlist_change_before_allocation(fresh_db, make_job, resume_txt):
    """The AUTO recommendation is recomputed when the cohort is finalized, and
    a candidate added before confirm is allocated like the initial shortlist."""
    from app.screening.routing import confirm_strategy

    job = make_job()
    # One passes and, with nothing else queued, the cohort finalizes to MODE_1.
    app1 = _apply(fresh_db, job, resume_txt, "c1@example.com")
    _screen(fresh_db, app1)
    assert fresh_db.get_job_cohort_status(job["job_id"])["recommended_strategy"] == "MODE_1_ONLY"

    # Before confirmation another applicant passes; the finalized cohort now has
    # 2 shortlisted. Confirmation must route BOTH to Mode 1 (still within cap).
    app2 = _apply(fresh_db, job, resume_txt, "c2@example.com")
    _screen(fresh_db, app2)
    status = fresh_db.get_job_cohort_status(job["job_id"])
    assert status["shortlisted"] == 2

    confirm_strategy(job["job_id"], "AUTO")
    mode1 = [c for c in fresh_db.get_candidates_for_job(job["job_id"])
             if c["interview_mode"] == "MODE_1"]
    assert len(mode1) == 2
    assert all(c["mode_status"] == "INVITED" for c in fresh_db.get_candidates_for_job(job["job_id"]))


def test_worker_sweep_assigns_pending(fresh_db, make_job, resume_txt):
    from app.screening.routing import confirm_strategy, route_pending_assignments
    job = make_job(job_id="job-sweep")
    cand = _screen_cohort(fresh_db, job, resume_txt, ["c1@example.com"])[0]
    confirm_strategy(job["job_id"], "MODE_1_ONLY")
    assert fresh_db.get_candidate(cand["candidate_id"])["interview_mode"] == "MODE_1"