"""
Regression tests for the canonical ATS screening implementation.

The SAME job (b039253996164d19a036887ae82df2cf, "Java Developer"), the SAME
resume and the SAME candidate must yield IDENTICAL scores, matched/missing
skills, hard-requirement verdicts and decisions regardless of ingestion path:

  Path A — public application -> create_application_and_queue + screen_application
  Path C — manual invite       -> POST /api/candidates/{id}/resume
  Path D — re-screen           -> requeue + screen_application (again)

Every test also asserts persistence: candidates.match_score mirrors
screening_results.ats_score — one authoritative number, never two divergent
computations (this is the discrepancy the fix removes).
"""
import io

import pytest

from app.core.models import JobPosting
from app.screening.service import create_application_and_queue, screen_application

JAVA_JOB_ID = "b039253996164d19a036887ae82df2cf"

JAVA_RESUME_TEXT = (
    "AARAV MEHTA\n"
    "Senior Java Developer with 6+ years of experience building microservices "
    "and rest api using java and sql. Spring Boot expertise in production.\n"
    "B.Tech in Computer Science\n"
)

COMPARED_FIELDS = (
    "matched_skills",
    "missing_skills",
    "hard_requirements_passed",
    "hard_requirement_failures",
    "decision",
    "decision_reason",
    "matcher_method",
)


