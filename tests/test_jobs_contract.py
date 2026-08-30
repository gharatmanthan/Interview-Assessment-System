"""
Job ID data-contract tests.

Proves the canonical job identifier flows DB -> backend -> API -> public
apply link without ever persisting a blank id. Regression for:

    POST /api/jobs  (frontend sends no job_id)
        -> server assigns & persists a stable id
        -> response returns it
        -> GET /api/public/jobs/{job_id} resolves the same job
        -> POST /api/public/apply/{job_id} links the application to it
"""

import pytest


@pytest.fixture
def resume_txt(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text(
        "Backend engineer with python, sql and rest api experience. "
        "5 years of experience. B.Tech in Computer Science.",
        encoding="utf-8",
    )
    return str(path)


def _payload(title="Java Developer", **overrides):
    payload = {
        "title": title,
        "description": "Build backend services in Java.",
        "required_skills": ["Java", "Spring"],
        "experience_level": "Senior",
        "department": "Software/CS",
    }
    payload.update(overrides)
    return payload


class TestJobIdContract:
    def test_create_assigns_canonical_job_id_when_client_sends_none(self, client):
        resp = client.post("/api/jobs", json=_payload())
        assert resp.status_code == 200
        job = resp.json()
        assert job["job_id"], "server must assign a job_id"
        assert job["title"] == "Java Developer"

        listed = client.get("/api/jobs").json()
        assert all(j["job_id"] for j in listed), "list must never contain blank job ids"
        assert listed[0]["job_id"] == job["job_id"]

    def test_create_ignores_blank_client_job_id(self, client):
        resp = client.post("/api/jobs", json=_payload(job_id=""))
        assert resp.status_code == 200
        job = resp.json()
        assert job["job_id"], "blank client id must be replaced by a server-generated id"

    def test_public_api_resolves_exactly_the_created_job(self, client, public_client):
        created = client.post("/api/jobs", json=_payload(title="Java Developer")).json()
        job_id = created["job_id"]

        public = public_client.get(f"/api/public/jobs/{job_id}")
        assert public.status_code == 200
        body = public.json()
        assert body["job_id"] == job_id
        assert body["title"] == "Java Developer"

    def test_public_apply_links_application_to_created_job(self, client, public_client, resume_txt):
        from app.core import db

        created = client.post("/api/jobs", json=_payload(title="Java Developer")).json()
        job_id = created["job_id"]

        resp = public_client.post(
            f"/api/public/apply/{job_id}",
            data={"name": "Jane Doe", "email": "jane@example.com", "phone": ""},
            files={"resume": ("resume.txt", resume_txt, "text/plain")},
        )
        assert resp.status_code == 202
        application_id = resp.json()["application_id"]

        # The application row must be linked to the created job, never a blank id.
        apps = db.get_applications_for_job(job_id)
        assert [a["application_id"] for a in apps] == [application_id]
        assert all(a.get("job_id") and a["job_id"] == job_id for a in apps)

    def test_two_jobs_keep_distinct_ids_across_the_contract(self, client, public_client):
        a = client.post("/api/jobs", json=_payload(title="Job A")).json()
        b = client.post("/api/jobs", json=_payload(title="Job B")).json()
        assert a["job_id"] and b["job_id"]
        assert a["job_id"] != b["job_id"]

        assert public_client.get(f"/api/public/jobs/{a['job_id']}").json()["title"] == "Job A"
        assert public_client.get(f"/api/public/jobs/{b['job_id']}").json()["title"] == "Job B"