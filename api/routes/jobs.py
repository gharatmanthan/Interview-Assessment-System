from fastapi import APIRouter
from api.schemas import JobPostingCreate, JobPostingResponse
from app.core import db
from app.core.models import JobPosting
from datetime import datetime

router = APIRouter()


@router.get("", response_model=list[JobPostingResponse])
def list_jobs():
    return db.get_all_job_postings()


@router.post("", response_model=JobPostingResponse)
def create_job(req: JobPostingCreate):
    job = JobPosting(
        job_id=req.job_id,
        title=req.title,
        description=req.description,
        required_skills=req.required_skills,
        experience_level=req.experience_level,
        department=req.department,
        num_rounds=req.num_rounds,
        time_limit_seconds=req.time_limit_seconds,
        adaptive_difficulty=req.adaptive_difficulty,
        competency_weights=req.competency_weights,
    )
    db.save_job_posting(job)
    return req


@router.put("/{job_id}", response_model=JobPostingResponse)
def update_job(job_id: str, req: JobPostingCreate):
    job = JobPosting(
        job_id=job_id,
        title=req.title,
        description=req.description,
        required_skills=req.required_skills,
        experience_level=req.experience_level,
        department=req.department,
        num_rounds=req.num_rounds,
        time_limit_seconds=req.time_limit_seconds,
        adaptive_difficulty=req.adaptive_difficulty,
        competency_weights=req.competency_weights,
    )
    db.save_job_posting(job)
    return req


@router.delete("/{job_id}")
def delete_job(job_id: str):
    db.delete_job_posting(job_id)
    return {"success": True}
