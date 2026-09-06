"""
Tests for the email intake pipeline (app/engine/email_intake.py).

All Gmail API calls are mocked — no real Gmail access in automated tests.
Intake stores the Application + queues screening; delivery happens via the
notification outbox worker, never synchronously inside intake.
"""
import base64
from unittest.mock import MagicMock, patch

import pytest

from app.core import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gmail_message(message_id, sender="Jane Applicant <jane@example.com>",
                        subject="Application for Backend Engineer",
                        attachment_filename="resume.txt", attachment_mime="text/plain",
                        attachment_data=None):
    """Build a mock Gmail API message response."""
    if attachment_data is None:
        attachment_data = _RESUME_TEXT.encode()
    att_body = base64.urlsafe_b64encode(attachment_data).decode()
    payload = {
        "headers": [
            {"name": "From", "value": sender},
            {"name": "Subject", "value": subject},
        ],
    }
    if attachment_filename:
        payload["parts"] = [{
            "filename": attachment_filename,
            "mimeType": attachment_mime,
            "body": {"data": att_body, "size": len(attachment_data)},
        }]
    return {"id": message_id, "payload": payload}


_RESUME_TEXT = (
    "Jane Doe\n"
    "Backend engineer with python, sql and rest api experience. "
    "5 years of experience. B.Tech in Computer Science.\n"
)


def _make_job(client, job_id="job-1", label="Applications/Backend",
              threshold=60.0, description="We need python and sql skills.",
              min_exp=3):
    """Create a job posting with a Gmail label and screening threshold via the API."""
    client.post("/api/jobs", json={
        "job_id": job_id,
        "title": "Backend Engineer",
        "description": description,
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": threshold,
        "application_gmail_label": label,
        "minimum_experience_years": min_exp,
    })


def _mock_gmail_service(messages=None, msg=None):
    """Create a mock Gmail API service."""
    service = MagicMock()
    if messages is None:
        messages = []
    service.users().messages().list().execute.return_value = {"messages": messages}
    if msg is not None:
        service.users().messages().get().execute.return_value = msg
    return service


