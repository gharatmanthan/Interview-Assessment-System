"""
Email intake pipeline — watches a Gmail label for job applications,
screens resumes, and auto-invites qualified candidates.

Reuses the existing resume_parser.py + jd_matcher.py pipeline unchanged;
this module only adds the Gmail layer around it.
"""
import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core import db
from app.core.models import ProcessedEmail
from app.core.oauth_client import CLIENT_SECRET_PATH, load_oauth_credentials
from app.core.settings_store import load_settings, save_settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.labels",
]

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"


def get_gmail_service():
    """Build a Gmail API service from the stored refresh token, using the
    OAuth client config from data/client_secret.json (single source of truth).
    Returns None if Gmail is not connected or the token/client cannot load.
    """
    settings = load_settings()
    if not settings.get("gmail_connected") or not settings.get("gmail_refresh_token"):
        return None
    creds = load_oauth_credentials(settings.get("gmail_refresh_token", ""))
    if creds is None:
        return None
    return build("gmail", "v1", credentials=creds)


def run_oauth_flow():
    """Run the OAuth consent flow and store the resulting credentials.
    Persists only the refresh token + account markers; the OAuth client
    config stays in data/client_secret.json. Returns the connected email
    address on success, raises on failure.
    """
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"OAuth client_secret.json not found at {CLIENT_SECRET_PATH}. "
            "Download it from Google Cloud Console and place it in data/."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    save_settings({
        "gmail_connected": True,
        "gmail_user": email,
        "gmail_refresh_token": creds.refresh_token,
    })
    return email


def disconnect_gmail():
    """Clear stored Gmail credentials."""
    save_settings({
        "gmail_connected": False,
        "gmail_user": "",
        "gmail_refresh_token": "",
    })


def compose_invite_email(candidate: dict, job: dict, invite_code: str,
                         frontend_url: str = "",
                         scheduled_at=None) -> MIMEText:
    """Compose a professional invite email for a shortlisted candidate.

    Kept as a separate template function so wording can be edited without
    touching the sending logic.

    If `scheduled_at` is provided (a datetime), the interview date is included
    so the candidate knows when to attend.
    """
    subject = f"You've been shortlisted for an interview \u2014 {job['title']}"

    if scheduled_at is not None:
        if getattr(scheduled_at, "tzinfo", None) is None:
            from datetime import timezone
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        from datetime import datetime as _dt
        try:
            local = scheduled_at.astimezone()
            date_str = local.strftime("%A, %B %d, %Y at %I:%M %p")
        except Exception:
            date_str = str(scheduled_at)
        schedule_line = (
            f"\n\nYour interview is scheduled for: {date_str}\n"
            "Please be ready a few minutes beforehand with your webcam and microphone enabled."
        )
    else:
        schedule_line = ""

    if frontend_url:
        link = f"{frontend_url}/candidate/entry?code={invite_code}"
        body = (
            f"Dear {candidate['name']},\n\n"
            f"Congratulations! You have been shortlisted for the {job['title']} position."
            f"{schedule_line}\n\n"
            f"Your interview invite code is: {invite_code}\n\n"
            f"To begin your interview, click the link below and enter your code:\n"
            f"{link}\n\n"
            f"If the link doesn't work, you can also enter the code manually at the interview entry page.\n\n"
            f"Best regards,\nInterviewIQ Automated Screening"
        )
    else:
        body = (
            f"Dear {candidate['name']},\n\n"
            f"Congratulations! You have been shortlisted for the {job['title']} position."
            f"{schedule_line}\n\n"
            f"Your interview invite code is: {invite_code}\n\n"
            f"Download the InterviewIQ app and enter this code to begin your interview.\n\n"
            f"Best regards,\nInterviewIQ Automated Screening"
        )

    return MIMEText(body)


def _extract_sender(message: dict) -> tuple[str, str]:
    """Extract sender name and email from Gmail message headers."""
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    from_header = headers.get("from", "")
    if "<" in from_header and ">" in from_header:
        name = from_header.split("<")[0].strip().strip('"')
        email = from_header.split("<")[1].rstrip(">")
    else:
        name = from_header
        email = from_header
    return name, email


def _find_resume_attachment(payload: dict) -> Optional[dict]:
    """Recursively find the first PDF/DOCX/TXT attachment in a Gmail message payload."""
    parts = payload.get("parts", [])
    if not parts:
        mime = payload.get("mimeType", "")
        filename = payload.get("filename", "")
        if filename and mime in (
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
        ):
            return payload
        return None
    for part in parts:
        result = _find_resume_attachment(part)
        if result is not None:
            return result
    return None


def _download_attachment(service, message_id: str, attachment_part: dict) -> Optional[bytes]:
    """Download the body data of a Gmail attachment part."""
    body = attachment_part.get("body", {})
    data = body.get("data")
    if data:
        return base64.urlsafe_b64decode(data)
    attachment_id = body.get("attachmentId")
    if attachment_id:
        att = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        return base64.urlsafe_b64decode(att["data"])
    return None


