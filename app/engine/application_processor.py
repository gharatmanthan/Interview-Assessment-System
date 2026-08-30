"""
Shared application processing pipeline — reusable by both the Gmail
email intake and the public Apply Now portal.

Extracts the core logic: parse resume -> match JD -> check threshold ->
create Candidate -> generate invite code -> send invite email.
"""
import base64
import logging
import secrets
from pathlib import Path

from app.core import db
from app.core.models import Candidate
from app.engine.resume_parser import parse_resume
from app.engine.jd_matcher import match_resume_to_jd

logger = logging.getLogger(__name__)

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"


def process_application(
    resume_path: str,
    job_id: str,
    applicant_name: str,
    applicant_email: str,
    source: str = "manual",
    send_invite: bool = True,
    frontend_url: str = "",
) -> dict:
    """
    Process a job application: parse resume, match against JD, screen,
    create candidate record, optionally send invite email.

    Args:
        resume_path: Path to the saved resume file on disk.
        job_id: Job posting ID to match against.
        applicant_name: Name from the application form or email.
        applicant_email: Email from the application form or email.
        source: "manual", "email_auto", or "apply_portal".
        send_invite: Whether to send an invite email (True for email pipeline,
                     False for portal where candidate sees result immediately).
        frontend_url: Frontend base URL for invite link (remote mode only).

    Returns:
        dict with keys: candidate_id, match_score, screening_status,
        status, invite_code, invite_email_sent, matched_skills,
        missing_skills, error (None on success).
    """
    job = db.get_job_posting(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}

    try:
        resume_data = parse_resume(resume_path)
    except Exception as e:
        logger.warning("Resume parse failed for %s: %s", applicant_email, e)
        return {"error": f"Resume parsing failed: {e}"}

    match_result = match_resume_to_jd(resume_data, job["description"])
    match_score = match_result.get("match_score", 0.0)
    threshold = job.get("screening_threshold", 60.0)

    candidate_id = f"{source}-{secrets.token_hex(8)}"
    code = secrets.token_urlsafe(6)

    if match_score >= threshold:
        screening_status = "passed_threshold"
        status = "invited"
    else:
        screening_status = "below_threshold"
        status = "invited"

    candidate = Candidate(
        candidate_id=candidate_id,
        job_id=job_id,
        name=applicant_name or "Unknown Applicant",
        email=applicant_email or "",
        invite_code=code,
        status=status,
        source=source,
        screening_status=screening_status,
        invite_email_sent=False,
    )
    db.save_candidate(candidate)
    db.save_candidate_resume(
        candidate_id,
        resume_path,
        resume_data.get("skills", []),
        resume_data.get("experience_years"),
        match_score,
        match_result.get("matched_skills", []),
        match_result.get("missing_skills", []),
    )

    invite_email_sent = False
    scheduled_at = None  # naive-UTC datetime of the booked interview, if any
    if send_invite and match_score >= threshold:
        try:
            from app.core.settings_store import load_settings
            from app.engine.email_intake import compose_invite_email, get_gmail_service
            from app.engine import scheduling

            settings = load_settings()
            url = frontend_url or (
                settings.get("remote_api_url", "")
                if settings.get("backend_mode") == "remote"
                else ""
            )

            # Auto-book the next free interview slot on the recruiter's calendar.
            allocated = scheduling.allocate_next_slot(candidate_id, job_id)
            if "error" not in allocated and allocated.get("scheduled_at"):
                scheduled_at = allocated["scheduled_at"]

            service = get_gmail_service()
            if service:
                email_msg = compose_invite_email(
                    {"name": candidate.name, "email": candidate.email},
                    {"title": job["title"]},
                    code,
                    url,
                    scheduled_at,
                )
                email_msg["to"] = candidate.email
                email_msg["from"] = settings.get("gmail_user", "")
                raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode()
                service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()
                db.update_candidate_invite_email_sent(candidate_id, True)
                invite_email_sent = True
        except Exception as e:
            logger.error("Failed to send invite email to %s: %s", applicant_email, e)

    return {
        "candidate_id": candidate_id,
        "match_score": match_score,
        "screening_status": screening_status,
        "status": status,
        "invite_code": code,
        "invite_email_sent": invite_email_sent,
        "scheduled_at": scheduled_at,
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
        "error": None,
    }
