"""
Email worker: drains app/screening 'notification_outbox' asynchronously via
Gmail. Gmail being unavailable is NOT a failure of the application/screening
transaction — messages simply stay pending and are retried later.

Notification types:
  * 'interview_invite'  -> Mode 1 timed invite (legacy path, e.g. resend flow)
                            auto-books a live-interview slot on send
  * 'mode1_invite'      -> Mode 1 direct invite (AUTO / MODE_1_ONLY cohorts)
                            auto-books a live-interview slot on send
  * 'mode2_invite'      -> Mode 2 self-serve interview invite (no slot)
  * 'mode1_promotion'   -> Mode 2 -> Mode 1 promotion invite (auto-books)
  * 'not_selected'      -> candidate not promoted after Mode 2 (no slot)
  * 'hr_shortlist'      -> a shortlist digest to the recruiter's HR inbox

Maximum attempts before a message is marked failed (so operators can see a
genuinely stuck message instead of infinite retries).
"""
import base64
import logging
from email.mime.text import MIMEText

from app.core import db
from app.core.settings_store import frontend_base_url, load_settings
from app.engine.email_intake import (
    compose_invite_email,
    compose_mode2_invite_email,
    compose_not_selected_email,
    compose_promotion_email,
    get_gmail_service,
)

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_ATTEMPTS = 3


def _frontend_url() -> str:
    # Candidate-facing invite links must always point at the frontend origin
    # (PUBLIC_APP_URL) which serves /candidate/entry — never at remote_api_url
    # (the API origin, which does not serve the Next.js routes).
    return frontend_base_url()


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


def _allocated_slot(candidate, job) -> object:
    """Best-effort live-interview slot allocation. Returns the scheduled_at
    (or None) — the calendar must never block an invite from sending."""
    try:
        from app.engine import scheduling
        allocated = scheduling.allocate_next_slot(candidate["candidate_id"], job["job_id"])
        if "error" not in allocated and allocated.get("scheduled_at"):
            return allocated["scheduled_at"]
    except Exception as exc:
        logger.warning(
            "auto-booking failed for %s: %s", candidate["candidate_id"], exc
        )
    return None


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

    ntype = notification["notification_type"]
    auto_book = ntype in ("interview_invite", "mode1_invite", "mode1_promotion")

    if auto_book:
        if not candidate:
            raise RuntimeError("candidate lookup failed for mode 1 invite")
        invite_code = candidate["invite_code"]
        scheduled_at = _allocated_slot(candidate, job)
        if ntype == "mode1_promotion":
            msg = compose_promotion_email(
                {"name": candidate["name"], "email": candidate["email"]},
                {"title": job["title"]},
                invite_code,
                _frontend_url(),
                scheduled_at,
            )
            subject = f"You've advanced to the final round \u2014 {job['title']}"
        else:
            msg = compose_invite_email(
                {"name": candidate["name"], "email": candidate["email"]},
                {"title": job["title"]},
                invite_code,
                _frontend_url(),
                scheduled_at,
            )
            subject = f"You've been shortlisted for an interview \u2014 {job['title']}"
    elif ntype == "mode2_invite":
        if not candidate:
            raise RuntimeError("candidate lookup failed for mode 2 invite")
        msg = compose_mode2_invite_email(
            {"name": candidate["name"], "email": candidate["email"]},
            {"title": job["title"]},
            candidate["invite_code"],
            _frontend_url(),
        )
        subject = f"Your self-serve interview \u2014 {job['title']}"
    elif ntype == "not_selected":
        if not candidate:
            raise RuntimeError("candidate lookup failed for not-selected email")
        msg = compose_not_selected_email(
            {"name": candidate["name"], "email": candidate["email"]},
            {"title": job["title"]},
        )
        subject = f"Update on your application \u2014 {job['title']}"
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

    if ntype in ("interview_invite", "mode1_invite", "mode2_invite",
                 "mode1_promotion") and candidate:
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