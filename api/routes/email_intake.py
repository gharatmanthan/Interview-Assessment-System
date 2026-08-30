from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_current_recruiter
from api.schemas import EmailCheckRequest, EmailCheckResponse, PollLogResponse
from app.engine.email_intake import (
    check_for_new_applications,
    summarize_poll_results,
)
from app.core import db

router = APIRouter()


@router.post("/check", response_model=EmailCheckResponse)
def trigger_email_check(req: EmailCheckRequest, username: str = Depends(get_current_recruiter)):
    """Manually trigger the email intake pipeline for a job posting you own."""
    job = db.get_job_posting(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    if not db.job_owned_by(req.job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")
    results = check_for_new_applications(req.job_id)
    invited, below, skipped, failed = summarize_poll_results(results)
    total = len(results)
    summary = f"{total} checked, {invited} invited, {below} not shortlisted, {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    if total > 0:
        db.save_poll_log(
            job_id=req.job_id,
            job_title=job["title"] if job else req.job_id,
            total=total,
            invited=invited,
            below_threshold=below,
            skipped=skipped,
            failed=failed,
            mode="manual",
        )
    return EmailCheckResponse(results=results, summary=summary)


@router.get("/poll-logs", response_model=PollLogResponse)
def get_poll_logs(username: str = Depends(get_current_recruiter)):
    """Return the most recent poll logs, scoped to the recruiter's own jobs."""
    owned = {j["job_id"] for j in db.get_owned_jobs(username)}
    logs = [log for log in db.get_poll_logs(limit=50) if log["job_id"] in owned]
    return PollLogResponse(logs=logs)