def _java_job(**overrides):
    fields = dict(
        job_id=JAVA_JOB_ID,
        title="Java Developer",
        description=(
            "We are looking for a Java Developer to build microservices and "
            "rest api using java and sql, with strong Spring Boot experience."
        ),
        required_skills=["java", "sql", "microservices", "rest api"],
        experience_level="Senior",
        department="Engineering",
        num_rounds=1,
        time_limit_seconds=120,
        adaptive_difficulty=True,
        competency_weights={},
        screening_threshold=60.0,
        screening_enabled=True,
        auto_invite_enabled=True,
        minimum_experience_years=5,
        required_education="",
        screening_weights={"skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10},
    )
    fields.update(overrides)
    return fields


@pytest.fixture
def java_job(fresh_db):
    fresh_db.save_job_posting(JobPosting(**_java_job()))
    return fresh_db.get_job_posting(JAVA_JOB_ID)


@pytest.fixture
def java_resume(tmp_path):
    path = tmp_path / "java_resume.txt"
    path.write_text(JAVA_RESUME_TEXT, encoding="utf-8")
    return str(path)


def _manual_candidate(client, candidate_id, email):
    resp = client.post(
        "/api/candidates",
        json={"candidate_id": candidate_id, "job_id": JAVA_JOB_ID,
              "name": "Aarav Mehta", "email": email},
    )
    assert resp.status_code == 200


def _upload_resume(client, candidate_id, resume_bytes):
    return client.post(
        f"/api/candidates/{candidate_id}/resume",
        files={"file": ("resume.txt", io.BytesIO(resume_bytes), "text/plain")},
    )


def test_same_candidate_same_resume_same_score_across_all_paths(
    client, fresh_db, java_job, java_resume
):
    email = "aarav.mehta@example.com"
    _manual_candidate(client, "manual-java-1", email)

    # Path C: manual candidate + resume upload (the path that previously
    # diverged by storing the raw matcher match_score instead of the ATS result).
    with open(java_resume, "rb") as fh:
        up = client.post(
            "/api/candidates/manual-java-1/resume",
            files={"file": ("resume.txt", fh, "text/plain")},
        )
    assert up.status_code == 200
    manual = up.json()
    manual_screening = manual["screening_result"]
    assert manual_screening is not None

    # Path A: public application using the SAME resume and the SAME candidate
    # email (the pipeline reuses the manually-created candidate row).
    app = create_application_and_queue(
        job=java_job,
        full_name="Aarav Mehta",
        email=email,
        resume_path=java_resume,
        source="apply_portal",
    )
    screen_application(app.application_id)
    apply_screening = fresh_db.get_screening_result(app.application_id)

    # Path D: re-screen the same application.
    fresh_db.requeue_screening(app.application_id)
    screen_application(app.application_id)
    rescreen_screening = fresh_db.get_screening_result(app.application_id)

    expected = apply_screening["ats_score"]
    assert manual_screening["ats_score"] == expected
    assert rescreen_screening["ats_score"] == expected
    for key in COMPARED_FIELDS:
        assert manual_screening[key] == apply_screening[key] == rescreen_screening[key]

    # The persisted match_score IS the canonical ATS score, not a raw matcher value.
    assert manual["match_score"] == expected

    # The candidate row mirrors the same authoritative number.
    cand = fresh_db.get_candidate("manual-java-1")
    assert cand["match_score"] == expected
    assert cand["matched_skills"] == manual_screening["matched_skills"]

    # The recruiter list endpoints read the canonical result for manual candidates.
    listed = client.get(f"/api/candidates/job/{JAVA_JOB_ID}").json()
    manual_entry = [c for c in listed if c["candidate_id"] == "manual-java-1"][0]
    assert manual_entry["screening_result"]["ats_score"] == expected
    assert manual_entry["screening_result"]["decision"] == "passed"

    # Re-screening refreshed the decision even though the candidate row predates it.
    assert cand["screening_status"] == "passed_threshold"
    assert fresh_db.get_candidate_by_email_job(email, JAVA_JOB_ID)["candidate_id"] == "manual-java-1"


def test_same_resume_parses_identically_across_paths(client, fresh_db, java_job, java_resume):
    from app.engine.resume_parser import parse_resume

    email = "aarav.parsed@example.com"
    _manual_candidate(client, "manual-java-2", email)
    with open(java_resume, "rb") as fh:
        up = _upload_resume(client, "manual-java-2", fh.read())
    assert up.status_code == 200
    manual = up.json()

    app = create_application_and_queue(
        job=java_job,
        full_name="Aarav Mehta",
        email=email,
        resume_path=java_resume,
        source="apply_portal",
    )
    service_parsed = parse_resume(app.resume_path)

    assert set(manual["resume_skills"]) == set(service_parsed["skills"])
    assert manual["experience_years"] == service_parsed.get("experience_years")


def test_changing_job_config_legitimately_changes_score(client, fresh_db, java_job, java_resume):
    app = create_application_and_queue(
        job=java_job,
        full_name="Binu Patel",
        email="binu@example.com",
        resume_path=java_resume,
        source="apply_portal",
    )
    screen_application(app.application_id)
    base = fresh_db.get_screening_result(app.application_id)
    assert base["ats_score"] == 100.0
    assert base["decision"] == "passed"

    # Raise the bar: add a required skill the resume does not demonstrate.
    # "pandas" is a recognized skill, so the matcher now reports it missing
    # too: skills 80 / semantic 80 / keyword 80, experience 100.
    fresh_db.save_job_posting(JobPosting(**_java_job(
        required_skills=["java", "sql", "microservices", "rest api", "pandas"])))

    fresh_db.requeue_screening(app.application_id)
    screen_application(app.application_id)
    changed = fresh_db.get_screening_result(app.application_id)
    assert changed["ats_score"] == 84.4  # canonical recompute, far from base
    assert changed["ats_score"] != base["ats_score"]
    assert changed["skills_score"] == 80.0
    assert "pandas" in changed["missing_skills"]

    # Deterministic: re-running produces the identical canonical result.
    fresh_db.requeue_screening(app.application_id)
    screen_application(app.application_id)
    rerun = fresh_db.get_screening_result(app.application_id)
    assert rerun["ats_score"] == changed["ats_score"]

    # The candidate row follows the refreshed canonical number.
    cand = fresh_db.get_candidate_by_email_job("binu@example.com", JAVA_JOB_ID)
    assert cand["match_score"] == changed["ats_score"]