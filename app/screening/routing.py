"""
Interview-mode routing: cohort-based allocation AFTER the ATS screening cohort
for a job is finalized, with a recruiter-confirmed job-level strategy.

High-level flow (no invitations before confirmation):

  1. Screening passes -> candidate is created + marked SHORTLISTED.
     No candidate invite is enqueued during screening.
  2. When the job's screening cohort is final (no queued/processing jobs and
     at least one shortlisted candidate), the AUTO recommendation is computed:
       shortlisted <= LIVE_INTERVIEW_CAPACITY -> MODE_1_ONLY
       shortlisted >  LIVE_INTERVIEW_CAPACITY -> MODE_2_THEN_MODE_1
  3. The recruiter confirms a strategy on the Job/Interview Configuration
     screen (AUTO applies the recommendation; MODE_1_ONLY / MODE_2_THEN_MODE_1
     override it). Confirmation assigns every SHORTLISTED candidate a mode and
     enqueues that mode's invite:
       MODE_1            -> mode1_invite  (email worker auto-books a slot)
       MODE_2            -> mode2_invite  (AI self-serve, no calendar slot)
  4. Mode 2 cohort: on completion, each candidate's Mode 2 score is persisted.
     When the WHOLE Mode 2 cohort has completed, candidates are ranked
     deterministically and the top LIVE_INTERVIEW_CAPACITY are promoted to
     Mode 1 (mode1_promotion -> auto-books a slot); the rest are emailed
     not_selected.

Idempotency: assignment only touches SHORTLISTED candidates with no mode;
ranking runs once per cohort (guarded by rank already being set).
"""
import logging
import secrets

from app.core import db
from app.core.models import InterviewInvite

logger = logging.getLogger(__name__)

# Number of Mode 1 interview slots available per job cohort. Centralized here
# (not hard-coded in routes) so operators can resize the funnel in one place.
LIVE_INTERVIEW_CAPACITY = 6

# Categories whose answers form the "technical/problem-solving" sub-score used
# as the deterministic tie-breaker after the Mode 2 overall score.
TECHNICAL_CATEGORIES = ("DSA", "System Design", "Technical Knowledge", "Problem Solving")

VALID_STRATEGIES = db.VALID_INTERVIEW_STRATEGIES


def recommend_strategy(job_id):
    """Compute + persist the AUTO recommendation from the finalized shortlist
    count. Guarded so the recommendation is never derived from a screening
    cohort that is still in progress."""
    shortlisted = db.count_shortlisted_for_job(job_id)
    recommended = (
        "MODE_1_ONLY" if shortlisted <= LIVE_INTERVIEW_CAPACITY
        else "MODE_2_THEN_MODE_1"
    )
    db.set_job_recommended_strategy(job_id, recommended)
    return recommended


def finalize_cohort_if_ready(job_id):
    """Mark the screening cohort as final once every queued/processing
    application for the job has been screened (idempotent) and at least one
    candidate is shortlisted. Persists the AUTO recommendation."""
    status = db.get_job_cohort_status(job_id)
    if status is None or status["screening_pending"] > 0:
        return status
    if status["shortlisted"] == 0:
        return status
    if not status["cohort_finalized"]:
        from datetime import datetime
        db.set_job_cohort_finalized(job_id, datetime.utcnow().isoformat())
        status["cohort_finalized"] = True
    recommend_strategy(job_id)
    status["recommended_strategy"] = (
        db.get_job_posting(job_id) or {}
    ).get("recommended_strategy", "")
    return status


def _ensure_active_invite(candidate_id, job_id, application_id):
    """Reuse the candidate's active invite for this job, else mint one. The
    invite row is what the candidate consumes at session start; the invite
    email just carries the invite_code."""
    for invite in db.get_interview_invites_for_candidate(candidate_id):
        if invite["job_id"] == job_id and invite["status"] == "active":
            return invite
    invite = InterviewInvite(
        candidate_id=candidate_id,
        job_id=job_id,
        application_id=application_id,
        token=secrets.token_urlsafe(32),
    )
    db.create_interview_invite(invite)
    return db.get_interview_invite_by_token(invite.token)


