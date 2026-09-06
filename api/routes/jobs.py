from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_recruiter
from api.schemas import (
    JobPostingCreate,
    JobPostingResponse,
    JobStrategyConfirmRequest,
    JobStrategyStatusResponse,
    LinkedInPreviewResponse,
    LinkedInPublishRequest,
    LinkedInPublishResponse,
)
from app.core import db
from app.core.models import JobPosting
from app.core.settings_store import public_apply_url
from app.engine import linkedin
from app.engine.linkedin_post import generate_linkedin_post

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


def _job_strategy_status(job_id: str) -> JobStrategyStatusResponse:
    """Map the DB cohort status into the recruiter-facing strategy response."""
    status = db.get_job_cohort_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStrategyStatusResponse(
        job_id=job_id,
        screening_pending=status.get("screening_pending", 0),
        shortlisted=status.get("shortlisted", 0),
        cohort_finalized=bool(status.get("cohort_finalized")),
        recommended_strategy=status.get("recommended_strategy", "AUTO"),
        interview_strategy=status.get("interview_strategy", "AUTO"),
        strategy_confirmed=bool(status.get("strategy_confirmed")),
        strategy_confirmed_at=status.get("strategy_confirmed_at"),
        cohort_finalized_at=status.get("cohort_finalized_at"),
        interview_capacity=6,
    )


@router.get("/{job_id}/interview-mode/status", response_model=JobStrategyStatusResponse)
def interview_mode_status(
    job_id: str, username: str = Depends(get_current_recruiter)
):
    """Current interview-mode routing status: cohort progress, the AUTO
    recommendation, and whether the strategy has been confirmed."""
    _owns_job(job_id, username)
    from app.screening.routing import finalize_cohort_if_ready

    # Re-deriving the recommendation here keeps the status fresh even when the
    # worker was down during the last screening pass; it is a no-op once the
    # cohort is already finalized.
    finalize_cohort_if_ready(job_id)
    return _job_strategy_status(job_id)


@router.post("/{job_id}/interview-mode/confirm", response_model=JobStrategyStatusResponse)
def confirm_interview_mode(
    job_id: str,
    req: JobStrategyConfirmRequest,
    username: str = Depends(get_current_recruiter),
):
    """Confirm the job's interview strategy. This is the gate that releases
    candidate invitations: until it succeeds, no candidate has been emailed a
    mode invite. Refuses to run while the screening cohort is still draining."""
    _owns_job(job_id, username)
    from app.screening.routing import confirm_strategy

    try:
        confirm_strategy(job_id, req.strategy or "AUTO")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _job_strategy_status(job_id)


@router.post("/{job_id}/linkedin/preview", response_model=LinkedInPreviewResponse)
def linkedin_preview(job_id: str, username: str = Depends(get_current_recruiter)):
    """Deterministic, recruiter-editable draft plus the public apply URL and the
    current publication state. Never calls LinkedIn — works offline."""
    job = db.get_job_posting(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    _owns_job(job_id, username)
    conn = db.get_linkedin_connection(username)
    return LinkedInPreviewResponse(
        job_id=job_id,
        content=generate_linkedin_post(job, public_apply_url(job_id)),
        public_url=public_apply_url(job_id),
        linkedin_post_status=job.get("linkedin_post_status", "NOT_POSTED"),
        connected=bool(conn),
    )


@router.post("/{job_id}/linkedin/publish", response_model=LinkedInPublishResponse)
def linkedin_publish(
    job_id: str,
    req: LinkedInPublishRequest,
    username: str = Depends(get_current_recruiter),
):
    """Publish the (editable) commentary to the recruiter's LinkedIn feed.

    Post-once rules live in the DB: PUBLISHED jobs refuse republish; a fresh
    PUBLISHING claim blocks concurrent/double clicks. On a definitive LinkedIn
    rejection the job lands in FAILED (retry allowed); on a transport timeout
    it stays PUBLISHING because the post may have been accepted — the caller
    must verify on LinkedIn before retrying (stale claims auto-expire)."""
    job = db.get_job_posting(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    _owns_job(job_id, username)

    conn = db.get_linkedin_connection(username)
    if conn is None:
        raise HTTPException(status_code=409, detail="Connect your LinkedIn account first.")

    status = job.get("linkedin_post_status", "NOT_POSTED")
    if status == linkedin.LinkedInPostStatus.PUBLISHED:
        raise HTTPException(
            status_code=409,
            detail="This job is already posted on LinkedIn.",
        )

    content = (req.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Post content must not be empty.")
    if len(content) > linkedin.MAX_POST_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Post content must be at most {linkedin.MAX_POST_CHARS} characters.",
        )

    if not linkedin.is_configured():
        raise HTTPException(status_code=503, detail="LinkedIn app is not configured.")

    allowed_from = (linkedin.LinkedInPostStatus.NOT_POSTED,
                    linkedin.LinkedInPostStatus.DRAFT,
                    linkedin.LinkedInPostStatus.FAILED)
    if not db.try_claim_linkedin_publish(job_id, allowed_from):
        # Fresh PUBLISHING claims are rejected here; only a stale (crashed)
        # claim is reclaimed inside try_claim_linkedin_publish.
        raise HTTPException(status_code=409, detail="Another publish is in progress for this job.")

    author_urn = linkedin.member_author_urn(conn["linkedin_member_id"])
    try:
        post_id = linkedin.create_post(conn["access_token"], author_urn, content)
    except linkedin.LinkedInTimeoutError:
        # Do NOT mark FAILED: a duplicate post is worse than a manual check.
        # linkedin_claim_started_at frees the claim after the stale window.
        raise HTTPException(
            status_code=502,
            detail="LinkedIn did not respond in time. The post may have been "
                   "accepted — verify on LinkedIn before retrying.",
        )
    except linkedin.LinkedInError as exc:
        safe = _safe_publish_error(exc)
        db.set_job_linkedin_post(
            job_id, status=linkedin.LinkedInPostStatus.FAILED, last_error=safe,
        )
        raise HTTPException(status_code=502, detail=safe)

    post_url = linkedin.post_feed_url(post_id)
    db.set_job_linkedin_post(
        job_id, status=linkedin.LinkedInPostStatus.PUBLISHED,
        post_id=post_id, post_url=post_url,
        posted_at=linkedin.utc_now_iso(), author_urn=author_urn,
    )
    return LinkedInPublishResponse(
        success=True,
        job_id=job_id,
        linkedin_post_status=linkedin.LinkedInPostStatus.PUBLISHED,
        post_id=post_id,
        post_url=post_url,
    )


def _safe_publish_error(exc: linkedin.LinkedInError) -> str:
    """Map LinkedIn failures to a recruiter-safe message (never tokens)."""
    status = exc.status
    if status in (401, 403):
        return "LinkedIn rejected your credentials or permissions. Reconnect your LinkedIn account and retry."
    if status == 429:
        return "LinkedIn is rate-limiting requests. Wait a bit and retry."
    if status is not None and status >= 500:
        return "LinkedIn is having issues right now. Try again shortly."
    return exc.message or "LinkedIn rejected the post."