"""
Applications + screening results + outbox status — the recruiter's view
of the candidate-first pipeline. All reads are ownership-scoped to the
authenticated recruiter's jobs.
"""
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_recruiter
from api.routes.media import to_relative_media_path
from api.schemas import (
    ApplicationDetailResponse,
    ApplicationListResponse,
    ScreeningResultResponse,
    NotificationOutboxResponse,
    JobPipelineStatsResponse,
)
from app.core import db

router = APIRouter()


def _ensure_job_owned(job_id: str, username: str):
    if not db.job_owned_by(job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")


def _detail_row(app: dict, username: str) -> dict:
    result = db.get_screening_result(app["application_id"])
    notifications = db.get_notifications_for_application(app["application_id"])
    return {
        "application_id": app["application_id"],
        "job_id": app["job_id"],
        "full_name": app["full_name"],
        "email": app["email"],
        "phone": app["phone"],
        "resume_path": to_relative_media_path(app["resume_path"] or ""),
        "source": app["source"],
        "status": app["status"],
        "screening_status": app["screening_status"],
        "candidate_id": app["candidate_id"],
        "submitted_at": app["submitted_at"],
        "updated_at": app["updated_at"],
        "screening_result": ScreeningResultResponse(**result).model_dump() if result else None,
        "notifications": [NotificationOutboxResponse(**n).model_dump() for n in notifications],
        "events": db.get_application_events(app["application_id"]),
    }


@router.get("/stats", response_model=JobPipelineStatsResponse)
def pipeline_stats(
    username: str = Depends(get_current_recruiter),
):
    return JobPipelineStatsResponse(jobs=db.get_job_pipeline_stats(username))


@router.get("", response_model=ApplicationListResponse)
def list_applications(
    job_id: str | None = None,
    username: str = Depends(get_current_recruiter),
):
    if job_id:
        _ensure_job_owned(job_id, username)
        apps = db.get_applications_for_job(job_id)
    else:
        apps = db.get_owned_applications(username)
    return ApplicationListResponse(
        applications=[_detail_row(a, username) for a in apps]
    )


@router.post("/{application_id}/rescreen")
def rescreen_application(
    application_id: str,
    username: str = Depends(get_current_recruiter),
):
    """Explicit re-screen after a threshold/config change: requeues the job;
    the worker recomputes a fresh result (latest result replaces the prior one;
    the decision history is preserved in the application_events audit trail)."""
    app = db.get_application(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    _ensure_job_owned(app["job_id"], username)
    if app.get("screening_status") in ("queued", "processing"):
        raise HTTPException(
            status_code=409, detail="Screening already queued or in progress."
        )
    db.requeue_screening(application_id)
    db.update_application_screening_status(application_id, "queued")
    db.update_application_status(application_id, "screening")
    db.insert_application_event(application_id, "screening_requeued")
    return {
        "success": True,
        "application_id": application_id,
        "screening_status": "queued",
    }


@router.get("/{application_id}", response_model=ApplicationDetailResponse)
def get_application_detail(
    application_id: str,
    username: str = Depends(get_current_recruiter),
):
    app = db.get_application(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    _ensure_job_owned(app["job_id"], username)
    return _detail_row(app, username)