"""
Screening orchestration: Application -> ScreeningResult -> Candidate ->
InterviewInvite -> notification outbox (all side effects deferred to workers).

Idempotency guarantees:
  * a screening result is stored once per application (UNIQUE application_id,
    re-runs UPSERT deterministically);
  * a candidate is created once per (email, job);
  * an active interview invite is reused rather than regenerated;
  * outbox enqueue is INSERT OR IGNORE per (application, type, recipient).
"""
import logging
import secrets
import sqlite3

from app.core import db
from app.core.models import Application, Candidate, InterviewInvite, ScreeningResult
from app.engine.jd_matcher import match_resume_to_jd
from app.engine.resume_parser import parse_resume
from app.screening.rules import decide, eval_hard_requirements
from app.screening.scoring import component_scores

logger = logging.getLogger(__name__)

MAX_SCREENING_ATTEMPTS = 3


class DuplicateApplicationError(Exception):
    """Raised when an application already exists for (email, job)."""


def _jd_text(job: dict) -> str:
    skills = "".join(f"- {s}\n" for s in (job.get("required_skills") or []))
    return f"{job.get('description', '')}\n\nRequired skills:\n{skills}"


def create_application_and_queue(
    *,
    job: dict,
    full_name: str,
    email: str,
    phone: str = "",
    resume_path: str = "",
    source: str = "apply_portal",
) -> Application:
    """Store the application first, then queue the screening job."""
    existing = db.get_application_by_email_job(email, job["job_id"])
    if existing:
        raise DuplicateApplicationError(
            f"An application for {email} already exists for job {job['job_id']}"
        )

    app = Application(
        application_id=secrets.token_hex(16),
        job_id=job["job_id"],
        full_name=full_name,
        email=email,
        phone=phone,
        resume_path=resume_path,
        source=source,
        status="received",
        screening_status="queued",
    )
    try:
        db.create_application(app)
    except sqlite3.IntegrityError:
        # The (email, job_id) unique index caught a concurrent duplicate that
        # slipped past the pre-check above. Surface it as a duplicate, not a 500.
        existing = db.get_application_by_email_job(email, job["job_id"])
        if existing:
            raise DuplicateApplicationError(
                f"An application for {email} already exists for job {job['job_id']}"
            )
        raise
    db.create_screening_job(app.application_id)
    db.insert_application_event(
        app.application_id,
        "application_received",
        f"source={source} job={job['job_id']}",
    )
    return app


def _ensure_candidate(app: dict, job: dict, resume_data: dict, match_result: dict):
    """Create a Candidate row only if none exists for (email, job). Returns
    (candidate_dict, created: bool). The dict has the candidate_id/email/name/
    invite_code keys the rest of the pipeline needs.
    """
    def _as_dict(cand) -> dict:
        return {
            "candidate_id": cand.candidate_id,
            "email": cand.email,
            "name": cand.name,
            "invite_code": cand.invite_code,
        }

    existing = db.get_candidate_by_email_job(app["email"], job["job_id"])
    if existing:
        # Reuse the existing candidate (e.g. the recruiter manually pre-invited
        # this person for the same job). Link this application to it so the
        # recruitment view and outbox address the same candidate row — mirroring
        # what the integrity-error adoption branch below does.
        db.update_application_candidate(app["application_id"], existing["candidate_id"])
        return existing, False

    candidate = Candidate(
        candidate_id=f"{app['source']}-{secrets.token_hex(8)}",
        job_id=job["job_id"],
        name=app["full_name"] or app["email"],
        email=app["email"],
        invite_code=secrets.token_urlsafe(6),
        status="invited",
        source=app["source"],
        screening_status="passed_threshold",
        invite_email_sent=False,
        application_id=app["application_id"],
    )
    try:
        db.save_candidate(candidate)
    except sqlite3.IntegrityError:
        # A concurrent screener (worker thread vs email-intake inline run) may
        # have created the other candidate for this (email, job) between our
        # existence check and the insert. Adopt it instead of failing.
        existing = db.get_candidate_by_email_job(app["email"], job["job_id"])
        if existing:
            db.update_application_candidate(app["application_id"], existing["candidate_id"])
            return existing, False
        raise
    db.save_candidate_resume(
        candidate.candidate_id,
        app.get("resume_path", ""),
        resume_data.get("skills", []),
        resume_data.get("experience_years"),
        match_result.get("match_score", 0.0),
        match_result.get("matched_skills", []),
        match_result.get("missing_skills", []),
    )
    db.update_application_candidate(app["application_id"], candidate.candidate_id)
    return _as_dict(candidate), True


def _ensure_interview_invite(candidate_id: str, job_id: str, application_id: str) -> dict:
    """Reuse an existing active invite for (candidate, job), else mint one."""
    for invite in db.get_interview_invites_for_candidate(candidate_id):
        if invite["job_id"] == job_id and invite["status"] == "active":
            return invite, False
    invite = InterviewInvite(
        candidate_id=candidate_id,
        job_id=job_id,
        application_id=application_id,
        token=secrets.token_urlsafe(32),
    )
    db.create_interview_invite(invite)
    return db.get_interview_invite_by_token(invite.token), True


