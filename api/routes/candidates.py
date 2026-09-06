import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from api.deps import get_current_recruiter
from api.schemas import CandidateCreate, CandidateResponse, ResendInviteResponse, InterviewStatusResponse
from app.core import db
from app.core.models import Candidate, InterviewInvite
from app.core.paths import get_resumes_dir
from app.screening.service import (
    candidate_screening_status_for,
    persist_candidate_screening_result,
    screen_resume_against_job,
)

router = APIRouter()

RESUME_DIR = get_resumes_dir()

MAX_RESUME_BYTES = 5 * 1024 * 1024


def _ownership_error():
    raise HTTPException(status_code=403, detail="Not your candidate.")


def _with_screening(candidate: dict) -> dict:
    """Attach the canonical screening decision + components so the recruiter
    can see exactly *why* an applicant was shortlisted (explainability).
    Manual candidates (no application row) read the result persisted under
    'manual:<candidate_id>' — the same computation every ingestion path uses."""
    if candidate.get("application_id"):
        result = db.get_screening_result(candidate["application_id"])
        if result:
            return {**candidate, "screening_result": result}
        return candidate
    result = db.get_candidate_screening_result(candidate.get("candidate_id") or "")
    if result:
        return {**candidate, "screening_result": result}
    return candidate


def _no_job_screening() -> dict:
    """The job row should exist for a manual candidate, but degrade gracefully
    if it was deleted. Mirrors the canonical screening dict shape so every
    downstream consumer (persist/UI) needs no special cases."""
    return {
        "ats_score": None,
        "skills_score": None,
        "experience_score": None,
        "semantic_score": None,
        "education_score": None,
        "keyword_score": None,
        "matched_skills": [],
        "missing_skills": [],
        "hard_requirements_passed": True,
        "hard_requirement_failures": [],
        "decision": "manual_review",
        "decision_reason": "No job posting found for this candidate",
        "threshold_used": None,
        "scoring_method": "",
        "matcher_method": "",
        "confidence": 0.0,
    }


@router.get("", response_model=list[CandidateResponse])
def list_candidates(username: str = Depends(get_current_recruiter)):
    cands = db.get_owned_candidates(username)
    return [_with_screening(c) for c in cands]