def _extension_for_mime(mime_type: str) -> str:
    """Map MIME type to file extension."""
    return {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt",
    }.get(mime_type, ".bin")


def _mark_as_read_and_label(service, message_id: str):
    """Mark a Gmail message as read and apply a 'Processed' label."""
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"], "addLabelIds": []},
        ).execute()
    except Exception as e:
        logger.warning("Failed to mark message %s as read: %s", message_id, e)


def check_for_new_applications(job_id: str) -> list[dict]:
    """For the given job posting's configured Gmail label:
    1. List messages in that label, excluding already-processed message IDs
    2. For each: extract sender, download resume attachment
    3. Store the application and QUEUE screening (async). Gmail sends are
       deferred to the outbox worker, so Gmail problems never lose an
       applicant's record.
    4. Mark message as read
    5. Record in ProcessedEmail regardless of outcome

    Returns a summary list of what was processed.
    """
    from app.screening.service import (
        DuplicateApplicationError,
        create_application_and_queue,
        screen_application,
    )

    job = db.get_job_posting(job_id)
    if not job:
        logger.error("Job %s not found", job_id)
        return []

    label = job.get("application_gmail_label", "")
    if not label:
        logger.info("Job %s has no Gmail label configured, skipping", job_id)
        return []

    service = get_gmail_service()
    if not service:
        logger.warning("Gmail not connected, skipping check for job %s", job_id)
        return []

    RESUME_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    try:
        response = service.users().messages().list(
            userId="me", q=f"label:{label}", maxResults=50
        ).execute()
        messages = response.get("messages", [])
    except Exception as e:
        logger.error("Failed to list Gmail messages: %s", e)
        return results

    for msg_stub in messages:
        message_id = msg_stub["id"]

        if db.is_email_processed(message_id):
            continue

        application_id = None
        candidate_id = None
        try:
            message = service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()

            sender_name, sender_email = _extract_sender(message)
            attachment = _find_resume_attachment(message.get("payload", {}))
            if not attachment:
                logger.info("No resume attachment in message %s from %s, skipping", message_id, sender_email)
                results.append({"message_id": message_id, "status": "skipped", "reason": "no_attachment"})
                _save_and_mark(service, message_id, job_id, None)
                continue

            file_data = _download_attachment(service, message_id, attachment)
            if not file_data:
                logger.warning("Failed to download attachment from message %s", message_id)
                results.append({"message_id": message_id, "status": "skipped", "reason": "download_failed"})
                _save_and_mark(service, message_id, job_id, None)
                continue

            ext = _extension_for_mime(attachment.get("mimeType", ""))
            resume_path = RESUME_DIR / f"{message_id}{ext}"
            resume_path.write_bytes(file_data)

            try:
                application = create_application_and_queue(
                    job=job,
                    full_name=sender_name or "Unknown Applicant",
                    email=sender_email or "",
                    resume_path=str(resume_path),
                    source="email_auto",
                )
            except DuplicateApplicationError:
                results.append({"message_id": message_id, "status": "duplicate", "candidate_id": None})
                _save_and_mark(service, message_id, job_id, None)
                continue

            application_id = application.application_id
            summary = screen_application(application_id)  # flush this app's job now
            candidate_id = summary.get("candidate_id")

            if summary["decision"] == "passed":
                results.append({
                    "message_id": message_id, "status": "invited",
                    "candidate_id": candidate_id, "match_score": summary.get("ats_score"),
                    "application_id": application_id,
                })
            else:
                results.append({
                    "message_id": message_id, "status": "not_shortlisted",
                    "candidate_id": candidate_id, "match_score": summary.get("ats_score"),
                    "application_id": application_id,
                })

            _mark_as_read_and_label(service, message_id)

        except Exception as e:
            logger.error("Error processing message %s: %s", message_id, e)
            results.append({"message_id": message_id, "status": "error", "reason": str(e)})

        _save_and_mark(service, message_id, job_id, candidate_id if candidate_id else application_id)

    return results


def summarize_poll_results(results: list[dict]) -> tuple:
    """Map the statuses emitted by check_for_new_applications into the
    poll-log counters. The pipeline returns: invited, not_shortlisted,
    skipped (no attachment / download failed), duplicate, error. Erroring
    messages are reported as failed so operators can see processing problems;
    the older below_threshold / invite_send_failed labels are not emitted."""
    invited = sum(1 for r in results if r.get("status") == "invited")
    below_threshold = sum(1 for r in results if r.get("status") == "not_shortlisted")
    skipped = sum(1 for r in results if r.get("status") in ("skipped", "duplicate"))
    failed = sum(1 for r in results if r.get("status") == "error")
    return invited, below_threshold, skipped, failed


def _save_and_mark(service, message_id: str, job_id: str, candidate_id: Optional[str]):
    """Record the email as processed and mark as read in Gmail."""
    processed = ProcessedEmail(
        message_id=message_id,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    db.save_processed_email(processed)
    if service:
        _mark_as_read_and_label(service, message_id)