def _enqueue_mode_invite(candidate, job, mode):
    """Enqueue the mode-specific candidate invite. No-op when auto-invite is
    disabled for the job or the candidate has no email. Idempotent per
    (application, type, recipient)."""
    if not job.get("auto_invite_enabled", True):
        return False
    email = (candidate.get("email") or "").strip()
    if not email:
        return False

    invite = _ensure_active_invite(
        candidate["candidate_id"], job["job_id"], candidate.get("application_id")
    )
    if mode == "MODE_1":
        ntype, subject = "mode1_invite", f"Your interview invitation \u2014 {job['title']}"
    elif mode == "MODE_2":
        ntype, subject = "mode2_invite", f"Your self-serve interview \u2014 {job['title']}"
    else:
        return False

    enqueued = db.enqueue_notification(
        application_id=candidate.get("application_id"),
        job_id=job["job_id"],
        notification_type=ntype,
        recipient=email,
        subject=subject,
        body=invite.get("token", ""),
        candidate_id=candidate["candidate_id"],
    )
    if enqueued:
        db.mark_candidate_invited(candidate["candidate_id"])
    return enqueued


def assign_modes_for_job(job_id):
    """Assign interview modes to every SHORTLISTED candidate of a finalized +
    confirmed job, then enqueue the mode invites. Idempotent: candidates that
    already hold a mode/status are skipped."""
    status = db.get_job_cohort_status(job_id)
    if status is None:
        return
    if not (status["cohort_finalized"] and status["strategy_confirmed"]):
        return status

    job = db.get_job_posting(job_id)
    strategy = status["interview_strategy"]
    if strategy == "AUTO":
        strategy = status["recommended_strategy"] or recommend_strategy(job_id)
    if strategy not in VALID_STRATEGIES or strategy == "AUTO":
        logger.warning("job %s has no useable strategy after confirmation", job_id)
        return status

    for candidate in db.get_shortlisted_candidates(job_id):
        if candidate.get("mode_status") != "SHORTLISTED" or candidate.get("interview_mode"):
            continue
        mode = "MODE_1" if strategy == "MODE_1_ONLY" else "MODE_2"
        db.set_candidate_route(candidate["candidate_id"], mode, "CONFIRMED", "SYSTEM")
        _enqueue_mode_invite(candidate, job, mode)
    return status


def confirm_strategy(job_id, strategy, confirmed_at=None):
    """Persist the recruiter-confirmed strategy and immediately assign modes +
    enqueue invites for the finalized cohort. Returns the cohort status dict."""
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unknown interview strategy: {strategy!r}")
    status = db.get_job_cohort_status(job_id)
    if status is None:
        raise ValueError(f"job {job_id} not found")
    if not status["cohort_finalized"]:
        raise ValueError(
            "The screening cohort for this job is not finalized yet; "
            "invitations cannot be sent until it is."
        )
    from datetime import datetime
    db.confirm_job_strategy(job_id, strategy, confirmed_at or datetime.utcnow().isoformat())
    return assign_modes_for_job(job_id)


def _compute_mode2_score(candidate):
    """Return the candidate's Mode 2 overall + technical sub-score from their
    completed session's competency_scores, or (None, None) if unavailable."""
    session_id = candidate.get("session_id")
    if not session_id:
        return None, None
    scores = [s["score"] for s in db.get_session_scores(session_id)]
    if not scores:
        return None, None
    overall = sum(scores) / len(scores)
    tech = [s["score"] for s in db.get_session_scores(session_id)
            if (s.get("category") or "").lower() in {c.lower() for c in TECHNICAL_CATEGORIES}]
    sub = sum(tech) / len(tech) if tech else 0.0
    return overall, sub


def on_mode2_candidate_completed(job_id, candidate_id):
    """Persist a completing Mode 2 candidate's score, then attempt cohort
    ranking once the whole Mode 2 cohort has finished. Called from the
    candidate complete-session path."""
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("interview_mode") != "MODE_2":
        return
    overall, sub = _compute_mode2_score(candidate)
    if overall is not None:
        db.set_candidate_mode2_result(candidate_id, overall, overall)
    rank_mode2_cohort_if_ready(job_id)


