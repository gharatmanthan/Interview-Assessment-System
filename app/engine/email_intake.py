"""
Email intake pipeline — watches a Gmail label for job applications,
screens resumes, and auto-invites qualified candidates.

Reuses the existing resume_parser.py + jd_matcher.py pipeline unchanged;
this module only adds the Gmail layer around it.
"""
import base64
import logging
import secrets
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core import db
from app.core.models import Candidate, ProcessedEmail
from app.core.settings_store import load_settings, save_settings
from app.engine.resume_parser import parse_resume
from app.engine.jd_matcher import match_resume_to_jd

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.labels",
]

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"

# Path to the OAuth client_secret.json (stored outside version control in data/)
CLIENT_SECRET_PATH = Path(__file__).parent.parent.parent / "data" / "client_secret.json"


def get_gmail_service():
    """Build a Gmail API service from the stored refresh token.
    Returns None if Gmail is not connected.
    """
    settings = load_settings()
    if not settings.get("gmail_connected") or not settings.get("gmail_refresh_token"):
        return None
    creds = Credentials(
        token=None,
        refresh_token=settings["gmail_refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id="",
        client_secret="",
    )
    return build("gmail", "v1", credentials=creds)


def run_oauth_flow():
    """Run the OAuth consent flow and store the resulting credentials.
    Returns the connected email address on success, raises on failure.
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
                         frontend_url: str = "") -> MIMEText:
    """Compose a professional invite email for a shortlisted candidate.

    Kept as a separate template function so wording can be edited without
    touching the sending logic.
    """
    subject = f"You've been shortlisted for an interview \u2014 {job['title']}"

    if frontend_url:
        link = f"{frontend_url}/candidate/entry?code={invite_code}"
        body = (
            f"Dear {candidate['name']},\n\n"
            f"Congratulations! You have been shortlisted for the {job['title']} position.\n\n"
            f"Your interview invite code is: {invite_code}\n\n"
            f"To begin your interview, click the link below and enter your code:\n"
            f"{link}\n\n"
            f"If the link doesn't work, you can also enter the code manually at the interview entry page.\n\n"
            f"Best regards,\nInterviewIQ Automated Screening"
        )
    else:
        body = (
            f"Dear {candidate['name']},\n\n"
            f"Congratulations! You have been shortlisted for the {job['title']} position.\n\n"
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
    3. Parse resume, match against job description
    4. Create Candidate, generate invite code, send invite email if above threshold
    5. Mark message as read + apply Processed label
    6. Record in ProcessedEmail regardless of outcome

    Returns a summary list of what was processed.
    """
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

    settings = load_settings()
    frontend_url = settings.get("remote_api_url", "") if settings.get("backend_mode") == "remote" else ""

    results = []

    try:
        # List messages in the label
        label_query = f"label:{label}"
        response = service.users().messages().list(
            userId="me", q=label_query, maxResults=50
        ).execute()
        messages = response.get("messages", [])
    except Exception as e:
        logger.error("Failed to list Gmail messages: %s", e)
        return results

    for msg_stub in messages:
        message_id = msg_stub["id"]

        # Skip already-processed
        if db.is_email_processed(message_id):
            continue

        candidate_id = None
        try:
            # Fetch full message
            message = service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()

            sender_name, sender_email = _extract_sender(message)

            # Find resume attachment
            attachment = _find_resume_attachment(message.get("payload", {}))
            if not attachment:
                logger.info("No resume attachment in message %s from %s, skipping", message_id, sender_email)
                results.append({"message_id": message_id, "status": "skipped", "reason": "no_attachment"})
                _save_and_mark(service, message_id, job_id, None)
                continue

            # Download attachment
            file_data = _download_attachment(service, message_id, attachment)
            if not file_data:
                logger.warning("Failed to download attachment from message %s", message_id)
                results.append({"message_id": message_id, "status": "skipped", "reason": "download_failed"})
                _save_and_mark(service, message_id, job_id, None)
                continue

            # Save resume file
            ext = _extension_for_mime(attachment.get("mimeType", ""))
            resume_filename = f"{message_id}{ext}"
            resume_path = RESUME_DIR / resume_filename
            resume_path.write_bytes(file_data)

            # Parse resume
            try:
                resume_data = parse_resume(str(resume_path))
            except Exception as e:
                logger.warning("Resume parse failed for message %s: %s", message_id, e)
                results.append({"message_id": message_id, "status": "skipped", "reason": "parse_failed"})
                _save_and_mark(service, message_id, job_id, None)
                continue

            # Match against job description
            match_result = match_resume_to_jd(resume_data, job["description"])
            match_score = match_result.get("match_score", 0.0)
            threshold = job.get("screening_threshold", 60.0)

            # Create candidate
            candidate_id = f"email-{message_id}"
            code = secrets.token_urlsafe(6)

            if match_score >= threshold:
                screening_status = "passed_threshold"
                status = "invited"
            else:
                screening_status = "below_threshold"
                status = "invited"  # Still "invited" for the status field; screening_status distinguishes

            candidate = Candidate(
                candidate_id=candidate_id,
                job_id=job_id,
                name=sender_name or "Unknown Applicant",
                email=sender_email or "",
                invite_code=code,
                status=status,
                source="email_auto",
                screening_status=screening_status,
                invite_email_sent=False,
            )
            db.save_candidate(candidate)
            db.save_candidate_resume(
                candidate_id,
                str(resume_path),
                resume_data.get("skills", []),
                resume_data.get("experience_years"),
                match_score,
                match_result.get("matched_skills", []),
                match_result.get("missing_skills", []),
            )

            # Send invite email if above threshold
            if match_score >= threshold:
                try:
                    email_msg = compose_invite_email(
                        {"name": candidate.name, "email": candidate.email},
                        {"title": job["title"]},
                        code,
                        frontend_url,
                    )
                    email_msg["to"] = candidate.email
                    email_msg["from"] = settings.get("gmail_user", "")
                    raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode()
                    service.users().messages().send(
                        userId="me",
                        body={"raw": raw},
                    ).execute()
                    db.update_candidate_invite_email_sent(candidate_id, True)
                    results.append({
                        "message_id": message_id, "status": "invited",
                        "candidate_id": candidate_id, "match_score": match_score,
                    })
                except Exception as e:
                    logger.error("Failed to send invite email to %s: %s", candidate.email, e)
                    db.update_candidate_invite_email_sent(candidate_id, False)
                    results.append({
                        "message_id": message_id, "status": "invite_send_failed",
                        "candidate_id": candidate_id, "match_score": match_score,
                    })
            else:
                results.append({
                    "message_id": message_id, "status": "below_threshold",
                    "candidate_id": candidate_id, "match_score": match_score,
                })

            # Mark as read
            _mark_as_read_and_label(service, message_id)

        except Exception as e:
            logger.error("Error processing message %s: %s", message_id, e)
            results.append({"message_id": message_id, "status": "error", "reason": str(e)})

        # Always record as processed, even if something above failed
        _save_and_mark(service, message_id, job_id, candidate_id)

    return results


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