@router.get("/job/{job_id}", response_model=list[CandidateResponse])
def list_candidates_for_job(job_id: str, username: str = Depends(get_current_recruiter)):
    if not db.job_owned_by(job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")
    cands = db.get_candidates_for_job(job_id)
    return [_with_screening(c) for c in cands]


@router.get("/{candidate_id}/interview-status", response_model=InterviewStatusResponse)
def interview_status(candidate_id: str, username: str = Depends(get_current_recruiter)):
    """Recruiter-facing Mode 2 interview status + question-set summary.

    Derives the high-level state (Not prepared / Ready / In progress /
    Completed) from the session's locked question set and scored answers — no
    live connection needed. Ownership-gated: only the owning recruiter can read
    a candidate's interview status.
    """
    candidate = db.get_owned_candidate(username, candidate_id)
    if not candidate:
        _ownership_error()

    session_id = candidate.get("session_id")
    if not session_id:
        return InterviewStatusResponse(
            candidate_id=candidate_id,
            session_id="",
            interview_status="not_ready",
            locked=False,
            total_questions=0,
            answered_questions=0,
            categories=[],
            candidate_status=candidate.get("status", ""),
        )

    questions = db.get_session_questions(session_id)
    answered = {s["question_id"] for s in db.get_session_scores(session_id)}
    total = len(questions)
    answered_count = sum(1 for q in questions if q["question_id"] in answered)
    categories = sorted({q["category"] for q in questions if q["category"]})

    if candidate.get("status") == "completed" or (total > 0 and answered_count == total):
        status = "completed"
    elif answered_count > 0:
        status = "in_progress"
    elif total > 0:
        status = "ready"
    else:
        status = "not_ready"

    return InterviewStatusResponse(
        candidate_id=candidate_id,
        session_id=session_id,
        interview_status=status,
        locked=total > 0,
        total_questions=total,
        answered_questions=answered_count,
        categories=categories,
        candidate_status=candidate.get("status", ""),
    )


@router.post("", response_model=CandidateResponse)
def create_candidate(req: CandidateCreate, username: str = Depends(get_current_recruiter)):
    if not db.job_owned_by(req.job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")
    if db.get_candidate_by_email_job(req.email, req.job_id):
        raise HTTPException(status_code=409, detail="A candidate for this email already exists for this job.")
    existing = db.get_candidate(req.candidate_id)
    if existing and existing["job_id"] != req.job_id:
        # save_candidate upserts on the candidate_id PK, so honoring a
        # collision against another job would silently repoint (hijack) a
        # candidate that belongs to another recruiter's job. A job has exactly
        # one owner, so any candidate_id reuse across jobs must be rejected.
        raise HTTPException(
            status_code=409,
            detail="Candidate id already exists for another job posting.",
        )
    invite_code = secrets.token_urlsafe(6)
    candidate = Candidate(
        candidate_id=req.candidate_id,
        job_id=req.job_id,
        name=req.name,
        email=req.email,
        invite_code=invite_code,
    )
    db.save_candidate(candidate)

    # A manually invited candidate must actually receive the invitation email,
    # not just appear in the dashboard with a generated code. Mirror the
    # interview-routing / resend paths: mint an active one-time InterviewInvite
    # and enqueue an 'interview_invite' outbox message so the existing email
    # worker delivers the code + join link. This reuses the single
    # outbox/email-worker architecture (no second email system) and keeps a
    # Gmail outage non-blocking — the message simply stays pending and retries.
    email = (candidate.email or "").strip()
    if email:
        invite = InterviewInvite(
            candidate_id=candidate.candidate_id,
            job_id=candidate.job_id,
            application_id=None,
            token=secrets.token_urlsafe(32),
        )
        db.create_interview_invite(invite)
        job = db.get_job_posting(candidate.job_id) or {}
        db.enqueue_notification(
            None,
            candidate.job_id,
            "interview_invite",
            email,
            subject=f"You've been shortlisted for an interview \u2014 {job.get('title', '')}",
            body=invite_code,
            candidate_id=candidate.candidate_id,
        )

    return CandidateResponse(
        candidate_id=candidate.candidate_id,
        job_id=candidate.job_id,
        name=candidate.name,
        email=candidate.email,
        invite_code=invite_code,
        status="invited",
    )


@router.delete("/{candidate_id}")
def delete_candidate(candidate_id: str, username: str = Depends(get_current_recruiter)):
    if not db.get_owned_candidate(username, candidate_id):
        _ownership_error()
    db.delete_candidate(candidate_id)
    return {"success": True}


@router.post("/{candidate_id}/resend", response_model=ResendInviteResponse)
def resend_invite(candidate_id: str, username: str = Depends(get_current_recruiter)):
    candidate = db.get_owned_candidate(username, candidate_id)
    if not candidate:
        _ownership_error()

    new_code = secrets.token_urlsafe(6)
    db.regenerate_invite_code(candidate_id, new_code)

    email = (candidate.get("email") or "").strip()
    if email:
        # Mint a fresh one-time invite and replace the old outbox message so the
        # candidate actually receives the new code by email.
        db.clear_interview_invites(candidate_id)
        fresh_invite = InterviewInvite(
            candidate_id=candidate_id,
            job_id=candidate["job_id"],
            application_id=candidate.get("application_id"),
            token=secrets.token_urlsafe(32),
        )
        db.create_interview_invite(fresh_invite)
        job = db.get_job_posting(candidate["job_id"]) or {}
        db.requeue_resend_notification(
            candidate_id=candidate_id,
            application_id=candidate.get("application_id"),
            job_id=candidate["job_id"],
            notification_type="interview_invite",
            recipient=email,
            subject=f"You've been shortlisted for an interview \u2014 {job.get('title', '')}",
            body=new_code,
        )

    return ResendInviteResponse(
        invite_code=new_code,
        message="New invite code generated and invitation email queued",
    )


@router.post("/{candidate_id}/resume")
async def upload_resume(candidate_id: str, file: UploadFile = File(...),
                        username: str = Depends(get_current_recruiter)):
    candidate = db.get_owned_candidate(username, candidate_id)
    if not candidate:
        _ownership_error()

    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESUME_DIR / f"{candidate_id}_{file.filename}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Resume is empty.")
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="Resume exceeds the 5MB limit.")
    with open(dest, "wb") as f:
        f.write(content)

    from app.engine.resume_parser import parse_resume

    parsed = parse_resume(str(dest))
    job = db.get_job_posting(candidate["job_id"])

    # Run the SAME canonical ATS pipeline as public/Gmail applications and
    # re-screening (screen_resume_against_job on the full _jd_text), store the
    # persisted ScreeningResult under 'manual:<candidate_id>', and mirror the
    # authoritative ats_score back onto candidates.match_score. One canonical
    # result per candidate regardless of how they were ingested.
    screening = screen_resume_against_job(parsed, job) if job else _no_job_screening()

    db.save_candidate_resume(
        candidate_id,
        str(dest),
        parsed.get("skills", []),
        parsed.get("experience_years"),
        screening["ats_score"] or 0.0,
        screening["matched_skills"],
        screening["missing_skills"],
    )
    db.update_candidate_screening_status(
        candidate_id, candidate_screening_status_for(screening["decision"])
    )
    persist_candidate_screening_result(candidate_id, screening)

    updated = db.get_owned_candidate(username, candidate_id)
    if updated:
        return _with_screening(updated)
    return {
        "candidate_id": candidate_id,
        **{k: candidate.get(k) for k in ("job_id", "name", "email", "invite_code", "status")},
        "resume_path": str(dest),
        "resume_skills": parsed.get("skills", []),
        "experience_years": parsed.get("experience_years"),
        "match_score": screening["ats_score"] or 0.0,
        "matched_skills": screening["matched_skills"],
        "missing_skills": screening["missing_skills"],
        "invite_email_sent": False,
    }