def rank_mode2_cohort_if_ready(job_id):
    """Rank the job's Mode 2 cohort once every member has completed, promote
    the top LIVE_INTERVIEW_CAPACITY to Mode 1 and enqueue promotion /
    not-selected emails. Deterministic + idempotent.

    Ordering: Mode 2 overall score desc, technical/problem-solving sub-score
    desc, then earlier session completed_at asc (ties resolved by candidate_id
    for full determinism). Performance, never completion order alone."""
    cohort = db.get_mode2_candidates_for_job(job_id)
    if not cohort:
        return

    # Not ready until every Mode 2 candidate has completed their session.
    if any(c.get("session_status") != "completed" for c in cohort):
        return
    # Already ranked (or partially ranked) -> never double-rank.
    if any(c.get("rank") not in (None, "") for c in cohort):
        return
    if all(c.get("overall_score") is None for c in cohort):
        return

    job = db.get_job_posting(job_id)

    ranked_rows = []
    for candidate in cohort:
        overall = candidate.get("overall_score")
        scores = db.get_session_scores(candidate.get("session_id") or "")
        tech = [s["score"] for s in scores
                if (s.get("category") or "").lower() in {c.lower() for c in TECHNICAL_CATEGORIES}]
        sub = sum(tech) / len(tech) if tech else 0.0
        completed_at = candidate.get("session_completed_at") or ""
        ranked_rows.append({
            "candidate": candidate,
            "overall": overall,
            "sub": sub,
            "completed_at": completed_at,
        })

    ranked_rows.sort(
        key=lambda r: (
            -(r["overall"] or 0.0),
            -(r["sub"]),
            r["completed_at"],
            r["candidate"]["candidate_id"],
        )
    )

    n = len(ranked_rows)
    promote_count = min(LIVE_INTERVIEW_CAPACITY, n)
    promoted_ids = [r["candidate"]["candidate_id"] for r in ranked_rows[:promote_count]]
    not_selected_ids = [r["candidate"]["candidate_id"] for r in ranked_rows[promote_count:]]

    from datetime import datetime
    now = datetime.utcnow().isoformat()
    db.apply_cohort_ranking(
        job_id,
        ranked=[(r["candidate"]["candidate_id"], i + 1) for i, r in enumerate(ranked_rows)],
        promoted=promoted_ids,
        not_promoted=not_selected_ids,
        at=now,
    )
    logger.info("ranked job %s: promoted=%d/%d", job_id, len(promoted_ids), n)

    for cid in promoted_ids:
        candidate = db.get_candidate(cid)
        email = (candidate or {}).get("email") or ""
        if email:
            db.enqueue_notification(
                application_id=candidate.get("application_id"),
                job_id=job_id,
                notification_type="mode1_promotion",
                recipient=email,
                subject=f"You've advanced to the final round \u2014 {job['title'] if job else ''}",
                body=str(now),
                candidate_id=cid,
            )
    for cid in not_selected_ids:
        candidate = db.get_candidate(cid)
        email = (candidate or {}).get("email") or ""
        if email:
            db.enqueue_notification(
                application_id=candidate.get("application_id"),
                job_id=job_id,
                notification_type="not_selected",
                recipient=email,
                subject=f"Update on your application \u2014 {job['title'] if job else ''}",
                body="",
                candidate_id=cid,
            )


def route_pending_assignments(limit: int = 50) -> list:
    """Worker sweep: assign + invite any SHORTLISTED candidates whose job is
    finalized and confirmed (e.g. AUTO cohorts waiting on the worker after the
    recruiter confirmed while screening was still draining)."""
    processed = []
    seen = set()
    for candidate in db.get_pending_mode_assignments():
        job_id = candidate["job_id"]
        if job_id in seen:
            continue
        seen.add(job_id)
        status = assign_modes_for_job(job_id)
        if status is not None:
            processed.append(status)
        if len(seen) >= limit:
            break
    return processed