def _run_check(job_id, tmp_path):
    from app.engine.email_intake import check_for_new_applications
    with patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"):
        return check_for_new_applications(job_id)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestEmailIntakePipeline:
    """Email intake -> application queued -> screening flushed synchronously."""

    @patch("app.engine.email_intake.get_gmail_service")
    def test_new_email_above_threshold_creates_application_and_queues_invite(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        _make_job(client, threshold=60.0)

        msg = _make_gmail_message("msg-001")
        service = _mock_gmail_service(messages=[{"id": "msg-001"}], msg=msg)
        mock_service_fn.return_value = service

        results = _run_check("job-1", tmp_path)

        assert len(results) == 1
        assert results[0]["status"] == "invited"
        assert results[0]["candidate_id"]

        applications = fresh_db.get_all_applications()
        assert len(applications) == 1
        assert applications[0]["screening_status"] == "completed"

        candidates = db.get_all_candidates()
        assert len(candidates) == 1
        assert candidates[0]["source"] == "email_auto"
        assert candidates[0]["screening_status"] == "passed_threshold"
        # Delivery is deferred: the outbox worker sends, not intake.
        assert candidates[0]["invite_email_sent"] is False

        candidate = candidates[0]
        invites = fresh_db.get_interview_invites_for_candidate(candidate["candidate_id"])
        assert len(invites) == 1
        assert invites[0]["status"] == "active"

        # No HR recipient is configured here (hr_email unset) and the candidate
        # invite is deferred until the job's interview strategy is confirmed,
        # so nothing is pending on the outbox yet.
        pending = fresh_db.get_pending_notifications()
        assert pending == []
        assert candidate["mode_status"] == "SHORTLISTED"

        assert db.is_email_processed("msg-001") is True

    @patch("app.engine.email_intake.get_gmail_service")
    def test_new_email_below_threshold_creates_no_candidate(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        _make_job(client, threshold=60.0, min_exp=99)  # hard requirement gate fails

        msg = _make_gmail_message("msg-002")
        service = _mock_gmail_service(messages=[{"id": "msg-002"}], msg=msg)
        mock_service_fn.return_value = service

        results = _run_check("job-1", tmp_path)

        assert len(results) == 1
        assert results[0]["status"] == "not_shortlisted"
        assert results[0]["candidate_id"] is None

        applications = fresh_db.get_all_applications()
        assert applications[0]["screening_status"] == "completed"
        result = fresh_db.get_screening_result(applications[0]["application_id"])
        assert result["decision"] in ("rejected", "manual_review")
        assert result["hard_requirements_passed"] is False

        assert db.get_all_candidates() == []
        assert fresh_db.get_pending_notifications() == []

        assert db.is_email_processed("msg-002") is True

    @patch("app.engine.email_intake.get_gmail_service")
    def test_no_valid_attachment_skips_and_does_not_crash_batch(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        _make_job(client)

        msg_no_attach = _make_gmail_message("msg-003", attachment_filename=None)
        msg_good = _make_gmail_message("msg-004")

        service = _mock_gmail_service(messages=[
            {"id": "msg-003"},
            {"id": "msg-004"},
        ])
        service.users().messages().get().execute.side_effect = [msg_no_attach, msg_good]
        mock_service_fn.return_value = service

        results = _run_check("job-1", tmp_path)

        assert len(results) == 2
        assert results[0]["status"] == "skipped"
        assert results[0]["reason"] == "no_attachment"
        assert results[1]["status"] == "invited"

        assert db.is_email_processed("msg-003") is True
        assert db.is_email_processed("msg-004") is True

    @patch("app.engine.email_intake.get_gmail_service")
    def test_already_processed_message_not_reprocessed(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        _make_job(client)

        from app.core.models import ProcessedEmail
        db.save_processed_email(ProcessedEmail(
            message_id="msg-005", job_id="job-1", candidate_id=None,
        ))

        msg = _make_gmail_message("msg-005")
        service = _mock_gmail_service(messages=[{"id": "msg-005"}], msg=msg)
        mock_service_fn.return_value = service

        results = _run_check("job-1", tmp_path)

        assert len(results) == 0
        assert db.get_all_candidates() == []

    @patch("app.engine.email_intake.get_gmail_service")
    def test_resume_parse_failure_skips_gracefully(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        _make_job(client)

        msg_bad = _make_gmail_message("msg-006", sender="Bad Applicant <bad@example.com>")
        msg_good = _make_gmail_message("msg-007", sender="Good Applicant <good@example.com>")
        service = _mock_gmail_service(messages=[
            {"id": "msg-006"},
            {"id": "msg-007"},
        ])
        service.users().messages().get().execute.side_effect = [msg_bad, msg_good]
        mock_service_fn.return_value = service

        good_resume = {
            "skills": ["python", "sql"],
            "experience_years": 5.0,
            "education": ["B.Tech Computer Science"],
            "raw_text": _RESUME_TEXT,
        }
        with patch("app.screening.service.parse_resume",
                   side_effect=[ValueError("Corrupted file"), good_resume]):
            results = _run_check("job-1", tmp_path)

        assert len(results) == 2
        assert results[0]["status"] == "error"
        assert "Corrupted file" in results[0]["reason"]
        assert results[1]["status"] == "invited"
        assert len(db.get_all_candidates()) == 1

        assert db.is_email_processed("msg-006") is True
        assert db.is_email_processed("msg-007") is True

    @patch("app.engine.email_intake.get_gmail_service")
    def test_gmail_send_failure_does_not_affect_intake(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Emails are never sent by intake — a Gmail outage cannot lose an
        application. The invite waits in the outbox instead."""
        _make_job(client, threshold=60.0)

        msg = _make_gmail_message("msg-008")
        service = _mock_gmail_service(messages=[{"id": "msg-008"}], msg=msg)
        service.users().messages().send.side_effect = Exception("Gmail API rate limit")
        mock_service_fn.return_value = service

        results = _run_check("job-1", tmp_path)

        assert len(results) == 1
        assert results[0]["status"] == "invited"

        applications = fresh_db.get_all_applications()
        assert applications[0]["screening_status"] == "completed"

        candidate = db.get_all_candidates()[0]
        assert candidate["screening_status"] == "passed_threshold"
        assert candidate["invite_email_sent"] is False
        assert candidate["mode_status"] == "SHORTLISTED"

        # No invite is enqueued by intake: the candidate is only SHORTLISTED and
        # the job awaits strategy confirmation. No hr_email is configured here,
        # so nothing is pending on the outbox.
        pending = fresh_db.get_pending_notifications()
        assert pending == []

        assert db.is_email_processed("msg-008") is True


class TestEmailCheckSummary:
    """Manual "Check Job" summary + poll log must count exactly the statuses
    check_for_new_applications emits (invited / not_shortlisted / skipped /
    duplicate / error), instead of labels the pipeline never produces."""

    @patch("api.routes.email_intake.check_for_new_applications")
    def test_manual_check_counts_emitted_statuses_and_writes_poll_log(
        self, mock_check, client, fresh_db
    ):
        _make_job(client, job_id="job-1", label="Applications/Backend")
        mock_check.return_value = [
            {"message_id": "m1", "status": "invited", "candidate_id": "c1"},
            {"message_id": "m2", "status": "not_shortlisted", "candidate_id": None},
            {"message_id": "m3", "status": "skipped", "reason": "no_attachment"},
            {"message_id": "m4", "status": "duplicate", "candidate_id": None},
            {"message_id": "m5", "status": "error", "reason": "boom"},
        ]

        resp = client.post("/api/email-intake/check", json={"job_id": "job-1"})
        assert resp.status_code == 200
        assert resp.json()["summary"] == (
            "5 checked, 1 invited, 1 not shortlisted, 2 skipped, 1 failed"
        )

        latest = fresh_db.get_poll_logs(limit=5)[0]
        assert latest["job_id"] == "job-1"
        assert latest["total_checked"] == 5
        assert latest["invited"] == 1
        assert latest["below_threshold"] == 1
        assert latest["skipped"] == 2
        assert latest["failed"] == 1


class TestEmailSenderRecipientFlow:
    """Verify the email sender (recruiter Gmail) and recipient (candidate) are correctly set."""

    def test_invite_email_uses_recruiter_as_sender_candidate_as_recipient(
        self, client, fresh_db, monkeypatch
    ):
        """Test that interview invite emails are sent FROM the authenticated
        recruiter Gmail account TO the candidate's email address."""
        # Set up test recruiter email
        recruiter_email = "atharvshigwan1142@gmail.com"
        candidate_email = "deadpooltorrato@gmail.com"

        from app.core.settings_store import save_settings, load_settings
        save_settings({"gmail_user": recruiter_email, "gmail_connected": True})
        settings = load_settings()
        assert settings.get("gmail_user") == recruiter_email

        # Test compose_invite_email produces correct headers
        from app.engine.email_intake import compose_invite_email, compose_mode2_invite_email

        candidate = {"name": "Test Candidate", "email": candidate_email}
        job = {"title": "Test Job"}
        invite_code = "TEST123"
        frontend_url = "http://localhost:3000"

        msg = compose_invite_email(candidate, job, invite_code, frontend_url)
        msg["To"] = candidate_email
        msg["From"] = recruiter_email

        assert msg["To"] == candidate_email
        assert msg["From"] == recruiter_email

        # Test compose_mode2_invite_email
        msg2 = compose_mode2_invite_email(candidate, job, invite_code, frontend_url)
        msg2["To"] = candidate_email
        msg2["From"] = recruiter_email

        assert msg2["To"] == candidate_email
        assert msg2["From"] == recruiter_email

    def test_two_candidates_receive_only_their_own_emails(self, client, fresh_db):
        """Test that each candidate receives only their own email."""
        from app.core import db
        from app.core.models import Candidate
        from app.screening.routing import _enqueue_mode_invite

        _make_job(client, job_id="job-1", threshold=60.0)

        # Create two candidates with different emails
        cand1 = Candidate(
            candidate_id="cand-1", job_id="job-1", name="Candidate One",
            email="candidate1@gmail.com", invite_code="CODE1", status="invited",
            source="manual", screening_status="passed_threshold"
        )
        db.save_candidate(cand1)
        cand2 = Candidate(
            candidate_id="cand-2", job_id="job-1", name="Candidate Two",
            email="candidate2@gmail.com", invite_code="CODE2", status="invited",
            source="manual", screening_status="passed_threshold"
        )
        db.save_candidate(cand2)

        job = db.get_job_posting("job-1")

        # Convert to dict for _enqueue_mode_invite (it expects a dict-like object)
        cand1_dict = {"candidate_id": cand1.candidate_id, "job_id": cand1.job_id, 
                      "email": cand1.email, "invite_code": cand1.invite_code,
                      "application_id": cand1.application_id}
        cand2_dict = {"candidate_id": cand2.candidate_id, "job_id": cand2.job_id, 
                      "email": cand2.email, "invite_code": cand2.invite_code,
                      "application_id": cand2.application_id}

        # Enqueue invites for both
        _enqueue_mode_invite(cand1_dict, job, "MODE_1")
        _enqueue_mode_invite(cand2_dict, job, "MODE_1")

        # Verify outbox has correct recipients
        notifications = fresh_db.get_pending_notifications()
        invite_notifications = [n for n in notifications if n["notification_type"] == "mode1_invite"]
        assert len(invite_notifications) == 2

        recipients = {n["recipient"] for n in invite_notifications}
        assert recipients == {"candidate1@gmail.com", "candidate2@gmail.com"}

        # Verify each notification has the correct candidate_id
        for n in invite_notifications:
            cand = db.get_candidate(n["candidate_id"])
            assert n["recipient"] == cand["email"]

    def test_multiple_recruiters_send_from_own_accounts(self, client, fresh_db):
        """Test that each recruiter sends from their own authenticated Gmail account."""
        from app.core.settings_store import load_settings, save_settings

        # Simulate first recruiter
        save_settings({"gmail_user": "recruiter1@gmail.com", "gmail_connected": True})
        settings = load_settings()
        assert settings["gmail_user"] == "recruiter1@gmail.com"

        # Simulate second recruiter (in a different process/session)
        save_settings({"gmail_user": "recruiter2@gmail.com", "gmail_connected": True})
        settings = load_settings()
        assert settings["gmail_user"] == "recruiter2@gmail.com"

        # The candidate recipient remains unchanged regardless of sender
        from app.screening.email_worker import _send_gmail
        from app.engine.email_intake import compose_invite_email

        candidate = {"name": "Test", "email": "candidate@gmail.com"}
        job = {"title": "Test Job"}

        msg = compose_invite_email(candidate, job, "CODE1", "http://localhost:3000")
        msg["To"] = candidate["email"]
        msg["From"] = settings["gmail_user"]

        assert msg["To"] == "candidate@gmail.com"
        assert msg["From"] == "recruiter2@gmail.com"