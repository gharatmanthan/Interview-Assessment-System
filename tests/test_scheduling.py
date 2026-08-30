"""
Tests for automatic interview scheduling (app/engine/scheduling.py).

Google Calendar API calls are mocked — no real network access.
"""
import base64
import email as email_lib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core import db
from app.core.models import Candidate
from app.engine import scheduling


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _mock_calendar_service(busy=None, created_events=None):
    """Build a mock Google Calendar API service with configurable busy intervals.

    busy: list of (start_naive_utc, end_naive_utc) intervals.
    created_events: optional list to append created event summaries to.
    """
    service = MagicMock()

    # freebusy -> busy intervals
    def _freebusy_execute(*a, **k):
        if busy is None:
            return {"calendars": {"primary": {"busy": []}}}
        return {
            "calendars": {
                "primary": {
                    "busy": [{"start": s.isoformat() + "Z", "end": e.isoformat() + "Z"} for (s, e) in busy]
                }
            }
        }

    fb = MagicMock()
    fb.query().execute.side_effect = _freebusy_execute
    service.freebusy = MagicMock(return_value=fb)

    # events().insert(...).execute() -> {"id": "evt-<n>"}
    evt = MagicMock()
    evt.insert().execute.return_value = {"id": "evt-autogen"}
    service.events = MagicMock(return_value=evt)
    return service


def _make_candidate(candidate_id="c1", job_id="job-1", email="jane@example.com"):
    candidate = Candidate(
        candidate_id=candidate_id,
        job_id=job_id,
        name="Jane Applicant",
        email=email,
        invite_code=f"code-{candidate_id}",
    )
    db.save_candidate(candidate)
    return candidate


FIXED_NOW = datetime(2026, 8, 27, 10, 0, 0)  # Thursday 10:00 UTC


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(scheduling, "_utcnow", lambda: FIXED_NOW)
    monkeypatch.setattr(db, "_utcnow", lambda: FIXED_NOW)


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------

def test_save_and_get_scheduled_interview(fresh_db):
    db.save_scheduled_interview("c1", "job-1", "2026-08-27 10:00:00", 45)
    row = db.get_scheduled_interview("c1")
    assert row is not None
    assert row["candidate_id"] == "c1"
    assert row["duration_minutes"] == 45


def test_get_all_scheduled_interviews_joins_names(fresh_db):
    _make_candidate("c1", "job-1")
    from app.core.models import JobPosting
    job = JobPosting(job_id="job-1", title="Backend Engineer", description="x",
                     required_skills=["python"], experience_level="Junior", department="Eng")
    db.save_job_posting(job)
    db.save_scheduled_interview("c1", "job-1", "2026-08-27 10:00:00", 45)
    rows = db.get_all_scheduled_interviews()
    assert rows[0]["candidate_name"] == "Jane Applicant"
    assert rows[0]["job_title"] == "Backend Engineer"


# ---------------------------------------------------------------------------
# Allocation logic (mocked calendar)
# ---------------------------------------------------------------------------

def test_allocates_first_free_slot_when_calendar_is_empty(fresh_db):
    _make_candidate("c1", "job-1")
    service = _mock_calendar_service(busy=[])
    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    assert "error" not in result
    # now=10:00, buffer=10 -> first slot starts at 10:10
    assert result["scheduled_at"] == FIXED_NOW + timedelta(minutes=10)
    assert result["duration_minutes"] == 45


def test_allocates_after_busy_event(fresh_db):
    _make_candidate("c1", "job-1")
    busy = [(FIXED_NOW, FIXED_NOW + timedelta(hours=2))]  # busy 10:00-12:00
    service = _mock_calendar_service(busy=busy)
    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    assert "error" not in result
    assert result["scheduled_at"] == FIXED_NOW + timedelta(hours=2)


def test_allocated_slot_is_persisted(fresh_db):
    _make_candidate("c1", "job-1")
    service = _mock_calendar_service(busy=[])
    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    row = db.get_scheduled_interview("c1")
    assert row is not None
    assert row["scheduled_at"]
    assert row["job_id"] == "job-1"


