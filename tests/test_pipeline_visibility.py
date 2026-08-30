"""
Pipeline-level acceptance covering the MASTER-PROMPT screening gaps:

* Sec 19/46 — the candidates list is exactly the passed shortlist; rejected
  and manual-review applicants never become candidates (backend enforced);
* Sec 24    — per-job pipeline funnel counts on GET /api/applications/stats;
* Sec 6/7   — the screening result persists the threshold actually used;
* Sec 22/48 — explicit re-screen requeues + recomputes, keeps a durable
  decision audit trail in application_events, never creates duplicate
  candidates, and is ownership-scoped.
"""
import io

from fastapi.testclient import TestClient

from api.main import app as api_app
from app.core import db
from app.screening.service import run_screening_jobs
from tests.conftest import _register_and_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESUME_TEXT = (
    "Jane Doe\n"
    "Backend engineer with python, sql and rest api experience. "
    "5 years of experience. B.Tech in Computer Science.\n"
)


def _make_job(client, job_id="job-vis-1", threshold=60.0,
              description="We need python and sql skills.",
              minimum_experience_years=None):
    payload = {
        "job_id": job_id,
        "title": "Backend Engineer",
        "description": description,
        "required_skills": ["Python", "SQL"],
        "experience_level": "Junior",
        "department": "Engineering",
        "screening_threshold": threshold,
        "application_gmail_label": "",
    }
    if minimum_experience_years is not None:
        payload["minimum_experience_years"] = minimum_experience_years
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 200, resp.text


def _update_job_json(client, job_id, **overrides):
    job = next(j for j in client.get("/api/jobs").json() if j["job_id"] == job_id)
    job.update(overrides)
    resp = client.put(f"/api/jobs/{job_id}", json=job)
    assert resp.status_code == 200, resp.text


def _resume_file():
    return ("resume.txt", io.BytesIO(_RESUME_TEXT.encode()), "text/plain")


