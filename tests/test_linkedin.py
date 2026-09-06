"""LinkedIn member-posting integration tests.

Every test mocks the LinkedIn HTTP surface (app.engine.linkedin) — nothing in
this file performs a real LinkedIn request or a real post. Requests-level unit
tests monkeypatch requests.post/get outright.
"""
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.core.models import LinkedinConnection
from app.engine import linkedin
from app.engine.linkedin import LinkedInError, LinkedInTimeoutError
from app.engine.linkedin_post import generate_linkedin_post

PUBLIC_BASE = "https://jobs.example.com"
REDIRECT_URI = f"{PUBLIC_BASE}/api/integrations/linkedin/callback"


@pytest.fixture(autouse=True)
def linkedin_app_env(monkeypatch):
    """Dummy LinkedIn app config + a deterministic public origin."""
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "test-client")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setenv("PUBLIC_APP_URL", PUBLIC_BASE)


def _connect_recruiter(username, member_id="m123", token="member-access-token"):
    """Seed a per-recruiter LinkedIn connection directly in the DB."""
    from app.core import db

    db.save_linkedin_connection(LinkedinConnection(
        recruiter_username=username,
        linkedin_member_id=member_id,
        member_name="Ada Lovelace",
        member_email="ada@example.com",
        access_token=token,
        scope=" ".join(linkedin.LINKEDIN_SCOPES),
    ))


def _create_job(client, job_id="job01"):
    resp = client.post("/api/jobs", json={
        "job_id": job_id,
        "title": "Backend Engineer",
        "description": "We are hiring a backend engineer to own the core API.",
        "required_skills": ["Python", "SQL"],
        "experience_level": "Senior",
        "department": "Engineering",
    })
    assert resp.status_code == 200, resp.text
    return job_id


def _auth_url_state(auth_url: str) -> str:
    return parse_qs(urlparse(auth_url).query)["state"][0]


def _good_callback_mocks(monkeypatch, member_id="u987"):
    """Mock the high-level client calls used by /callback."""
    monkeypatch.setattr(linkedin, "exchange_code", lambda code, redirect: {
        "access_token": "exchanged-token",
        "refresh_token": "",
        "expires_in": 5184000,
        "scope": " ".join(linkedin.LINKEDIN_SCOPES),
    })
    monkeypatch.setattr(linkedin, "get_userinfo", lambda token: {
        "sub": member_id, "name": "Ada Lovelace", "email": "ada@example.com",
    })


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

def test_status_disconnected(client):
    body = client.get("/api/integrations/linkedin/status").json()
    assert body["connected"] is False
    assert body["member_author_urn"] == ""


def test_status_connected_returns_identity_without_tokens(client):
    _connect_recruiter("recruiter")
    body = client.get("/api/integrations/linkedin/status").json()
    assert body["connected"] is True
    assert body["member_name"] == "Ada Lovelace"
    assert body["member_email"] == "ada@example.com"
    assert body["member_author_urn"] == "urn:li:person:m123"
    raw = client.get("/api/integrations/linkedin/status").text.lower()
    for secret in ("access_token", "member-access-token", "refresh"):
        assert secret not in raw


def test_status_is_per_recruiter(client):
    from tests.conftest import _register_and_token

    _connect_recruiter("recruiter")
    assert client.get("/api/integrations/linkedin/status").json()["connected"] is True
    second = _register_and_token("recruiter2", "secret123")
    client.headers.update({"Authorization": f"Bearer {second}"})
    assert client.get("/api/integrations/linkedin/status").json()["connected"] is False


# ---------------------------------------------------------------------------
# /connect
# ---------------------------------------------------------------------------

