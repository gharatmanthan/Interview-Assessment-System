"""
Scheduling routes — view and manually trigger automatic interview scheduling
based on the recruiter's Google Calendar availability. All routes are
recruiter-authenticated and ownership-scoped.
"""
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_recruiter
from api.schemas import (
    ScheduledInterviewResponse,
    AllocateSlotRequest,
    AllocateSlotResponse,
    AvailabilityResponse,
)
from app.core import db
from app.core.settings_store import load_settings
from app.engine import scheduling

router = APIRouter()


@router.get("", response_model=list[ScheduledInterviewResponse])
def list_scheduled_interviews(username: str = Depends(get_current_recruiter)):
    return db.get_owned_scheduled_interviews(username)


@router.post("/allocate", response_model=AllocateSlotResponse)
def allocate_slot(req: AllocateSlotRequest, username: str = Depends(get_current_recruiter)):
    """Manually book the next free interview slot for a candidate."""
    if not db.job_owned_by(req.job_id, username):
        raise HTTPException(status_code=403, detail="Not your job posting.")
    candidate = db.get_candidates_for_job(req.job_id)
    candidate = next((c for c in candidate if c["candidate_id"] == req.candidate_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    result = scheduling.allocate_next_slot(req.candidate_id, req.job_id)
    if "error" in result:
        return AllocateSlotResponse(success=False, message=result["error"])
    return AllocateSlotResponse(
        success=True,
        scheduled_at=str(result["scheduled_at"]),
        duration_minutes=result.get("duration_minutes"),
        message="Slot allocated",
    )


@router.get("/availability", response_model=AvailabilityResponse)
def get_availability(hours: int = 48, username: str = Depends(get_current_recruiter)):
    """Preview the recruiter's next free slots within the given number of hours."""
    from datetime import timedelta

    service = scheduling.get_calendar_service()
    if not service:
        return AvailabilityResponse(connected=False, slots=[], message="Calendar not connected")

    settings = load_settings()
    duration = int(settings.get("interview_duration_minutes", 45))
    buffer = int(settings.get("interview_buffer_minutes", 10))
    work_start = int(settings.get("work_start_hour", 9))
    work_end = int(settings.get("work_end_hour", 18))
    calendar_id = settings.get("calendar_id", "primary")

    now = scheduling._utcnow()
    start = now + timedelta(minutes=buffer)
    end = start + timedelta(hours=hours)

    working_days = settings.get("working_days") if settings.get("working_days") is not None else list(range(7))
    excluded_dates = settings.get("excluded_dates") or []

    busy = scheduling._busy_intervals(service, calendar_id, start, end)
    free = scheduling._free_windows(busy, start, end, work_start, work_end,
                                    working_days=working_days, excluded_dates=excluded_dates)
    bookings = scheduling._existing_bookings()

    slots = []
    for (fs, fe) in free:
        cursor = fs
        while cursor + timedelta(minutes=duration) <= fe:
            buffered_end = cursor + timedelta(minutes=duration + buffer)
            if buffered_end <= fe and not scheduling._overlaps(cursor, buffered_end, bookings):
                slots.append(str(cursor))
            cursor = cursor + timedelta(minutes=buffer)

    return AvailabilityResponse(connected=True, slots=slots[:50], message="OK")