def _apply(client, job_id="job-vis-1", name="Jane Doe", email="jane@example.com"):
    resp = client.post(
        f"/api/public/apply/{job_id}",
        data={"name": name, "email": email},
        files={"resume": _resume_file()},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["application_id"]


def _flow(client, job_id, email, **job_kwargs):
    """Create job + apply + run the worker synchronously; return application."""
    _make_job(client, job_id=job_id, **job_kwargs)
    app_id = _apply(client, job_id=job_id, email=email)
    run_screening_jobs()
    return db.get_application(app_id)


# ---------------------------------------------------------------------------
# Sec 19/46 — candidate visibility
# ---------------------------------------------------------------------------

class TestCandidateVisibility:

    def test_rejected_never_becomes_candidate(self, client, fresh_db):
        app = _flow(client, "job-vis-hard",
                    email="hard@example.com", minimum_experience_years=99)
        # hard gate fails -> rejected (not passed)
        assert app["status"] == "rejected"
        assert db.get_all_candidates() == []
        assert client.get("/api/candidates").json() == []
        assert client.get("/api/candidates/job/job-vis-hard").json() == []

    def test_manual_review_never_becomes_candidate(self, client, fresh_db):
        # Learn the deterministic heuristic ats score first, then set a
        # threshold that lands just above it -> manual-review band.
        _flow(client, "job-vis-learn", email="learn@example.com")
        learned_at = db.get_screening_result(
            db.get_all_applications()[0]["application_id"]
        )["ats_score"]
        assert learned_at is not None

        threshold = round(learned_at) + 5
        app = _flow(client, "job-vis-manual", email="manual@example.com",
                    threshold=threshold)
        assert app["status"] == "manual_review"
        assert client.get("/api/candidates/job/job-vis-manual").json() == []
        # the only candidate anywhere came from the learning job, not manual review
        cands = db.get_all_candidates()
        assert [c["job_id"] for c in cands] == ["job-vis-learn"]

    def test_passed_appears_in_candidates_shortlist(self, client, fresh_db):
        app = _flow(client, "job-vis-pass", email="pass@example.com")
        assert app["status"] == "invite_pending"
        cands = client.get("/api/candidates/job/job-vis-pass").json()
        assert len(cands) == 1
        assert cands[0]["email"] == "pass@example.com"


# ---------------------------------------------------------------------------
# Sec 24 — per-job pipeline funnel stats
# ---------------------------------------------------------------------------

class TestPipelineStats:

    def test_stats_counts_funnel_and_scopes_to_recruiter(self, client, fresh_db):
        _flow(client, "job-stats-pass", email="pass@example.com")
        _flow(client, "job-stats-hard", email="hard@example.com",
              minimum_experience_years=99)

        resp = client.get("/api/applications/stats")
        assert resp.status_code == 200
        jobs = {j["job_id"]: j for j in resp.json()["jobs"]}

        passed = jobs["job-stats-pass"]
        assert passed["applications"] == 1
        assert passed["screening_pending"] == 0
        assert passed["shortlisted"] == 1
        assert passed["rejected"] == 0
        assert passed["manual_review"] == 0
        assert passed["invites_sent"] == 0  # outbox pending, Gmail not called
        assert passed["interviews_completed"] == 0
        assert passed["email_failures"] == 0

        hard = jobs["job-stats-hard"]
        assert hard["applications"] == 1
        assert hard["shortlisted"] == 0
        assert hard["rejected"] == 1

        # Ownership: another recruiter sees none of these jobs.
        other = TestClient(api_app)
        other.headers.update({"Authorization": f"Bearer {_register_and_token('recruiter2')}"})
        assert other.get("/api/applications/stats").json()["jobs"] == []

    def test_stats_requires_recruiter_auth(self, public_client, fresh_db):
        resp = public_client.get("/api/applications/stats")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Sec 22/48 — explicit re-screen + audit trail
# ---------------------------------------------------------------------------

class TestRescreen:

    def test_rescreen_recomputes_and_persists_threshold_and_history(self, client, fresh_db):
        app = _flow(client, "job-rs", email="rs@example.com")
        detail = client.get(f"/api/applications/{app['application_id']}").json()
        assert detail["screening_result"]["decision"] == "passed"
        first_events = [e["event"] for e in detail["events"]]
        assert "candidate_created" in first_events
        assert "invite_created" in first_events
        assert "screening_passed" in first_events
        # threshold that was actually used is persisted
        assert detail["screening_result"]["threshold_used"] == 60.0

        # Raise the bar above the deterministic score (the ±10 manual-review
        # band means a threshold of 120 lands the applicant firmly "rejected").
        _update_job_json(client, "job-rs", screening_threshold=120)
        resp = client.post(f"/api/applications/{app['application_id']}/rescreen")
        assert resp.status_code == 200
        assert resp.json()["screening_status"] == "queued"

        events_after_requeue = client.get(
            f"/api/applications/{app['application_id']}"
        ).json()["events"]
        assert events_after_requeue[-1]["event"] == "screening_requeued"

        run_screening_jobs()
        after = db.get_application(app["application_id"])
        assert after["status"] == "rejected"
        assert after["screening_status"] == "completed"

        result = db.get_screening_result(app["application_id"])
        assert result["decision"] == "rejected"
        assert result["threshold_used"] == 120.0
        assert result["decision_reason"].startswith("ATS score")

        # No duplicate candidate from the second run.
        assert len(db.get_all_candidates()) == 1

        # Audit trail still shows the first pass, then the requeue + rejection.
        trail = [e["event"] for e in
                 client.get(f"/api/applications/{app['application_id']}").json()["events"]]
        assert "screening_passed" in trail
        assert trail.index("screening_requeued") < trail.index("screening_rejected")
        assert "screening_failed" not in trail

    def test_rescreen_409_when_already_queued(self, client, fresh_db):
        _flow(client, "job-rs2", email="rs2@example.com")
        app = db.get_all_applications()[0]
        _update_job_json(client, "job-rs2", screening_threshold=99.9)
        assert client.post(f"/api/applications/{app['application_id']}/rescreen").status_code == 200
        # second call while queued/in-flight is refused
        assert client.post(f"/api/applications/{app['application_id']}/rescreen").status_code == 409

    def test_rescreen_is_ownership_scoped(self, fresh_db):
        owner = TestClient(api_app)
        owner.headers.update({"Authorization": f"Bearer {_register_and_token('owner')}"})
        stranger = TestClient(api_app)
        stranger.headers.update({"Authorization": f"Bearer {_register_and_token('stranger')}"})

        _flow(owner, "job-rs3", email="rs3@example.com")
        app_row = db.get_all_applications()[0]
        _update_job_json(owner, "job-rs3", screening_threshold=99.9)

        assert stranger.post(
            f"/api/applications/{app_row['application_id']}/rescreen"
        ).status_code == 403
        assert stranger.get(
            f"/api/applications/{app_row['application_id']}"
        ).status_code == 403