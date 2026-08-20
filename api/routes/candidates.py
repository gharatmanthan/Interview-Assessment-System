import secrets
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File
from api.schemas import CandidateCreate, CandidateResponse, ResendInviteResponse
from app.core import db
from app.core.models import Candidate
from datetime import datetime

router = APIRouter()

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"


@router.get("", response_model=list[CandidateResponse])
def list_candidates():
    return db.get_all_candidates()


@router.get("/job/{job_id}", response_model=list[CandidateResponse])
def list_candidates_for_job(job_id: str):
    return db.get_candidates_for_job(job_id)


@router.post("", response_model=CandidateResponse)
def create_candidate(req: CandidateCreate):
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
def delete_candidate(candidate_id: str):
    db.delete_candidate(candidate_id)
    return {"success": True}


@router.post("/{candidate_id}/resend", response_model=ResendInviteResponse)
def resend_invite(candidate_id: str):
    new_code = secrets.token_urlsafe(6)
    db.regenerate_invite_code(candidate_id, new_code)
    return ResendInviteResponse(invite_code=new_code, message="New invite code generated")


@router.post("/{candidate_id}/resume")
async def upload_resume(candidate_id: str, file: UploadFile = File(...)):
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESUME_DIR / f"{candidate_id}_{file.filename}"
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    from app.engine.resume_parser import parse_resume
    from app.engine.jd_matcher import match_resume_to_jd

    parsed = parse_resume(str(dest))

    candidates = db.get_all_candidates()
    candidate = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
    match_result = {"match_score": 0, "matched_skills": [], "missing_skills": []}
    if candidate:
        jobs = db.get_all_job_postings()
        job = next((j for j in jobs if j["job_id"] == candidate["job_id"]), None)
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

    updated_candidates = db.get_all_candidates()
    updated = next((c for c in updated_candidates if c["candidate_id"] == candidate_id), None)
    if updated:
        return updated
    return {
        "candidate_id": candidate_id,
        "job_id": candidate["job_id"] if candidate else "",
        "name": candidate["name"] if candidate else "",
        "email": candidate["email"] if candidate else "",
        "invite_code": candidate["invite_code"] if candidate else "",
        "status": candidate["status"] if candidate else "invited",
        "resume_path": str(dest),
        "resume_skills": parsed.get("skills", []),
        "experience_years": parsed.get("experience_years"),
        "match_score": match_result.get("match_score", 0),
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
    }
