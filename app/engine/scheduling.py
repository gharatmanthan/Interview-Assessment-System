"""
Automatic interview scheduling from the recruiter's Google Calendar.

Flow:
1. Recruiter connects their Google Calendar (OAuth, calendar scopes) once.
2. When a candidate passes the screening threshold and is auto-invited, the
   system queries the recruiter's calendar free/busy, picks the next slot that
   fits the configured interview duration + buffer within working hours, and
   does not overlap already-scheduled interviews (from the DB *or* the calendar).
3. The chosen slot is persisted to `scheduled_interviews` and written back to
   the recruiter's calendar as a booking event, so future auto-schedules naturally
   avoid it.
"""
import os
import base64
import logging
from datetime import datetime, timedelta

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core import db
from app.core.oauth_client import CLIENT_SECRET_PATH, load_oauth_credentials
from app.core.settings_store import load_settings, save_settings

logger = logging.getLogger(__name__)

# readonly lets us find free slots; events lets us write booking events back to
# the calendar so non-overlap holds across future auto-bookings.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_calendar_service():
    """Build a Google Calendar service from the stored refresh token, using
    the OAuth client config from data/client_secret.json (single source of
    truth). Returns None if the calendar is not connected.
    """
    settings = load_settings()
    if not settings.get("calendar_connected") or not settings.get("calendar_refresh_token"):
        return None
    creds = load_oauth_credentials(settings.get("calendar_refresh_token", ""))
    if creds is None:
        return None
    return build("calendar", "v3", credentials=creds)


def run_calendar_oauth_flow() -> str:
    """Run the OAuth consent flow and store the resulting credentials.
    Persists only the refresh token + account markers; the OAuth client
    config stays in data/client_secret.json. Returns the connected account
    email on success, raises on failure.
    """
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"OAuth client_secret.json not found at {CLIENT_SECRET_PATH}. "
            "Download it from Google Cloud Console and place it in data/."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    # Use configured redirect URI if provided
    redirect_uri = os.environ.get("CALENDAR_REDIRECT_URI", "").strip()
    if redirect_uri:
        flow.redirect_uri = redirect_uri
        creds = flow.run_local_server(port=0)
    else:
        creds = flow.run_local_server(port=0)
    service = build("calendar", "v3", credentials=creds)
    about = service.calendarList().get(calendarId="primary").execute()
    email = about.get("id", "")

    save_settings({
        "calendar_connected": True,
        "calendar_user": email,
        "calendar_refresh_token": creds.refresh_token,
        "calendar_id": "primary",
    })
    return email


def disconnect_calendar():
    """Clear stored calendar credentials."""
    save_settings({
        "calendar_connected": False,
        "calendar_user": "",
        "calendar_refresh_token": "",
    })


