from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_current_recruiter
from api.schemas import JobPostingCreate, JobPostingResponse
from app.core import db
from app.core.models import JobPosting

router = APIRouter()


def _owns_job(job_id: str, username: str):
    if not db.job_owned_by(job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")


@router.get("", response_model=list[JobPostingResponse])
def list_jobs(username: str = Depends(get_current_recruiter)):
    """Owned jobs only (authorization root)."""
    return db.get_owned_jobs(username)


@router.post("", response_model=JobPostingResponse)
def create_job(req: JobPostingCreate, username: str = Depends(get_current_recruiter)):
    # The backend owns the canonical job id. A caller may propose an id for a
    # brand-new job, but it is rejected the moment colleague work already holds
    # that id: job_postings is INSERT OR REPLACE keyed on job_id and ownership
    # is rooted on created_by, so honoring a colliding id on create would let a
    # caller clobber another recruiter's job and take it over. Blank ids get a
    # server-generated id; updates go through the ownership-checked PUT below.
    job_id = (req.job_id or "").strip()
    if job_id:
        if db.get_job_posting(job_id):
            raise HTTPException(
                status_code=409,
                detail="A job posting with this id already exists.",
            )
    else:
        job_id = db.generate_job_id()
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
        screening_threshold=req.screening_threshold,
        application_gmail_label=req.application_gmail_label,
        screening_enabled=req.screening_enabled,
        auto_invite_enabled=req.auto_invite_enabled,
        minimum_experience_years=req.minimum_experience_years,
        required_education=req.required_education,
        screening_weights=req.screening_weights,
        created_by=username,
    )
    db.save_job_posting(job)
    return db.get_job_posting(job_id)


@router.put("/{job_id}", response_model=JobPostingResponse)
def update_job(job_id: str, req: JobPostingCreate, username: str = Depends(get_current_recruiter)):
    _owns_job(job_id, username)
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
        screening_threshold=req.screening_threshold,
        application_gmail_label=req.application_gmail_label,
        screening_enabled=req.screening_enabled,
        auto_invite_enabled=req.auto_invite_enabled,
        minimum_experience_years=req.minimum_experience_years,
        required_education=req.required_education,
        screening_weights=req.screening_weights,
        created_by=username,
    )
    db.save_job_posting(job)
    return db.get_job_posting(job_id)


@router.delete("/{job_id}")
def delete_job(job_id: str, username: str = Depends(get_current_recruiter)):
    _owns_job(job_id, username)
    db.delete_job_posting(job_id)
    return {"success": True}