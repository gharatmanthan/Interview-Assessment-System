"""
Tests for the email intake pipeline (app/engine/email_intake.py).

All Gmail API calls are mocked — no real Gmail access in automated tests.
"""
import base64
from unittest.mock import MagicMock, patch

import pytest

from app.core import db
from app.core.models import JobPosting, Candidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gmail_message(message_id, sender="Jane Applicant <jane@example.com>",
                        subject="Application for Backend Engineer",
                        attachment_filename="resume.pdf", attachment_mime="application/pdf",
                        attachment_data=b"fake resume content"):
    """Build a mock Gmail API message response."""
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


def _make_job(client, job_id="job-1", label="Applications/Backend",
              threshold=60.0, description="We need python and sql skills."):
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
    })


def _mock_gmail_service(messages=None):
    """Create a mock Gmail API service."""
    service = MagicMock()
    if messages is None:
        messages = []
    service.users().messages().list().execute.return_value = {"messages": messages}
    return service


def _mock_resume_data(skills=None, experience_years=3.0):
    return {
        "raw_text": "Jane Doe\nSkills: Python, SQL",
        "skills": skills or ["python", "sql"],
        "experience_years": experience_years,
        "education": ["B.S. Computer Science"],
    }


def _mock_match_result(match_score=75.0, matched=None, missing=None):
    return {
        "match_score": match_score,
        "matched_skills": matched or ["python", "sql"],
        "missing_skills": missing or ["kubernetes"],
        "fit_summary": "Strong match",
        "matched_by": "keyword_overlap",
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestEmailIntakePipeline:
    """6 test cases covering the email intake pipeline."""

    @patch("app.engine.email_intake.get_gmail_service")
    @patch("app.engine.email_intake.match_resume_to_jd")
    @patch("app.engine.email_intake.parse_resume")
    def test_new_email_above_threshold_creates_candidate_and_invites(
        self, mock_parse, mock_match, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Test 1: New email above threshold -> candidate created, invite sent, marked processed."""
        _make_job(client, threshold=60.0)

        msg = _make_gmail_message("msg-001")
        service = _mock_gmail_service(messages=[{"id": "msg-001"}])
        service.users().messages().get().execute.return_value = msg
        mock_service_fn.return_value = service
        mock_parse.return_value = _mock_resume_data()
        mock_match.return_value = _mock_match_result(match_score=75.0)

        with patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"), \
             patch("app.engine.email_intake._download_attachment", return_value=b"fake resume"):
            from app.engine.email_intake import check_for_new_applications
            results = check_for_new_applications("job-1")

        assert len(results) == 1
        assert results[0]["status"] == "invited"
        assert results[0]["match_score"] == 75.0

        candidates = db.get_all_candidates()
        assert len(candidates) == 1
        assert candidates[0]["source"] == "email_auto"
        assert candidates[0]["screening_status"] == "passed_threshold"
        assert candidates[0]["invite_email_sent"] is True
        assert candidates[0]["match_score"] == 75.0

        assert db.is_email_processed("msg-001") is True

    @patch("app.engine.email_intake.get_gmail_service")
    @patch("app.engine.email_intake.match_resume_to_jd")
    @patch("app.engine.email_intake.parse_resume")
    def test_new_email_below_threshold_creates_candidate_no_invite(
        self, mock_parse, mock_match, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Test 2: New email below threshold -> candidate created, no invite sent."""
        _make_job(client, threshold=60.0)

        msg = _make_gmail_message("msg-002")
        service = _mock_gmail_service(messages=[{"id": "msg-002"}])
        service.users().messages().get().execute.return_value = msg
        mock_service_fn.return_value = service
        mock_parse.return_value = _mock_resume_data()
        mock_match.return_value = _mock_match_result(match_score=30.0)

        with patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"), \
             patch("app.engine.email_intake._download_attachment", return_value=b"fake resume"):
            from app.engine.email_intake import check_for_new_applications
            results = check_for_new_applications("job-1")

        assert len(results) == 1
        assert results[0]["status"] == "below_threshold"
        assert results[0]["match_score"] == 30.0

        candidates = db.get_all_candidates()
        assert len(candidates) == 1
        assert candidates[0]["screening_status"] == "below_threshold"
        assert candidates[0]["invite_email_sent"] is False

        assert db.is_email_processed("msg-002") is True

    @patch("app.engine.email_intake.get_gmail_service")
    def test_no_valid_attachment_skips_and_does_not_crash_batch(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Test 3: Email with no valid attachment -> skipped, logged, doesn't crash."""
        _make_job(client)

        # Message with no attachment parts
        msg_no_attach = _make_gmail_message("msg-003", attachment_filename=None)
        msg_good = _make_gmail_message("msg-004")

        service = _mock_gmail_service(messages=[
            {"id": "msg-003"},
            {"id": "msg-004"},
        ])
        service.users().messages().get().execute.side_effect = [msg_no_attach, msg_good]
        mock_service_fn.return_value = service

        with patch("app.engine.email_intake.parse_resume", return_value=_mock_resume_data()), \
             patch("app.engine.email_intake.match_resume_to_jd", return_value=_mock_match_result()), \
             patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"), \
             patch("app.engine.email_intake._download_attachment", return_value=b"fake resume"):
            from app.engine.email_intake import check_for_new_applications
            results = check_for_new_applications("job-1")

        assert len(results) == 2
        assert results[0]["status"] == "skipped"
        assert results[0]["reason"] == "no_attachment"
        assert results[1]["status"] == "invited"

        assert db.is_email_processed("msg-003") is True
        assert db.is_email_processed("msg-004") is True

    @patch("app.engine.email_intake.get_gmail_service")
    @patch("app.engine.email_intake.match_resume_to_jd")
    @patch("app.engine.email_intake.parse_resume")
    def test_already_processed_message_not_reprocessed(
        self, mock_parse, mock_match, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Test 4: Already-processed message ID -> skipped entirely."""
        _make_job(client)

        # Pre-record the message as processed
        from app.core.models import ProcessedEmail
        db.save_processed_email(ProcessedEmail(
            message_id="msg-005", job_id="job-1", candidate_id=None,
        ))

        msg = _make_gmail_message("msg-005")
        service = _mock_gmail_service(messages=[{"id": "msg-005"}])
        service.users().messages().get().execute.return_value = msg
        mock_service_fn.return_value = service

        with patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"):
            from app.engine.email_intake import check_for_new_applications
            results = check_for_new_applications("job-1")

        assert len(results) == 0
        assert db.get_all_candidates() == []
        mock_parse.assert_not_called()

    @patch("app.engine.email_intake.get_gmail_service")
    def test_resume_parse_failure_skips_gracefully(
        self, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Test 5: Resume parse failure -> graceful skip, other emails still processed."""
        _make_job(client)

        msg_bad = _make_gmail_message("msg-006")
        msg_good = _make_gmail_message("msg-007")
        service = _mock_gmail_service(messages=[
            {"id": "msg-006"},
            {"id": "msg-007"},
        ])
        service.users().messages().get().execute.side_effect = [msg_bad, msg_good]
        mock_service_fn.return_value = service

        parse_side_effect = [ValueError("Corrupted file"), _mock_resume_data()]

        with patch("app.engine.email_intake.parse_resume", side_effect=parse_side_effect), \
             patch("app.engine.email_intake.match_resume_to_jd", return_value=_mock_match_result()), \
             patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"), \
             patch("app.engine.email_intake._download_attachment", return_value=b"fake resume"):
            from app.engine.email_intake import check_for_new_applications
            results = check_for_new_applications("job-1")

        assert len(results) == 2
        assert results[0]["status"] == "skipped"
        assert results[0]["reason"] == "parse_failed"
        assert results[1]["status"] == "invited"

        assert db.is_email_processed("msg-006") is True
        assert db.is_email_processed("msg-007") is True

    @patch("app.engine.email_intake.get_gmail_service")
    @patch("app.engine.email_intake.match_resume_to_jd")
    @patch("app.engine.email_intake.parse_resume")
    def test_invite_send_failure_marks_candidate_correctly(
        self, mock_parse, mock_match, mock_service_fn, client, fresh_db, tmp_path
    ):
        """Test 6: Candidate passes threshold but Gmail send fails ->
        candidate exists with passed_threshold, invite_email_sent=False,
        message still processed, no unhandled exception."""
        _make_job(client, threshold=60.0)

        msg = _make_gmail_message("msg-008")
        service = _mock_gmail_service(messages=[{"id": "msg-008"}])
        service.users().messages().get().execute.return_value = msg
        service.users().messages().send.side_effect = Exception("Gmail API rate limit")
        mock_service_fn.return_value = service
        mock_parse.return_value = _mock_resume_data()
        mock_match.return_value = _mock_match_result(match_score=80.0)

        with patch("app.engine.email_intake.RESUME_DIR", tmp_path / "resumes"), \
             patch("app.engine.email_intake._download_attachment", return_value=b"fake resume"):
            from app.engine.email_intake import check_for_new_applications
            results = check_for_new_applications("job-1")

        assert len(results) == 1
        assert results[0]["status"] == "invite_send_failed"
        assert results[0]["match_score"] == 80.0

        candidates = db.get_all_candidates()
        assert len(candidates) == 1
        assert candidates[0]["screening_status"] == "passed_threshold"
        assert candidates[0]["invite_email_sent"] is False
        assert candidates[0]["source"] == "email_auto"

        assert db.is_email_processed("msg-008") is True