def test_avoids_overlap_with_existing_booking(fresh_db):
    _make_candidate("c1", "job-1")
    _make_candidate("c2", "job-1", email="jane.two@example.com")
    # Book c2 at 10:10 -> 10:55 first
    db.save_scheduled_interview("c2", "job-1", str(FIXED_NOW + timedelta(minutes=10)), 45)
    service = _mock_calendar_service(busy=[])
    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    # c1's slot starts at 10:10 but overlaps c2's booking (10:10-10:55);
    # advance by buffer until free at 11:00.
    assert result["scheduled_at"] == datetime(2026, 8, 27, 11, 0, 0)


def test_returns_existing_booking_not_a_duplicate(fresh_db):
    """Retrying allocation for an already-scheduled candidate must return the
    existing booking and not create a second calendar event."""
    _make_candidate("c1", "job-1")
    service = _mock_calendar_service(busy=[])
    first = scheduling.allocate_next_slot("c1", "job-1", service=service)
    second = scheduling.allocate_next_slot("c1", "job-1", service=service)

    assert first["status"] == "scheduled"
    assert second["existing"] is True
    assert second["scheduled_at"] == first["scheduled_at"]
    assert second["gcal_event_id"] == first["gcal_event_id"]
    # No calendar write happens during the duplicate attempt.
    service.events.return_value.insert.reset_mock()
    scheduling.allocate_next_slot("c1", "job-1", service=service)
    service.events.return_value.insert.assert_not_called()


def test_calendar_write_failure_returns_error_and_skips_booking(fresh_db):
    _make_candidate("c1", "job-1")
    service = _mock_calendar_service(busy=[])
    service.events.return_value.insert.return_value = MagicMock()
    service.events.return_value.insert().execute.side_effect = RuntimeError("gcal down")

    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    assert "error" in result
    assert db.get_scheduled_interview("c1") is None


def test_db_save_failure_compensates_ghost_calendar_event(fresh_db):
    """If the calendar event is created but the DB save then fails, the
    just-created event must be deleted (compensation) so a retry does not leave
    an orphaned 'ghost' booking on the recruiter's calendar."""
    _make_candidate("c1", "job-1")
    service = _mock_calendar_service(busy=[])
    service.events.return_value.insert().execute.return_value = {"id": "evt-ghost"}
    # A write failure from the DB after the calendar event already exists.
    with patch.object(db, "save_scheduled_interview",
                      side_effect=RuntimeError("db locked, write failed")):
        result = scheduling.allocate_next_slot("c1", "job-1", service=service)

    assert "error" in result
    # No booking may be persisted despite the calendar event being created.
    assert db.get_scheduled_interview("c1") is None
    # The just-created event is deleted from the calendar (no ghost left behind).
    service.events.return_value.delete.assert_called_once()
    args, kwargs = service.events.return_value.delete.call_args
    assert kwargs.get("eventId") == "evt-ghost"


def test_freebusy_failure_returns_error_not_exception(fresh_db):
    _make_candidate("c1", "job-1")
    service = _mock_calendar_service(busy=[])
    service.freebusy.return_value.query().execute.side_effect = RuntimeError("token refresh failed")

    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    assert "error" in result
    assert db.get_scheduled_interview("c1") is None


def test_working_days_are_respected(fresh_db):
    _make_candidate("c1", "job-1")
    # FIXED_NOW is Thursday 2026-08-27. With only weekends allowed, the first
    # usable date becomes Saturday 2026-08-29.
    from app.core.settings_store import save_settings
    save_settings({"working_days": [5, 6], "work_start_hour": 9, "work_end_hour": 18})
    service = _mock_calendar_service(busy=[])
    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    assert result["scheduled_at"].date() == datetime(2026, 8, 29).date()


def test_excluded_dates_are_respected(fresh_db):
    _make_candidate("c1", "job-1")
    from app.core.settings_store import save_settings
    save_settings({
        "excluded_dates": [FIXED_NOW.strftime("%Y-%m-%d")],
        "work_start_hour": 1, "work_end_hour": 23,
    })
    service = _mock_calendar_service(busy=[])
    result = scheduling.allocate_next_slot("c1", "job-1", service=service)
    assert result["scheduled_at"].date() != FIXED_NOW.date()