def _normalize_dt(value):
    """Return a naive UTC datetime from a datetime/date/RFC3339 string."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(tz_utc()).replace(tzinfo=None)
    if hasattr(value, "isoformat"):  # date
        return datetime(value.year, value.month, value.day)
    # RFC3339 string, e.g. 2026-08-27T10:00:00Z or with offset
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return value
    return _normalize_dt(parsed)


def tz_utc():
    from datetime import timezone
    return timezone.utc


def _utcnow():
    """Separate helper so tests can pin the current time. Keep callers using this."""
    return datetime.utcnow()


def _busy_intervals(service, calendar_id, start_utc, end_utc):
    """Return a list of (start_naive_utc, end_naive_utc) busy intervals."""
    body = {
        "timeMin": start_utc.isoformat() + "Z",
        "timeMax": end_utc.isoformat() + "Z",
        "timeZone": "UTC",
        "items": [{"id": calendar_id}],
    }
    resp = service.freebusy().query(body=body).execute()
    busy = []
    for cal in resp.get("calendars", {}).values():
        for block in cal.get("busy", []):
            start = _normalize_dt(block.get("start"))
            end = _normalize_dt(block.get("end"))
            busy.append((start, end))
    busy.sort(key=lambda b: b[0])
    return busy


def _free_windows(busy, start, end, work_start, work_end, working_days=None, excluded_dates=None):
    """Invert busy intervals into free windows, clipped to [start, end),
    the recruiter's working hours, working days, and excluded dates (holidays).
    Returns list of (start_naive_utc, end_naive_utc).
    """
    working_days = working_days if working_days is not None else list(range(7))
    excluded_dates = excluded_dates or []

    # Merge overlapping/sorted busy intervals
    merged = []
    for b in busy:
        b = (max(b[0], start), min(b[1], end))
        if b[1] <= b[0]:
            continue
        if merged and b[0] < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b[1]))
        else:
            merged.append(b)

    free = []
    cursor = start
    for b in merged:
        if b[0] > cursor:
            free.append((cursor, b[0]))
        cursor = max(cursor, b[1])
    if cursor < end:
        free.append((cursor, end))

    # Clip each free window to working hours and split across day boundaries.
    windows = []
    for (fs, fe) in free:
        day = fs.replace(hour=0, minute=0, second=0, microsecond=0)
        while day < fe:
            if day.weekday() in working_days and day.strftime("%Y-%m-%d") not in excluded_dates:
                day_work_start = day.replace(hour=work_start, minute=0, second=0, microsecond=0)
                day_work_end = day.replace(hour=work_end, minute=0, second=0, microsecond=0)
                ws = max(fs, day_work_start)
                we = min(fe, day_work_end)
                if we > ws:
                    windows.append((ws, we))
            day = day + timedelta(days=1)
    windows.sort(key=lambda w: w[0])
    return windows


def _existing_bookings():
    """Our own already-scheduled interviews as (start, end) naive-UTC intervals."""
    bookings = []
    for row in db.get_upcoming_scheduled_interviews():
        if (row.get("status") or "scheduled") != "scheduled":
            continue
        start = _normalize_dt(row["scheduled_at"])
        end = start + timedelta(minutes=int(row["duration_minutes"] or 45))
        bookings.append((start, end))
    bookings.sort()
    return bookings


def _overlaps(slot_start, slot_end, intervals):
    for (a, b) in intervals:
        if slot_start < b and slot_end > a:
            return True
    return False


def allocate_next_slot(candidate_id, job_id, service=None):
    """Find and book the next available interview slot for a candidate.

    Returns a dict with keys: scheduled_at (naive-UTC datetime), duration_minutes,
    status; or {"error": <reason>} if none could be found (e.g. calendar not
    connected or no free slot in the horizon). Failures are returned as
    error dicts rather than raised, so an OAuth-refresh hiccup or a failed
    calendar write cannot 500 the API.

    Idempotent: a candidate who already has a scheduled booking gets that
    booking back instead of a duplicate calendar event. The DB row is only
    written after the calendar event is successfully created, so a retry
    after a partial failure re-books cleanly instead of double-booking.
    """
    settings = load_settings()

    existing = db.get_scheduled_interview(candidate_id)
    if existing and existing.get("status") == "scheduled":
        return {
            "scheduled_at": _normalize_dt(existing["scheduled_at"]),
            "duration_minutes": int(existing.get("duration_minutes") or 45),
            "status": existing.get("status", "scheduled"),
            "gcal_event_id": existing.get("gcal_event_id"),
            "existing": True,
        }

    if service is None:
        service = get_calendar_service()
    if service is None:
        return {"error": "Calendar is not connected. Connect it in Settings first."}

    duration = int(settings.get("interview_duration_minutes", 45))
    buffer_min = int(settings.get("interview_buffer_minutes", 10))
    work_start = int(settings.get("work_start_hour", 9))
    work_end = int(settings.get("work_end_hour", 18))
    horizon = int(settings.get("scheduling_horizon_days", 30))
    calendar_id = settings.get("calendar_id", "primary")
    working_days = settings.get("working_days") if settings.get("working_days") is not None else list(range(7))
    excluded_dates = settings.get("excluded_dates") or []

    now = _utcnow()
    # Start searching from the next whole slot after the buffer.
    start = now + timedelta(minutes=buffer_min)
    end = now + timedelta(days=horizon)

    try:
        busy = _busy_intervals(service, calendar_id, start, end)
    except Exception as e:
        logger.error("Failed to query calendar free/busy: %s", e)
        return {"error": "Could not reach your calendar right now. Please try again."}
    free = _free_windows(busy, start, end, work_start, work_end,
                         working_days=working_days, excluded_dates=excluded_dates)
    bookings = _existing_bookings()

    total_window = duration + buffer_min
    for (fs, fe) in free:
        cursor = fs
        while cursor + timedelta(minutes=duration) <= fe:
            slot_end = cursor + timedelta(minutes=duration)
            buffered_end = cursor + timedelta(minutes=total_window)
            # Must not overlap our own bookings either.
            if buffered_end <= fe and not _overlaps(cursor, buffered_end, bookings):
                gcal_event_id = _create_calendar_event(
                    service, calendar_id, cursor, slot_end,
                    f"Interview — {job_id[:40]}",
                )
                if not gcal_event_id:
                    # No event on the calendar means no validated booking.
                    # Fail the attempt rather than persisting a "scheduled"
                    # row without its calendar counterpart.
                    return {"error": "Your interview slot could not be written to the calendar. Please try again."}
                try:
                    db.save_scheduled_interview(
                        candidate_id=candidate_id,
                        job_id=job_id,
                        scheduled_at=cursor,
                        duration_minutes=duration,
                        gcal_event_id=gcal_event_id,
                    )
                except Exception as e:
                    # Compensation: the calendar event was already created but
                    # the DB write failed, which would otherwise leave an
                    # orphaned "ghost" booking on the recruiter's calendar.
                    # Remove it so a retry re-books cleanly.
                    logger.error("Failed to persist scheduled interview (%s); "
                                 "removing ghost calendar event %s", e, gcal_event_id)
                    try:
                        service.events().delete(
                            calendarId=calendar_id, eventId=gcal_event_id
                        ).execute()
                    except Exception as cleanup_exc:
                        logger.warning("Failed to remove ghost calendar event %s: %s",
                                       gcal_event_id, cleanup_exc)
                    return {"error": "Your interview slot could not be saved. Please try again."}
                return {
                    "scheduled_at": cursor,
                    "duration_minutes": duration,
                    "status": "scheduled",
                    "gcal_event_id": gcal_event_id,
                    "existing": False,
                }
            cursor = cursor + timedelta(minutes=buffer_min)

    return {"error": "No free slot found in the scheduling horizon."}


def _create_calendar_event(service, calendar_id, start, end, summary):
    """Create a booking event on the recruiter's calendar so future auto-
    scheduling avoids it. Returns the new event id, or None on failure."""
    try:
        event = service.events().insert(
            calendarId=calendar_id,
            body={
                "summary": summary,
                "start": {"dateTime": start.isoformat() + "Z", "timeZone": "UTC"},
                "end": {"dateTime": end.isoformat() + "Z", "timeZone": "UTC"},
            },
        ).execute()
        return event.get("id")
    except Exception as e:
        logger.error("Failed to create calendar event: %s", e)
        return None


def delete_calendar_event(calendar_id, event_id):
    """Remove a booking event from the recruiter's calendar when an
    interview is cancelled or rescheduled."""
    service = get_calendar_service()
    if not service or not event_id:
        return
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except Exception as e:
        logger.warning("Failed to delete calendar event %s: %s", event_id, e)
