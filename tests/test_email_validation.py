"""
Regression tests for the canonical email validation + normalization.

Covers the shared rule (app/core/validation.py) plus every backend email
boundary: the public application form, the manual candidate-invite API, and
the create_application_and_queue service port (shared by email intake).
Normalization (trim + lowercase) must leave duplicate-email detection intact.
"""
from io import BytesIO

import pytest

from app.core import db
from app.core.models import JobPosting
from app.core.validation import is_valid_email, normalize_email
from app.screening.service import DuplicateApplicationError, create_application_and_queue

VALID_EMAILS = [
    "user@gmail.com",
    "john.doe@company.com",
    "name+jobs@company.co.in",
    "first.last+tag@sub.domain.org",
    "a@b.co",
]

INVALID_EMAILS = [
    "abc",
    "test@",
    "@test.com",
    "test@gmail",
    "test..abc@gmail.com",
    "user@.com",
    "a b@c.com",
    "user test@example.com",
    " ",
]


class TestEmailRules:
    def test_accepts_valid_emails(self):
        for email in VALID_EMAILS:
            assert is_valid_email(email), email

    def test_rejects_invalid_emails(self):
        for email in INVALID_EMAILS:
            assert not is_valid_email(email), email

    def test_normalize_trims_and_lowercases(self):
        assert normalize_email("  USER@Example.COM  ") == "user@example.com"
        assert normalize_email(" user@example.com\t") == "user@example.com"
        assert normalize_email("") == ""

    def test_normalized_email_still_valid(self):
        assert is_valid_email(normalize_email("  USER@Gmail.COM  "))


def _create_job(client, job_id="job-email"):
    resp = client.post("/api/jobs", json={
        "job_id": job_id,
        "title": "Email Engineer",
        "description": "We need python and sql skills.",
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": 50.0,
        "minimum_experience_years": 0,
    })
    assert resp.status_code == 200, resp.text


def _apply(public_client, email, job_id="job-email", name="Jane Doe"):
    return public_client.post(
        f"/api/public/apply/{job_id}",
        data={"name": name, "email": email},
        files={"resume": ("resume.txt", BytesIO(b"python sql 3 years"), "text/plain")},
    )


class TestPublicApplyEmailValidation:
    def test_rejects_invalid_emails(self, client, public_client):
        _create_job(client)
        for email in INVALID_EMAILS:
            resp = _apply(public_client, email)
            assert resp.status_code == 422, email

    def test_accepts_valid_emails(self, client, public_client):
        _create_job(client)
        for email in VALID_EMAILS:
            resp = _apply(public_client, email)
            assert resp.status_code == 202, (email, resp.text)

    def test_normalizes_stored_email(self, client, public_client):
        _create_job(client)
        resp = _apply(public_client, "  JANE.DOE@Company.COM  ")
        assert resp.status_code == 202, resp.text
        assert db.get_application_by_email_job("jane.doe@company.com", "job-email")

    def test_duplicate_detected_after_normalization(self, client, public_client):
        _create_job(client)
        assert _apply(public_client, "  JANE.DOE@company.com  ").status_code == 202
        resp = _apply(public_client, "jane.doe@Company.COM")
        assert resp.status_code == 409, resp.text


def _create_candidate(client, email, candidate_id="cand-email-1"):
    return client.post("/api/candidates", json={
        "candidate_id": candidate_id,
        "job_id": "job-email",
        "name": "Jane Doe",
        "email": email,
    })


class TestCandidateCreateEmailValidation:
    def test_rejects_invalid_emails(self, client):
        _create_job(client)
        for email in INVALID_EMAILS:
            resp = _create_candidate(client, email)
            assert resp.status_code == 422, email

    def test_normalizes_stored_email(self, client):
        _create_job(client)
        resp = _create_candidate(client, "  JANE.DOE@Company.COM  ")
        assert resp.status_code == 200, resp.text
        cand = db.get_candidate_by_email_job("jane.doe@company.com", "job-email")
        assert cand and cand["email"] == "jane.doe@company.com"

    def test_duplicate_email_same_job_rejected(self, client):
        _create_job(client)
        assert _create_candidate(client, "first.candidate@example.com").status_code == 200
        resp = _create_candidate(client, "  FIRST.CANDIDATE@EXAMPLE.COM  ", candidate_id="cand-email-2")
        assert resp.status_code == 409, resp.text


class TestScreeningPortNormalization:
    def test_normalizes_email_before_duplicate_check(self, fresh_db):
        job_posting = JobPosting(
            job_id="job-port",
            title="Port Engineer",
            description="python sql",
            required_skills=[],
            experience_level="Junior",
            department="Engineering",
        )
        db.save_job_posting(job_posting)
        job = db.get_job_posting("job-port")
        result = create_application_and_queue(
            job=job, full_name="Jane Doe", email="  JANE.Doe@Port.Jobs ",
        )
        assert result.email == "jane.doe@port.jobs"
        assert db.get_application_by_email_job("jane.doe@port.jobs", "job-port")

        with pytest.raises(DuplicateApplicationError):
            create_application_and_queue(
                job=job, full_name="Jane Doe", email="jane.doe@PORT.JOBS",
            )