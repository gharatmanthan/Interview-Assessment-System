from fastapi import APIRouter, Depends
from api.deps import get_current_recruiter
from api.schemas import (
    SettingsUpdate, SettingsResponse, GmailStatusResponse, GmailConnectResponse,
    CalendarStatusResponse, CalendarConnectResponse,
)
from app.core.settings_store import load_settings, save_settings
from app.engine.email_intake import run_oauth_flow, disconnect_gmail
from app.engine.scheduling import run_calendar_oauth_flow, disconnect_calendar

router = APIRouter()


def _public_settings() -> SettingsResponse:
    """Settings surface, with OAuth tokens and the signing secret redacted."""
    settings = load_settings()
    redacted = {
        "camera_index": settings.get("camera_index", 0),
        "mic_device": settings.get("mic_device", "default"),
        "llm_provider": settings.get("llm_provider", "Groq"),
        "export_dir": settings.get("export_dir", ""),
        "gmail_connected": settings.get("gmail_connected", False),
        "gmail_user": settings.get("gmail_user", ""),
        "calendar_connected": settings.get("calendar_connected", False),
        "calendar_user": settings.get("calendar_user", ""),
        "interview_duration_minutes": settings.get("interview_duration_minutes", 45),
        "interview_buffer_minutes": settings.get("interview_buffer_minutes", 10),
        "work_start_hour": settings.get("work_start_hour", 9),
        "work_end_hour": settings.get("work_end_hour", 18),
        "scheduling_horizon_days": settings.get("scheduling_horizon_days", 30),
        "working_days": settings.get("working_days", [0, 1, 2, 3, 4]),
        "excluded_dates": settings.get("excluded_dates", []),
    }
    return SettingsResponse(**redacted)


@router.get("", response_model=SettingsResponse)
def get_settings(username: str = Depends(get_current_recruiter)):
    return _public_settings()


@router.put("", response_model=SettingsResponse)
def update_settings(req: SettingsUpdate, username: str = Depends(get_current_recruiter)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    save_settings(updates)
    return _public_settings()


@router.get("/gmail/status", response_model=GmailStatusResponse)
def gmail_status(username: str = Depends(get_current_recruiter)):
    settings = load_settings()
    return GmailStatusResponse(
        connected=settings.get("gmail_connected", False),
        email=settings.get("gmail_user", ""),
    )


@router.post("/gmail/connect", response_model=GmailConnectResponse)
def gmail_connect(username: str = Depends(get_current_recruiter)):
    """Initiate the Gmail OAuth flow and store the resulting credentials."""
    try:
        email = run_oauth_flow()
        return GmailConnectResponse(
            success=True,
            email=email,
            message=f"Connected as {email}",
        )
    except FileNotFoundError as e:
        return GmailConnectResponse(success=False, message=str(e))
    except Exception as e:
        return GmailConnectResponse(success=False, message=f"OAuth failed: {e}")


@router.post("/gmail/disconnect")
def gmail_disconnect(username: str = Depends(get_current_recruiter)):
    disconnect_gmail()
    return {"success": True, "message": "Gmail disconnected"}


@router.get("/calendar/status", response_model=CalendarStatusResponse)
def calendar_status(username: str = Depends(get_current_recruiter)):
    settings = load_settings()
    return CalendarStatusResponse(
        connected=settings.get("calendar_connected", False),
        email=settings.get("calendar_user", ""),
    )


@router.post("/calendar/connect", response_model=CalendarConnectResponse)
def calendar_connect(username: str = Depends(get_current_recruiter)):
    """Initiate the Google Calendar OAuth flow and store the credentials."""
    try:
        email = run_calendar_oauth_flow()
        return CalendarConnectResponse(
            success=True,
            email=email,
            message=f"Calendar connected as {email}",
        )
    except FileNotFoundError as e:
        return CalendarConnectResponse(success=False, message=str(e))
    except Exception as e:
        return CalendarConnectResponse(success=False, message=f"OAuth failed: {e}")


@router.post("/calendar/disconnect")
def calendar_disconnect(username: str = Depends(get_current_recruiter)):
    disconnect_calendar()
    return {"success": True, "message": "Calendar disconnected"}