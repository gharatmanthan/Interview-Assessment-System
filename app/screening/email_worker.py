"""
Email worker: drains app/screening 'notification_outbox' asynchronously via
Gmail. Gmail being unavailable is NOT a failure of the application/screening
transaction — messages simply stay pending and are retried later.

Notification types:
  * 'interview_invite' -> the shortlisted candidate's timed interview invite
  * 'hr_shortlist'     -> a shortlist digest to the recruiter's HR inbox

Maximum attempts before a message is marked failed (so operators can see a
genuinely stuck message instead of infinite retries).
"""
import base64
import logging
from email.mime.text import MIMEText

from app.core import db
from app.core.settings_store import load_settings
from app.engine.email_intake import compose_invite_email, get_gmail_service

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_ATTEMPTS = 3


def _frontend_url() -> str:
    settings = load_settings()
    if settings.get("backend_mode") == "remote":
        return settings.get("remote_api_url", "")
    return ""


def compose_hr_shortlist_email(candidate: dict, job: dict, ats_score=None) -> dict:
    """Compose the HR shortlist notification (separate template for editing)."""
    subject = f"Shortlist: {candidate.get('name')} for {job.get('title', '')}"
    lines = [
        f"Candidate: {candidate.get('name')}",
        f"Email: {candidate.get('email')}",
        f"Position: {job.get('title', '')}",
    ]
    if ats_score is not None:
        lines.append(f"ATS score: {ats_score:.1f}/100")
    lines.append("\nReview the full application in the recruiter dashboard.")
    return {"subject": subject, "body": "\n".join(lines)}


def _send_gmail(notification: dict) -> None:
    """Compose + send one outbox message via Gmail. Raises on failure."""
    settings = load_settings()
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail not connected — message stays pending")

    candidate = db.get_candidate(notification.get("candidate_id")) if notification.get("candidate_id") else None
    job = db.get_job_posting(notification.get("job_id")) if notification.get("job_id") else None
    if not job:
        raise RuntimeError("job lookup failed when composing email")

    if notification["notification_type"] == "interview_invite":
        if not candidate:
            raise RuntimeError("candidate lookup failed for interview invite")
        invite_code = candidate["invite_code"]
        scheduled_at = None
        try:
            from app.engine import scheduling
            allocated = scheduling.allocate_next_slot(candidate["candidate_id"], job["job_id"])
            if "error" not in allocated and allocated.get("scheduled_at"):
                scheduled_at = allocated["scheduled_at"]
        except Exception as exc:  # best-effort: calendar must never block the invite
            logger.warning("auto-booking failed for %s: %s", candidate["candidate_id"], exc)

        msg = compose_invite_email(
            {"name": candidate["name"], "email": candidate["email"]},
            {"title": job["title"]},
            invite_code,
            _frontend_url(),
            scheduled_at,
        )
        subject = f"You've been shortlisted for an interview \u2014 {job['title']}"
    else:  # hr_shortlist
        app_id = notification.get("application_id")
        result = db.get_screening_result(app_id) if app_id else None
        ats = result.get("ats_score") if result else None
        content = compose_hr_shortlist_email(
            candidate or {"name": "", "email": notification.get("recipient", "")},
            job,
            ats,
        )
        msg = MIMEText(content["body"])
        subject = content["subject"]

    msg["Subject"] = subject
    msg["To"] = notification["recipient"]
    msg["From"] = settings.get("gmail_user", "")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()

    if notification["notification_type"] == "interview_invite" and candidate:
        db.update_candidate_invite_email_sent(candidate["candidate_id"], True)


def send_pending_notifications(limit: int = 20) -> list:
    """Attempt to send up to `limit` pending outbox messages. Returns the ids
    of messages sent. Failed messages are retried until MAX_NOTIFICATION_ATTEMPTS.

    Each message is atomically claimed as 'sending' before it is handed to
    Gmail, so a concurrent worker (or a retry after a crash between the Gmail
    send and the DB 'sent' mark) can never grab the same message and send a
    duplicate. Messages left 'sending' by a crashed worker are reclaimed as
    pending (still respecting the attempt cap).

    Gmail-disconnected is a transient condition, NOT a send failure: when no
    service is available we return immediately without consuming attempts, so
    a temporary outage never permanently fails the outbox.
    """
    try:
        if get_gmail_service() is None:
            return []
    except Exception as exc:
        logger.warning("Gmail service probe failed: %s", exc)
        return []

    db.reclaim_stale_sending_notifications()

    sent = []
    for _ in range(limit):
        notification = db.claim_pending_notification()
        if not notification:
            break
        try:
            _send_gmail(notification)
        except Exception as exc:
            logger.warning("notification %s failed (%s)", notification["id"], exc)
            db.mark_notification_failed(notification["id"], str(exc))
            continue
        db.mark_notification_sent(notification["id"])
        sent.append(notification["id"])
    return sent