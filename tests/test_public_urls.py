"""
External-candidate URL correctness.

These guard the invariant that every candidate-facing link (application link
for LinkedIn, and /candidate/entry invite links in emails) is built from the
PUBLIC_APP_URL frontend origin — never from remote_api_url (the API origin,
which does not serve the Next.js routes) and never from a machine-localhost.
"""
import pytest


# ---------------------------------------------------------------------------
# Candidate invite email links
# ---------------------------------------------------------------------------

def test_mode2_invite_link_uses_public_app_url(monkeypatch):
    from app.screening.email_worker import _frontend_url
    from app.engine.email_intake import compose_mode2_invite_email

    monkeypatch.setenv("PUBLIC_APP_URL", "https://frontend.example.com")
    url = _frontend_url()
    msg = compose_mode2_invite_email(
        {"name": "Jane", "email": "jane@example.com"},
        {"title": "Backend Engineer"},
        "CODE-123",
        url,
    )
    payload = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
    assert "https://frontend.example.com/candidate/entry?code=CODE-123" in payload


def test_promotion_link_uses_public_app_url(monkeypatch):
    from app.screening.email_worker import _frontend_url
    from app.engine.email_intake import compose_promotion_email

    monkeypatch.setenv("PUBLIC_APP_URL", "https://frontend.example.com")
    url = _frontend_url()
    msg = compose_promotion_email(
        {"name": "Jane", "email": "jane@example.com"},
        {"title": "Backend Engineer"},
        "FINAL-1",
        url,
    )
    payload = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
    assert "https://frontend.example.com/candidate/entry?code=FINAL-1" in payload


def test_invite_link_uses_public_app_url(monkeypatch):
    from app.screening.email_worker import _frontend_url
    from app.engine.email_intake import compose_invite_email

    monkeypatch.setenv("PUBLIC_APP_URL", "https://frontend.example.com")
    url = _frontend_url()
    msg = compose_invite_email(
        {"name": "Jane", "email": "jane@example.com"},
        {"title": "Backend Engineer"},
        "INV-1",
        url,
    )
    payload = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
    assert "https://frontend.example.com/candidate/entry?code=INV-1" in payload


# ---------------------------------------------------------------------------
# Email worker's frontend origin resolution
# ---------------------------------------------------------------------------

def test_email_worker_frontend_url_uses_public_app_url(monkeypatch):
    from app.screening.email_worker import _frontend_url

    monkeypatch.setenv("PUBLIC_APP_URL", "https://frontend.example.com")
    assert _frontend_url() == "https://frontend.example.com"


def test_email_worker_frontend_url_never_uses_remote_api_url(monkeypatch, tmp_path):
    """Even in remote mode with remote_api_url set, invite links must point at
    the frontend origin (PUBLIC_APP_URL), never at the API origin."""
    from app.core.settings_store import load_settings, save_settings

    settings = load_settings()
    settings["backend_mode"] = "remote"
    settings["remote_api_url"] = "https://api.example.com"
    save_settings(settings)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://frontend.example.com")

    from app.screening.email_worker import _frontend_url
    assert _frontend_url() == "https://frontend.example.com"
    assert "api.example.com" not in _frontend_url()


# ---------------------------------------------------------------------------
# Public application URL (application link for LinkedIn)
# ---------------------------------------------------------------------------

def test_public_apply_url_uses_public_app_url(monkeypatch):
    from app.core.settings_store import public_apply_url

    monkeypatch.setenv("PUBLIC_APP_URL", "https://frontend.example.com")
    assert (
        public_apply_url("job01")
        == "https://frontend.example.com/apply?jobId=job01"
    )