def test_connect_returns_authorization_url_and_stores_state(client):
    from app.core import db

    resp = client.get("/api/integrations/linkedin/connect")
    assert resp.status_code == 200
    auth_url = resp.json()["authorization_url"]
    parsed = urlparse(auth_url)
    assert parsed.netloc == "www.linkedin.com"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["test-client"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert "w_member_social" in query["scope"][0]
    state = query["state"][0]
    assert state
    conn = db.get_connection()
    saved = conn.execute(
        "SELECT * FROM linkedin_oauth_states WHERE state = ?", (state,)
    ).fetchone()
    conn.close()
    assert saved is not None
    assert saved["recruiter_username"] == "recruiter"
    assert saved["used_at"] is None


def test_connect_not_configured_returns_503(client, monkeypatch):
    for var in ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_REDIRECT_URI"):
        monkeypatch.delenv(var, raising=False)
    resp = client.get("/api/integrations/linkedin/connect")
    assert resp.status_code == 503
    assert "configured" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /callback
# ---------------------------------------------------------------------------

def test_callback_happy_path_stores_connection_and_redirects(client, monkeypatch):
    from app.core import db

    auth_url = client.get("/api/integrations/linkedin/connect").json()["authorization_url"]
    state = _auth_url_state(auth_url)
    _good_callback_mocks(monkeypatch)

    resp = client.get(
        f"/api/integrations/linkedin/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{PUBLIC_BASE}/settings?linkedin=connected"

    conn = db.get_linkedin_connection("recruiter")
    assert conn is not None
    assert conn["linkedin_member_id"] == "u987"
    assert conn["access_token"] == "exchanged-token"

    consumed = db.get_connection().execute(
        "SELECT used_at FROM linkedin_oauth_states WHERE state = ?", (state,)
    ).fetchone()
    assert consumed["used_at"] is not None


def test_callback_redirects_failed_on_oauth_error(client, monkeypatch):
    auth_url = client.get("/api/integrations/linkedin/connect").json()["authorization_url"]
    state = _auth_url_state(auth_url)
    resp = client.get(
        f"/api/integrations/linkedin/callback?code=abc&state={state}"
        "&error=access_denied&error_description=user+denied",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{PUBLIC_BASE}/settings?linkedin=failed&reason=denied"


def test_callback_bad_state_rejected(client):
    resp = client.get(
        "/api/integrations/linkedin/callback?code=abc&state=bogus",
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_callback_state_replay_rejected(client, monkeypatch):
    auth_url = client.get("/api/integrations/linkedin/connect").json()["authorization_url"]
    state = _auth_url_state(auth_url)
    _good_callback_mocks(monkeypatch)

    first = client.get(
        f"/api/integrations/linkedin/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert first.status_code == 302
    second = client.get(
        f"/api/integrations/linkedin/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert second.status_code == 400


def test_callback_expired_state_rejected(client):
    from app.core import db

    past = datetime.utcnow() - timedelta(minutes=30)
    db.save_linkedin_oauth_state("stale", "recruiter", REDIRECT_URI, past, past)
    resp = client.get(
        "/api/integrations/linkedin/callback?code=abc&state=stale",
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_callback_redirect_uri_mismatch_rejected(client, monkeypatch):
    auth_url = client.get("/api/integrations/linkedin/connect").json()["authorization_url"]
    state = _auth_url_state(auth_url)
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://evil.example.com/cb")
    resp = client.get(
        f"/api/integrations/linkedin/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_callback_exchange_failure_redirects_failed(client, monkeypatch):
    auth_url = client.get("/api/integrations/linkedin/connect").json()["authorization_url"]
    state = _auth_url_state(auth_url)

    def _fail(*a, **k):
        raise LinkedInError("Token exchange failed", status=400, code="invalid_grant")

    monkeypatch.setattr(linkedin, "exchange_code", _fail)
    resp = client.get(
        f"/api/integrations/linkedin/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{PUBLIC_BASE}/settings?linkedin=failed"


# ---------------------------------------------------------------------------
# /disconnect
# ---------------------------------------------------------------------------

def test_disconnect_removes_connection(client):
    _connect_recruiter("recruiter")
    assert client.get("/api/integrations/linkedin/status").json()["connected"] is True
    assert client.post("/api/integrations/linkedin/disconnect").status_code == 200
    assert client.get("/api/integrations/linkedin/status").json()["connected"] is False
    _create_job(client)
    pub = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Hiring!"})
    assert pub.status_code == 409
    assert "Connect" in pub.json()["detail"]


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

def test_preview_is_offline_deterministic_and_uses_public_url(client, monkeypatch):
    _create_job(client)
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise AssertionError("preview must never call LinkedIn")

    monkeypatch.setattr(linkedin, "create_post", _boom)
    monkeypatch.setattr(linkedin, "exchange_code", _boom)
    monkeypatch.setattr(linkedin, "get_userinfo", _boom)

    first = client.post("/api/jobs/job01/linkedin/preview").json()
    second = client.post("/api/jobs/job01/linkedin/preview").json()
    assert calls["n"] == 0
    assert first == second
    assert "Backend Engineer" in first["content"]
    assert "Python" in first["content"]
    assert first["public_url"] == f"{PUBLIC_BASE}/apply?jobId=job01"
    assert first["linkedin_post_status"] == "NOT_POSTED"
    assert first["connected"] is False


def test_preview_requires_owner(client):
    from tests.conftest import _register_and_token

    _create_job(client)
    second = _register_and_token("recruiter2", "secret123")
    client.headers.update({"Authorization": f"Bearer {second}"})
    assert client.post("/api/jobs/job01/linkedin/preview").status_code == 403


def test_preview_missing_job(client):
    assert client.post("/api/jobs/nope/linkedin/preview").status_code == 404


def test_preview_reflects_published_status_and_connection(client, monkeypatch):
    _create_job(client)
    _connect_recruiter("recruiter")
    monkeypatch.setattr(linkedin, "create_post", lambda *a, **k: "urn:li:share:111")
    client.post("/api/jobs/job01/linkedin/publish", json={"content": "Hiring!"})
    body = client.post("/api/jobs/job01/linkedin/preview").json()
    assert body["linkedin_post_status"] == "PUBLISHED"
    assert body["connected"] is True


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------

def test_publish_success_persists_post_and_backend_author(client, monkeypatch):
    from app.core import db

    _create_job(client)
    _connect_recruiter("recruiter")
    captured = {}

    def _create(access_token, author_urn, commentary):
        captured.update(access_token=access_token, author=author_urn,
                        commentary=commentary)
        return "urn:li:share:abc123"

    monkeypatch.setattr(linkedin, "create_post", _create)
    resp = client.post("/api/jobs/job01/linkedin/publish", json={
        "content": "Hiring a Backend Engineer — apply now!",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["linkedin_post_status"] == "PUBLISHED"
    assert body["post_id"] == "urn:li:share:abc123"
    assert body["post_url"] == "https://www.linkedin.com/feed/update/urn:li:share:abc123"
    # Author identity is derived from the stored member id, not from the client.
    assert captured["author"] == "urn:li:person:m123"
    assert captured["access_token"] == "member-access-token"
    assert captured["commentary"] == "Hiring a Backend Engineer — apply now!"

    job = db.get_job_posting("job01")
    assert job["linkedin_post_status"] == "PUBLISHED"
    assert job["linkedin_author_urn"] == "urn:li:person:m123"
    assert job["linkedin_posted_at"]


def test_publish_requires_connection(client):
    _create_job(client)
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Hi"})
    assert resp.status_code == 409


def test_publish_already_published_is_rejected_without_second_call(client, monkeypatch):
    _create_job(client)
    _connect_recruiter("recruiter")
    monkeypatch.setattr(linkedin, "create_post", lambda *a, **k: "urn:li:share:1")
    assert client.post("/api/jobs/job01/linkedin/publish",
                       json={"content": "First"}).status_code == 200

    calls = {"n": 0}

    def _count(*a, **k):
        calls["n"] += 1
        return "urn:li:share:2"

    monkeypatch.setattr(linkedin, "create_post", _count)
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Second"})
    assert resp.status_code == 409
    assert calls["n"] == 0


def _authed_client():
    from api.main import app
    from app.core import db
    from fastapi.testclient import TestClient
    from tests.conftest import _register_and_token

    db.init_db()
    token = _register_and_token("recruiter", "secret123")
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    _create_job(client)
    _connect_recruiter("recruiter")
    return client


@pytest.mark.parametrize("linkedin_status,linkedin_code", [
    (401, "UNAUTHENTICATED"),
    (403, "UNAUTHORIZED"),
    (429, "RATE_LIMITED"),
    (500, "INTERNAL_ERROR"),
    (503, "SERVICE_UNAVAILABLE"),
])
def test_publish_definitive_failures_mark_failed(monkeypatch, linkedin_status, linkedin_code):
    from app.core import db

    client = _authed_client()

    def _fail(access_token, author_urn, commentary):
        raise LinkedInError("Rejected", status=linkedin_status, code=linkedin_code)

    monkeypatch.setattr(linkedin, "create_post", _fail)
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Post"})
    assert resp.status_code == 502
    job = db.get_job_posting("job01")
    assert job["linkedin_post_status"] == "FAILED"
    assert job["linkedin_last_error"]
    assert "token" not in job["linkedin_last_error"].lower()


def test_publish_timeout_stays_publishing_then_stale_recovery(monkeypatch):
    from app.core import db

    client = _authed_client()
    calls = {"n": 0}

    def _timeout(*a, **k):
        calls["n"] += 1
        raise LinkedInTimeoutError("timed out")

    monkeypatch.setattr(linkedin, "create_post", _timeout)
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Post"})
    assert resp.status_code == 502
    assert "verify" in resp.json()["detail"].lower()
    assert db.get_job_posting("job01")["linkedin_post_status"] == "PUBLISHING"

    # A fresh in-flight claim refuses a second publish (no duplicate post).
    monkeypatch.setattr(linkedin, "create_post", lambda *a, **k: "urn:li:share:stale")
    blocked = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Post"})
    assert blocked.status_code == 409
    assert calls["n"] == 1

    # Age the claim past the stale window => crashed-worker recovery republishes.
    cur = db.get_connection().execute(
        "UPDATE job_postings SET linkedin_claim_started_at = ? WHERE job_id = ?",
        (str(datetime.utcnow() - timedelta(minutes=10)), "job01"),
    )
    cur.connection.commit()
    ok = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Post"})
    assert ok.status_code == 200
    assert ok.json()["linkedin_post_status"] == "PUBLISHED"


def test_publish_requires_owner(client):
    from tests.conftest import _register_and_token

    _create_job(client)
    _connect_recruiter("recruiter")
    second = _register_and_token("recruiter2", "secret123")
    client.headers.update({"Authorization": f"Bearer {second}"})
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Hi"})
    assert resp.status_code == 403


def test_publish_missing_job(client):
    resp = client.post("/api/jobs/nope/linkedin/publish", json={"content": "Hi"})
    assert resp.status_code == 404


@pytest.mark.parametrize("content", ["", "   "])
def test_publish_rejects_blank_content(client, content):
    _create_job(client)
    _connect_recruiter("recruiter")
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": content})
    assert resp.status_code == 400


def test_publish_rejects_oversized_content(client):
    _create_job(client)
    _connect_recruiter("recruiter")
    resp = client.post("/api/jobs/job01/linkedin/publish", json={
        "content": "x" * (linkedin.MAX_POST_CHARS + 1),
    })
    assert resp.status_code == 400


def test_publish_not_configured_returns_503(client, monkeypatch):
    _create_job(client)
    _connect_recruiter("recruiter")
    for var in ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_REDIRECT_URI"):
        monkeypatch.delenv(var, raising=False)
    resp = client.post("/api/jobs/job01/linkedin/publish", json={"content": "Hi"})
    assert resp.status_code == 503


def test_job_edit_preserves_published_state(client, monkeypatch):
    from app.core import db

    _create_job(client)
    _connect_recruiter("recruiter")
    monkeypatch.setattr(linkedin, "create_post", lambda *a, **k: "urn:li:share:keep")
    client.post("/api/jobs/job01/linkedin/publish", json={"content": "First"})

    resp = client.put("/api/jobs/job01", json={
        "job_id": "job01",
        "title": "Backend Engineer (Edited)",
        "description": "Updated description.",
        "required_skills": ["Python", "SQL", "Docker"],
        "experience_level": "Senior",
        "department": "Engineering",
    })
    assert resp.status_code == 200
    job = db.get_job_posting("job01")
    assert job["linkedin_post_status"] == "PUBLISHED"
    assert job["linkedin_post_url"] == "https://www.linkedin.com/feed/update/urn:li:share:keep"


# ---------------------------------------------------------------------------
# app.engine.linkedin unit tests (mocked requests — no network)
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code, json_body=None, headers=None):
        self.status_code = status_code
        self.content = b"{}"
        self.headers = headers or {}
        self.text = "{}"
        self._json = json_body if json_body is not None else {}

    def json(self):
        return self._json


class TestCreatePostClient:
    def test_create_post_builds_request_and_parses_id_header(self, monkeypatch):
        captured = {}

        def _post(url, json=None, headers=None, timeout=...):
            captured.update(url=url, json=json, headers=headers, timeout=timeout)
            return _FakeResponse(201, headers={"x-restli-id": "urn:li:share:987"})

        monkeypatch.setattr(requests, "post", _post)
        post_id = linkedin.create_post("tok", "urn:li:person:42", "Hello LinkedIn")
        assert post_id == "urn:li:share:987"
        assert captured["url"] == linkedin.POSTS_URL
        assert captured["headers"]["Authorization"] == "Bearer tok"
        assert captured["headers"]["X-Restli-Protocol-Version"] == "2.0.0"
        assert captured["headers"]["LinkedIn-Version"] == linkedin.LINKEDIN_API_VERSION
        assert captured["json"]["author"] == "urn:li:person:42"
        assert captured["json"]["commentary"] == "Hello LinkedIn"
        assert captured["json"]["lifecycleState"] == "PUBLISHED"
        assert captured["json"]["visibility"] == "PUBLIC"

    def test_create_post_non_201_raises_linkedin_error(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(
            403, {"code": "UNAUTHORIZED", "message": "no permission"}))
        with pytest.raises(LinkedInError) as exc:
            linkedin.create_post("tok", "urn:li:person:42", "x")
        assert exc.value.status == 403
        assert "no permission" in exc.value.message

    def test_create_post_201_without_id_raises(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(201))
        with pytest.raises(LinkedInError) as exc:
            linkedin.create_post("tok", "urn:li:person:42", "x")
        assert exc.value.status == 201

    def test_create_post_timeout_raises_timeout_error(self, monkeypatch):
        def _timeout(*a, **k):
            raise requests.Timeout("slow")

        monkeypatch.setattr(requests, "post", _timeout)
        with pytest.raises(LinkedInTimeoutError):
            linkedin.create_post("tok", "urn:li:person:42", "x")


class TestOAuthClient:
    def test_exchange_code_parses_tokens(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(
            200, {"access_token": "at", "refresh_token": "rt",
                  "expires_in": 3600, "scope": "w_member_social"}))
        tokens = linkedin.exchange_code("code", REDIRECT_URI)
        assert tokens["access_token"] == "at"
        assert tokens["refresh_token"] == "rt"
        assert tokens["expires_in"] == 3600

    def test_exchange_code_failure_raises(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(
            400, {"error": "invalid_grant", "error_description": "bad code"}))
        with pytest.raises(LinkedInError) as exc:
            linkedin.exchange_code("code", REDIRECT_URI)
        assert exc.value.status == 400
        assert exc.value.code == "invalid_grant"

    def test_get_userinfo_derives_member_id(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(
            200, {"sub": "u55", "name": "Ada", "email": "a@x.io"}))
        info = linkedin.get_userinfo("tok")
        assert info["sub"] == "u55"
        assert linkedin.member_author_urn(info["sub"]) == "urn:li:person:u55"

    def test_get_userinfo_rejects_when_scope_missing(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(
            403, {"code": "FORBIDDEN", "message": "no scope"}))
        with pytest.raises(LinkedInError) as exc:
            linkedin.get_userinfo("tok")
        assert exc.value.status == 403


def test_generate_linkedin_post_is_deterministic_and_omits_missing_fields():
    job = {
        "title": "  Backend Engineer  ",
        "experience_level": "Senior",
        "department": "Engineering",
        "required_skills": ["python", "SQL"],
        "description": "Some descriptive text. Second sentence.",
    }
    url = "https://jobs.example.com/apply?jobId=j"
    post = generate_linkedin_post(job, url)
    assert "Backend Engineer" in post
    assert "Senior" in post
    assert "Engineering" in post
    assert "python" in post
    assert "jobs.example.com" in post
    assert post == generate_linkedin_post(job, url)

    sparse = generate_linkedin_post({"title": "Solo Role"}, "https://x/apply?jobId=1")
    assert "Experience" not in sparse
    assert "Department" not in sparse
    assert "Key skills" not in sparse
    assert "Solo Role" in sparse
    assert len(sparse) <= linkedin.MAX_POST_CHARS