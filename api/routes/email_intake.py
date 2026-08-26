from fastapi import APIRouter, HTTPException
from api.schemas import EmailCheckRequest, EmailCheckResponse, PollLogResponse
from app.engine.email_intake import check_for_new_applications
from app.core import db

router = APIRouter()


@router.post("/check", response_model=EmailCheckResponse)
def trigger_email_check(req: EmailCheckRequest):
    """Manually trigger the email intake pipeline for a specific job posting."""
    job = db.get_job_posting(req.job_id)
    results = check_for_new_applications(req.job_id)
    invited = sum(1 for r in results if r.get("status") == "invited")
    below = sum(1 for r in results if r.get("status") == "below_threshold")
    skipped = sum(1 for r in results if r.get("status") in ("skipped", "error"))
    failed = sum(1 for r in results if r.get("status") == "invite_send_failed")
    total = len(results)
    summary = f"{total} checked, {invited} invited, {below} below threshold, {skipped} skipped"
    if failed:
        summary += f", {failed} invite sends failed"
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
def get_poll_logs():
    """Return the most recent background poll run logs."""
    logs = db.get_poll_logs(limit=50)
    return PollLogResponse(logs=logs)
