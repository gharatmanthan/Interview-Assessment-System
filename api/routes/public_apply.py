"""
Public application intake — no authentication required.

Candidates visit /apply/{jobId}, upload their resume, and this endpoint
stores the application and QUEUES screening (async, 202). The request
never runs the matcher, creates a candidate, or touches Gmail — so the
heavy AI/side-effect work is decoupled from submission latency and a
Gmail outage can never block the applicant.
"""
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException

from app.core import db
from api.rate_limit import rate_limited
from api.schemas import PublicJobResponse, PublicApplyResponse
from app.screening.service import DuplicateApplicationError, create_application_and_queue

router = APIRouter()

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def _validate_resume_file(upload: UploadFile) -> str:
    """Return allowed extension or raise 400."""
    content_type = upload.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF, DOCX, or TXT file.",
        )
    ext = Path(upload.filename or "resume.pdf").suffix.lower()
    if ext not in {".pdf", ".docx", ".txt"}:
        ext = ".txt" if content_type == "text/plain" else ".pdf"
    return ext


@router.get("/jobs/{job_id}", response_model=PublicJobResponse)
def get_public_job(job_id: str):
    """Return minimal job details for the public apply page (no auth required)."""
    job = db.get_job_posting(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    return PublicJobResponse(
        job_id=job["job_id"],
        title=job["title"],
        description=job["description"],
        required_skills=job["required_skills"],
        experience_level=job["experience_level"],
        department=job["department"],
    )


@router.post("/apply/{job_id}", response_model=PublicApplyResponse, status_code=202, dependencies=[Depends(rate_limited("public_apply"))])
async def apply_for_job(
    job_id: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    resume: UploadFile = File(...),
):
    """
    Submit a job application. Stores the application, queues screening,
    and returns 202 {application_id, status: "received"}. No authentication.
    """
    job = db.get_job_posting(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    if not job.get("is_active", True):
        raise HTTPException(status_code=400, detail="This position is no longer accepting applications.")

    name = (name or "").strip()
    email = (email or "").strip().lower() if email else ""
    if not name or not email or "@" not in email:
        raise HTTPException(status_code=422, detail="A valid name and email are required.")

    ext = _validate_resume_file(resume)

    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"apply-{job_id}-{secrets.token_hex(8)}{ext}"
    resume_path = RESUME_DIR / filename
    file_data = await resume.read()
    if not file_data or len(file_data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Resume is empty or exceeds the 5MB limit.")
    resume_path.write_bytes(file_data)

    try:
        app = create_application_and_queue(
            job=job,
            full_name=name,
            email=email,
            phone=phone,
            resume_path=str(resume_path),
            source="apply_portal",
        )
    except DuplicateApplicationError:
        raise HTTPException(
            status_code=409,
            detail="An application for this email already exists for this position.",
        )

    return PublicApplyResponse(
        success=True,
        status="received",
        application_id=app.application_id,
        message="Application received and queued for screening.",
    )
