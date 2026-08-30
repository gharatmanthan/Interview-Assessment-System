"""
Tests for the public apply endpoint (api/routes/public_apply.py).

No real Gmail access. Submission is store-first: 202 + queued screening,
with heavy work (matcher/candidate/email) deferred to the screening worker.
"""
import io

from app.core import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(client, job_id="job-pub-1", threshold=60.0,
              description="We need python and sql skills."):
    client.post("/api/jobs", json={
        "job_id": job_id,
        "title": "Backend Engineer",
        "description": description,
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": threshold,
        "application_gmail_label": "",
    })


_RESUME_TEXT = (
    "Jane Doe\n"
    "Backend engineer with python, sql and rest api experience. "
    "5 years of experience. B.Tech in Computer Science.\n"
)


def _resume_file(filename="resume.txt", content_type="text/plain",
                 data=None):
    return (filename, io.BytesIO(data or _RESUME_TEXT.encode()), content_type)


def _apply(client, job_id="job-pub-1", name="Jane Doe", email="jane@example.com",
           resume=(_resume_file())):
    return client.post(
        f"/api/public/apply/{job_id}",
        data={"name": name, "email": email},
        files={"resume": resume},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPublicJobEndpoint:
    """GET /api/public/jobs/{job_id}"""

    def test_returns_minimal_job_fields(self, client, fresh_db):
        _make_job(client)
        resp = client.get("/api/public/jobs/job-pub-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == "job-pub-1"
        assert body["title"] == "Backend Engineer"
        assert body["description"]
        assert body["required_skills"] == ["Python", "SQL"]
        assert body["experience_level"] == "Junior"
        assert body["department"] == "Engineering"
        # Must NOT leak internal fields
        assert "screening_threshold" not in body
        assert "competency_weights" not in body
        assert "application_gmail_label" not in body
        assert "num_rounds" not in body
        assert "time_limit_seconds" not in body

    def test_404_for_nonexistent_job(self, client, fresh_db):
        resp = client.get("/api/public/jobs/nonexistent-id")
        assert resp.status_code == 404


class TestPublicApplyEndpoint:
    """POST /api/public/apply/{job_id} — store-first, 202, async screening."""

    def test_apply_creates_application_and_queues_screening(self, client, fresh_db):
        _make_job(client)
        resp = _apply(client)
        assert resp.status_code == 202
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "received"
        assert body["application_id"]

        applications = db.get_all_applications()
        assert len(applications) == 1
        assert applications[0]["source"] == "apply_portal"
        assert applications[0]["full_name"] == "Jane Doe"
        assert applications[0]["email"] == "jane@example.com"
        assert applications[0]["status"] == "received"
        assert applications[0]["screening_status"] == "queued"
        assert fresh_db.get_screening_job(body["application_id"])["status"] == "queued"

        # Store-first: nothing heavy ran at request time.
        assert db.get_all_candidates() == []

    def test_apply_screening_run_creates_shortlisted_candidate(self, client, fresh_db):
        _make_job(client, threshold=60.0)
        _apply(client)

        from app.screening.service import screen_application
        app = db.get_all_applications()[0]
        summary = screen_application(app["application_id"])
        assert summary["decision"] == "passed"

        candidates = db.get_all_candidates()
        assert len(candidates) == 1
        assert candidates[0]["source"] == "apply_portal"
        assert candidates[0]["screening_status"] == "passed_threshold"

    def test_apply_duplicate_email_returns_409(self, client, fresh_db):
        _make_job(client)
        assert _apply(client).status_code == 202
        dup = _apply(client, email="jane@example.com")
        assert dup.status_code == 409

        assert len(db.get_all_applications()) == 1

    def test_apply_404_for_nonexistent_job(self, client, fresh_db):
        resp = _apply(client, job_id="nonexistent")
        assert resp.status_code == 404

    def test_apply_inactive_job_rejected(self, client, fresh_db):
        _make_job(client)
        db.set_job_posting_active("job-pub-1", False)
        resp = _apply(client)
        assert resp.status_code == 400

    def test_apply_rejects_invalid_file_type(self, client, fresh_db):
        _make_job(client)
        resp = _apply(client, resume=(
            "malware.exe", io.BytesIO(b"bad"), "application/octet-stream",
        ))
        assert resp.status_code == 400

    def test_apply_rejects_bad_name_or_email(self, client, fresh_db):
        _make_job(client)
        assert _apply(client, name="").status_code == 422
        assert _apply(client, email="not-an-email").status_code == 422

    def test_apply_rejects_empty_resume(self, client, fresh_db):
        _make_job(client)
        resp = _apply(client, resume=("empty.pdf", io.BytesIO(b""), "application/pdf"))
        assert resp.status_code == 400

    def test_resume_parse_failure_surfaces_as_screening_error(self, client, fresh_db):
        """A corrupt resume is recorded at request time; the parse failure
        happens later, in the screening worker, as a retryable job failure."""
        _make_job(client)
        _apply(client, resume=("corrupt.pdf", io.BytesIO(b"\x00\x01"), "application/pdf"))

        from app.screening.service import run_screening_jobs
        run_screening_jobs()

        app = db.get_all_applications()[0]
        assert app["screening_status"] in ("queued", "failed")