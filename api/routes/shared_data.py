"""Shared candidate and job data endpoints for desktop clients."""
from fastapi import APIRouter, HTTPException, status

from api import persistence as db
from api.schemas import CandidateAccountRequest, CandidateCredentials, JobPostingRequest

router = APIRouter(tags=["shared-data"])


@router.get("/candidates")
def list_candidates() -> list[dict]:
    return db.get_candidate_accounts()


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
def create_candidate(payload: CandidateAccountRequest) -> dict[str, str]:
    if not db.create_candidate_account(
        payload.candidate_id, payload.password, payload.full_name
    ):
        raise HTTPException(status_code=409, detail="Candidate already exists.")
    return {"candidate_id": payload.candidate_id, "full_name": payload.full_name}


@router.post("/candidates/auth")
def authenticate_candidate(payload: CandidateCredentials) -> dict:
    account = db.authenticate_candidate(payload.candidate_id, payload.password)
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid candidate credentials.")
    return account


@router.get("/jobs")
def list_jobs() -> list[dict]:
    return db.get_active_job_postings()


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobPostingRequest) -> dict[str, str]:
    db.save_job_posting(payload.title, payload.description)
    return {"title": payload.title, "description": payload.description}