def test_returns_error_when_calendar_not_connected(fresh_db):
    _make_candidate("c1", "job-1")
    result = scheduling.allocate_next_slot("c1", "job-1", service=None)
    assert "error" in result


# ---------------------------------------------------------------------------
# Invite email includes the scheduled date
# ---------------------------------------------------------------------------

def test_invite_email_includes_scheduled_date():
    from app.engine.email_intake import compose_invite_email
    msg = compose_invite_email(
        {"name": "Jane", "email": "jane@example.com"},
        {"title": "Backend Engineer"},
        "CODE123",
        "",
        scheduled_at=FIXED_NOW,
    )
    body = msg.get_payload()
    assert "interview is scheduled for" in body
    assert "CODE123" in body


# ---------------------------------------------------------------------------
# Integration: email intake auto-allocates + emails the date
# ---------------------------------------------------------------------------

@patch("app.engine.scheduling.get_calendar_service")
@patch("app.engine.email_intake.get_gmail_service")
def test_email_auto_invite_queues_invite_and_allocates_on_flush(mock_gmail, mock_gcal, client, fresh_db, tmp_path):
    from app.core.models import JobPosting

    job = JobPosting(
        job_id="job-1", title="Backend Engineer", description="We need python and sql.",
        required_skills=["Python", "SQL"], experience_level="Junior", department="Engineering",
        screening_threshold=60.0, application_gmail_label="Applications/Backend",
    )
    db.save_job_posting(job)

    # Gmail message with a resume attachment
    resume_text = (
        b"Backend engineer with python, sql and rest api experience. "
        b"5 years of experience. B.Tech in Computer Science."
    )
    msg = {
        "id": "msg-900",
        "payload": {
            "headers": [
                {"name": "From", "value": "Jane Applicant <jane@example.com>"},
                {"name": "Subject", "value": "Application"},
            ],
            "parts": [{
                "filename": "resume.txt", "mimeType": "text/plain",
                "body": {"data": base64.urlsafe_b64encode(resume_text).decode()},
            }],
        },
    }
    gmail = MagicMock()
    gmail.users().messages().list().execute.return_value = {"messages": [{"id": "msg-900"}]}
    gmail.users().messages().get().execute.return_value = msg
    gmail.users().messages().send().execute.return_value = {"id": "s1"}
    mock_gmail.return_value = gmail

    # Calendar has no busy events -> first slot.
    mock_gcal.return_value = _mock_calendar_service(busy=[])

    with patch("app.engine.application_processor.parse_resume",
               return_value={"skills": ["python", "sql"], "experience_years": 3.0, "raw_text": "x"}), \
         patch("app.engine.application_processor.match_resume_to_jd",
               return_value={"match_score": 75.0, "matched_skills": ["python"], "missing_skills": [], "fit_summary": "x"}), \
         patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"), \
         patch("app.engine.email_intake._download_attachment", return_value=resume_text):
        from app.engine.email_intake import check_for_new_applications
        results = check_for_new_applications("job-1")

    assert results[0]["status"] == "invited"

    # The invite is queued in the outbox (deferred delivery), not sent inline.
    pending = db.get_pending_notifications()
    assert len(pending) == 1
    assert pending[0]["notification_type"] == "interview_invite"

    # Flush the outbox: this allocates the calendar slot and sends via Gmail.
    with patch("app.screening.email_worker.get_gmail_service", return_value=gmail):
        from app.screening.email_worker import send_pending_notifications
        sent_ids = send_pending_notifications()
    assert sent_ids == [pending[0]["id"]]

    sched = db.get_all_scheduled_interviews()
    assert len(sched) == 1
    assert sched[0]["candidate_id"]
    assert sched[0]["scheduled_at"]

    # The sent invite email includes the interview date.
    raw = base64.urlsafe_b64decode(gmail.users().messages().send.call_args.kwargs["body"]["raw"])
    parsed = email_lib.message_from_bytes(raw)
    assert "interview is scheduled for" in parsed.get_payload()
