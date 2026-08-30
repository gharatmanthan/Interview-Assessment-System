"""
Owner: Member C
Touches: this file, app/ui/pages/settings_page.py

Simple JSON-backed app settings — camera/mic device selection, LLM
provider config, export preferences. Deliberately not in the SQLite DB
since this is app-level config, not interview data.
"""
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "settings.json"

# Fields that used to mirror the OAuth client id/secret from
# client_secret.json into settings. They are no longer written, and any
# leftovers in an existing settings.json are stripped during migration.
_OBSOLETE_CREDENTIAL_KEYS = (
    "gmail_client_id",
    "gmail_client_secret",
    "calendar_client_id",
    "calendar_client_secret",
)


def _migrate_obsolete_credentials(data: dict) -> None:
    """Drop the mirrored OAuth client id/secret keys from an existing
    settings.json, preserving refresh tokens and every other setting.

    Rewrites the file only when obsolete keys are present, so the cleanup
    is idempotent and never wipes unrelated settings.
    """
    if not any(k in data for k in _OBSOLETE_CREDENTIAL_KEYS):
        return
    for k in _OBSOLETE_CREDENTIAL_KEYS:
        data.pop(k, None)
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        data = {}
    _migrate_obsolete_credentials(data)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = load_settings()
    merged.update(settings)
    for k in _OBSOLETE_CREDENTIAL_KEYS:
        merged.pop(k, None)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(merged, f, indent=2)
    return merged

DEFAULTS = {
    "camera_index": 0,
    "mic_device": "default",
    "llm_provider": "Groq",
    "llm_api_key": "",
    "export_dir": str(Path.home() / "Documents"),
    # How this desktop app reaches the API:
    #   "local"  — Electron spawns api/main.py as a child process (single
    #              machine / on-site use, works with zero setup)
    #   "remote" — no local spawn; all shared data goes to remote_api_url
    #              (the central deployed server) over HTTPS
    "backend_mode": "local",
    # Central server base URL used when backend_mode == "remote".
    # Empty means not configured yet -> Electron shows the one-time
    # server-address setup screen on first launch.
    "remote_api_url": "",
    # Gmail integration — OAuth tokens stored here, never in SQLite. The
    # OAuth client config lives in data/client_secret.json (single source of
    # truth); only the refresh token is persisted here.
    "gmail_connected": False,
    "gmail_user": "",
    "gmail_refresh_token": "",
    # Google Calendar integration (recruiter availability for auto-scheduling)
    "calendar_connected": False,
    "calendar_user": "",
    "calendar_refresh_token": "",
    "calendar_id": "primary",
    # Automatic interview scheduling configuration
    "interview_duration_minutes": 45,
    "interview_buffer_minutes": 10,
    "work_start_hour": 9,       # auto-schedules only within these working hours
    "work_end_hour": 18,
    "scheduling_horizon_days": 30,
    # Days of the week (0=Monday .. 6=Sunday) interviews may be scheduled on.
    "working_days": [0, 1, 2, 3, 4],
    # Dates (YYYY-MM-DD) the recruiter is unavailable — e.g. holidays.
    "excluded_dates": [],
    # HR digest email — receives the shortlist notification from the outbox.
    "hr_email": "",
    # HMAC signing secret for recruiter auth tokens (generated at first login).
    "auth_secret": "",
}