def _enqueue_notifications(app: dict, job: dict, candidate: dict, invite: dict,
                           match_score: float):
    from app.core.settings_store import load_settings
    settings = load_settings()
    hr_recipient = (settings.get("hr_email") or "").strip()

    if hr_recipient:
        db.enqueue_notification(
            application_id=app["application_id"],
            job_id=job["job_id"],
            notification_type="hr_shortlist",
            recipient=hr_recipient,
            subject=f"Shortlisted candidate: {app['full_name']} — {job['title']}",
            body="",
            candidate_id=candidate["candidate_id"],
        )

    if job.get("auto_invite_enabled", True) and candidate.get("email"):
        db.enqueue_notification(
            application_id=app["application_id"],
            job_id=job["job_id"],
            notification_type="interview_invite",
            recipient=candidate["email"],
            subject=f"You've been shortlisted for an interview — {job['title']}",
            body=invite["token"],
            candidate_id=candidate["candidate_id"],
        )


def screen_application(application_id: str) -> dict:
    """Run the full screening pipeline for one application. Idempotent:
    re-runs after a failure recompute the same result (UPSERT) and reuse
    the same candidate/invite.
    """
    app = db.get_application(application_id)
    if not app:
        raise ValueError(f"application {application_id} not found")

    job = db.get_job_posting(app["job_id"])
    if not job:
        raise ValueError(f"job {app['job_id']} not found for application {application_id}")
    if not app.get("resume_path"):
        raise ValueError(f"application {application_id} has no stored resume")

    # Automated screening disabled on this job: leave the application for
    # manual review instead of shortlisting anyone. No AI decision, no invite.
    if not job.get("screening_enabled", True):
        db.update_application_screening_status(application_id, "completed")
        db.update_application_status(application_id, "manual_review")
        db.insert_application_event(
            application_id,
            "screening_disabled",
            "Automated screening disabled on this job; left for manual review.",
        )
        db.insert_application_event(application_id, "screening_completed")
        db.complete_screening_job(application_id)
        return {
            "application_id": application_id,
            "decision": "manual_review",
            "reason": "screening disabled on this job",
            "ats_score": None,
            "candidate_id": None,
            "invite_token": None,
        }

    db.update_application_status(application_id, "screening")
    db.update_application_screening_status(application_id, "processing")
    db.insert_application_event(application_id, "screening_started")

    resume_data = parse_resume(app["resume_path"])
    match_result = match_resume_to_jd(resume_data, _jd_text(job))
    hard = eval_hard_requirements(resume_data, job)
    scored = component_scores(resume_data, job, match_result)
    ats = scored["overall"]
    threshold = job.get("screening_threshold", 60.0)

    decision, reason = decide(
        ats,
        hard["passed"],
        threshold,
    )

    result = ScreeningResult(
        application_id=application_id,
        ats_score=ats,
        skills_score=_component_value(scored, "skills"),
        experience_score=_component_value(scored, "experience"),
        semantic_score=_component_value(scored, "semantic"),
        education_score=_component_value(scored, "education"),
        keyword_score=_component_value(scored, "keyword"),
        matched_skills=match_result.get("matched_skills", []),
        missing_skills=match_result.get("missing_skills", []),
        hard_requirements_passed=hard["passed"],
        hard_requirement_failures=hard["failures"],
        decision=decision,
        decision_reason=reason,
        threshold_used=threshold,
        scoring_method="weighted_components",
        matcher_method=match_result.get("matched_by", ""),
        confidence=_confidence(match_result),
    )
    db.save_screening_result(result)

    candidate = None
    invite = None
    if decision == "passed":
        candidate, candidate_created = _ensure_candidate(app, job, resume_data, match_result)
        invite, invite_minted = _ensure_interview_invite(
            candidate["candidate_id"], job["job_id"], application_id
        )
        if candidate_created:
            db.insert_application_event(
                application_id,
                "candidate_created",
                f"candidate_id={candidate['candidate_id']}",
            )
        if invite_minted:
            db.insert_application_event(
                application_id,
                "invite_created",
                f"candidate_id={candidate['candidate_id']}",
            )
        _enqueue_notifications(app, job, candidate, invite,
                               match_result.get("match_score", 0.0))
        db.update_application_status(application_id, "invite_pending")
    else:
        db.update_application_status(application_id, decision)  # rejected | manual_review

    db.update_application_screening_status(application_id, "completed")
    db.complete_screening_job(application_id)
    db.expire_stale_invites()
    db.insert_application_event(
        application_id,
        f"screening_{decision}",
        f"ats={ats:.2f} threshold={threshold:.2f} — {reason}",
    )
    db.insert_application_event(application_id, "screening_completed")

    return {
        "application_id": application_id,
        "decision": decision,
        "reason": reason,
        "ats_score": ats,
        "matched_by": match_result.get("matched_by", ""),
        "hard_requirements_passed": hard["passed"],
        "candidate_id": candidate["candidate_id"] if candidate else None,
        "invite_token": invite.get("token") if invite else None,
    }


def _component_value(scored: dict, name: str):
    comp = scored["components"].get(name)
    return comp["value"] if comp else None


def _confidence(match_result: dict) -> float:
    """Simple confidence heuristic: LLM semantic path ranks higher than pure
    keyword overlap. Classical ML honesty: this is stated as a heuristic, not
    a trained calibration.
    """
    return 0.85 if match_result.get("matched_by") == "llm_semantic" else 0.6


def run_screening_jobs(limit: int = 10) -> list:
    """Claim and process up to `limit` queued screening jobs."""
    processed = []
    for _ in range(limit):
        screening_job = db.claim_next_screening_job()
        if not screening_job:
            break
        app_id = screening_job["application_id"]
        try:
            summary = screen_application(app_id)
            processed.append(summary)
        except Exception as exc:  # pragmatic: worker retries, never crashes the loop
            logger.exception("screening failed for %s", app_id)
            status = db.fail_screening_job(app_id, str(exc))
            db.update_application_screening_status(app_id, status)
            db.insert_application_event(app_id, "screening_failed", str(exc)[:1000])
    return processed