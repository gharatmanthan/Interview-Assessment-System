import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from api.deps import get_current_recruiter
from api.schemas import CandidateCreate, CandidateResponse, ResendInviteResponse
from app.core import db
from app.core.models import Candidate, InterviewInvite

router = APIRouter()

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"

MAX_RESUME_BYTES = 5 * 1024 * 1024


def _ownership_error():
    raise HTTPException(status_code=403, detail="Not your candidate.")


def _with_screening(candidate: dict) -> dict:
    """Attach the screening decision + components so the recruiter can see
    exactly *why* an applicant was shortlisted (explainability)."""
    if candidate.get("application_id"):
        result = db.get_screening_result(candidate["application_id"])
        if result:
            return {**candidate, "screening_result": result}
    return candidate


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


@router.post("", response_model=CandidateResponse)
def create_candidate(req: CandidateCreate, username: str = Depends(get_current_recruiter)):
    if not db.job_owned_by(req.job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")
    invite_code = secrets.token_urlsafe(6)
    candidate = Candidate(
        candidate_id=req.candidate_id,
        job_id=req.job_id,
        name=req.name,
        email=req.email,
        invite_code=invite_code,
    )
    db.save_candidate(candidate)
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
    from app.engine.jd_matcher import match_resume_to_jd

    parsed = parse_resume(str(dest))
    job = db.get_job_posting(candidate["job_id"])
    match_result = {"match_score": 0, "matched_skills": [], "missing_skills": []}
    if job:
        match_result = match_resume_to_jd(parsed, job.get("description", ""))

    db.save_candidate_resume(
        candidate_id,
        str(dest),
        parsed.get("skills", []),
        parsed.get("experience_years"),
        match_result.get("match_score", 0),
        match_result.get("matched_skills", []),
        match_result.get("missing_skills", []),
    )

    updated = db.get_owned_candidate(username, candidate_id)
    if updated:
        return updated
    return {
        "candidate_id": candidate_id,
        **{k: candidate.get(k) for k in ("job_id", "name", "email", "invite_code", "status")},
        "resume_path": str(dest),
        "resume_skills": parsed.get("skills", []),
        "experience_years": parsed.get("experience_years"),
        "match_score": match_result.get("match_score", 0),
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
        "invite_email_sent": False,
    }