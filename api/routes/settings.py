from fastapi import APIRouter
from api.schemas import SettingsUpdate, SettingsResponse, GmailStatusResponse, GmailConnectResponse
from app.core.settings_store import load_settings, save_settings
from app.engine.email_intake import run_oauth_flow, disconnect_gmail

router = APIRouter()


@router.get("", response_model=SettingsResponse)
def get_settings():
    return load_settings()


@router.put("", response_model=SettingsResponse)
def update_settings(req: SettingsUpdate):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = save_settings(updates)
    return result


@router.get("/gmail/status", response_model=GmailStatusResponse)
def gmail_status():
    settings = load_settings()
    return GmailStatusResponse(
        connected=settings.get("gmail_connected", False),
        email=settings.get("gmail_user", ""),
    )


@router.post("/gmail/connect", response_model=GmailConnectResponse)
def gmail_connect():
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
def gmail_disconnect():
    disconnect_gmail()
    return {"success": True, "message": "Gmail disconnected"}
