"""
OAuth cleanup tests: client_secret.json is the single source of truth for
the Google OAuth client (Gmail + Calendar); settings.json stores only the
refresh tokens and never mirrors client_id/client_secret.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.core import settings_store
from app.core.oauth_client import load_oauth_client, load_oauth_credentials
from app.core.settings_store import load_settings, save_settings

FAKE_CLIENT_JSON = {
    "installed": {
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "redirect_uris": ["http://localhost"],
    }
}

OBSOLETE_KEYS = (
    "gmail_client_id",
    "gmail_client_secret",
    "calendar_client_id",
    "calendar_client_secret",
)


@pytest.fixture
def client_file(tmp_path):
    path = tmp_path / "client_secret.json"
    path.write_text(json.dumps(FAKE_CLIENT_JSON))
    return path


@pytest.fixture
def pointed_client_file(tmp_path, monkeypatch):
    path = tmp_path / "client_secret.json"
    path.write_text(json.dumps(FAKE_CLIENT_JSON))
    monkeypatch.setattr("app.core.oauth_client.CLIENT_SECRET_PATH", path)
    return path


def test_load_oauth_client_reads_single_source_file(client_file):
    client = load_oauth_client(client_file)
    assert client["client_id"] == "test-client-id.apps.googleusercontent.com"
    assert client["client_secret"] == "test-client-secret"
    assert client["token_uri"] == "https://oauth2.googleapis.com/token"


def test_load_oauth_client_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_oauth_client(tmp_path / "nope.json")


def test_load_oauth_credentials_builds_from_file_plus_refresh(client_file):
    from google.oauth2.credentials import Credentials

    creds = load_oauth_credentials("rt-gmail", client_file)
    assert isinstance(creds, Credentials)
    assert creds.refresh_token == "rt-gmail"
    assert creds.client_id == "test-client-id.apps.googleusercontent.com"
    assert creds.client_secret == "test-client-secret"


def test_load_oauth_credentials_missing_file_returns_none(tmp_path):
    creds = load_oauth_credentials("rt", tmp_path / "missing.json")
    assert creds is None


def test_load_oauth_credentials_empty_refresh_returns_none(client_file):
    assert load_oauth_credentials("", client_file) is None


def test_get_gmail_service_builds_from_file_and_refresh(pointed_client_file, monkeypatch):
    save_settings({"gmail_connected": True, "gmail_refresh_token": "rt-gmail"})
    sentinel = object()
    monkeypatch.setattr("app.engine.email_intake.build", lambda *a, **k: sentinel)
    from app.engine.email_intake import get_gmail_service

    assert get_gmail_service() is sentinel


def test_get_gmail_service_not_connected_returns_none(pointed_client_file, monkeypatch):
    save_settings({"gmail_connected": False})
    monkeypatch.setattr("app.engine.email_intake.build", Mock())
    from app.engine.email_intake import get_gmail_service

    assert get_gmail_service() is None


def test_get_gmail_service_missing_client_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.oauth_client.CLIENT_SECRET_PATH", tmp_path / "missing.json")
    save_settings({"gmail_connected": True, "gmail_refresh_token": "rt-gmail"})
    monkeypatch.setattr("app.engine.email_intake.build", Mock())
    from app.engine.email_intake import get_gmail_service

    assert get_gmail_service() is None


def test_get_calendar_service_builds_from_file_and_refresh(pointed_client_file, monkeypatch):
    save_settings({"calendar_connected": True, "calendar_refresh_token": "rt-cal"})
    sentinel = object()
    monkeypatch.setattr("app.engine.scheduling.build", lambda *a, **k: sentinel)
    from app.engine.scheduling import get_calendar_service

    assert get_calendar_service() is sentinel


def test_get_calendar_service_not_connected_returns_none(pointed_client_file, monkeypatch):
    save_settings({"calendar_connected": False})
    monkeypatch.setattr("app.engine.scheduling.build", Mock())
    from app.engine.scheduling import get_calendar_service

    assert get_calendar_service() is None


def test_run_oauth_flow_persists_only_runtime_state(tmp_path, monkeypatch):
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(json.dumps(FAKE_CLIENT_JSON))
    monkeypatch.setattr("app.core.oauth_client.CLIENT_SECRET_PATH", client_file)
    monkeypatch.setattr("app.engine.email_intake.CLIENT_SECRET_PATH", client_file)

    creds = SimpleNamespace(refresh_token="rt-gmail-new")
    flow = Mock()
    flow.run_local_server.return_value = creds
    flow_cls = Mock()
    flow_cls.from_client_secrets_file.return_value = flow
    monkeypatch.setattr("app.engine.email_intake.InstalledAppFlow", flow_cls)

    build = Mock()
    build.return_value.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "me@test"
    }
    monkeypatch.setattr("app.engine.email_intake.build", build)

    from app.engine.email_intake import run_oauth_flow

    assert run_oauth_flow() == "me@test"

    settings = load_settings()
    assert settings["gmail_connected"] is True
    assert settings["gmail_user"] == "me@test"
    assert settings["gmail_refresh_token"] == "rt-gmail-new"
    assert not any(k in settings for k in OBSOLETE_KEYS)

    on_disk = json.loads(settings_store.SETTINGS_PATH.read_text())
    assert not any(k in on_disk for k in OBSOLETE_KEYS)


def test_run_calendar_oauth_flow_persists_only_runtime_state(tmp_path, monkeypatch):
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(json.dumps(FAKE_CLIENT_JSON))
    monkeypatch.setattr("app.core.oauth_client.CLIENT_SECRET_PATH", client_file)
    monkeypatch.setattr("app.engine.scheduling.CLIENT_SECRET_PATH", client_file)

    creds = SimpleNamespace(refresh_token="rt-cal-new")
    flow = Mock()
    flow.run_local_server.return_value = creds
    flow_cls = Mock()
    flow_cls.from_client_secrets_file.return_value = flow
    monkeypatch.setattr("app.engine.scheduling.InstalledAppFlow", flow_cls)

    build = Mock()
    build.return_value.calendarList.return_value.get.return_value.execute.return_value = {
        "id": "me@test"
    }
    monkeypatch.setattr("app.engine.scheduling.build", build)

    from app.engine.scheduling import run_calendar_oauth_flow

    assert run_calendar_oauth_flow() == "me@test"

    settings = load_settings()
    assert settings["calendar_connected"] is True
    assert settings["calendar_user"] == "me@test"
    assert settings["calendar_refresh_token"] == "rt-cal-new"
    assert not any(k in settings for k in OBSOLETE_KEYS)


def _write_settings_on_disk(data: dict):
    settings_store.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings_store.SETTINGS_PATH.write_text(json.dumps(data))


def test_load_settings_migrates_duplicate_client_fields():
    old_file = {
        "gmail_connected": True,
        "gmail_user": "me@test",
        "gmail_refresh_token": "rt-gmail",
        "gmail_client_id": "old-gmail-id",
        "gmail_client_secret": "old-gmail-secret",
        "calendar_connected": True,
        "calendar_refresh_token": "rt-cal",
        "calendar_client_id": "old-cal-id",
        "calendar_client_secret": "old-cal-secret",
        "camera_index": 7,
    }
    _write_settings_on_disk(old_file)

    settings = load_settings()

    # Duplicate client credentials are gone…
    assert not any(k in settings for k in OBSOLETE_KEYS)
    # …while refresh tokens and unrelated settings survive.
    assert settings["gmail_refresh_token"] == "rt-gmail"
    assert settings["calendar_refresh_token"] == "rt-cal"
    assert settings["camera_index"] == 7
    assert settings["gmail_connected"] is True

    on_disk = json.loads(settings_store.SETTINGS_PATH.read_text())
    assert not any(k in on_disk for k in OBSOLETE_KEYS)
    assert on_disk["gmail_refresh_token"] == "rt-gmail"
    assert on_disk["calendar_refresh_token"] == "rt-cal"
    assert on_disk["camera_index"] == 7


def test_load_settings_does_not_rewrite_when_nothing_to_migrate():
    clean = {"gmail_refresh_token": "rt-gmail", "camera_index": 3}
    _write_settings_on_disk(clean)
    load_settings()
    assert json.loads(settings_store.SETTINGS_PATH.read_text()) == clean


def test_save_settings_never_persists_obsolete_keys():
    save_settings({
        "gmail_connected": True,
        "gmail_refresh_token": "rt-gmail",
        "gmail_client_id": "should-not-persist",
        "calendar_client_secret": "never",
    })
    on_disk = json.loads(settings_store.SETTINGS_PATH.read_text())
    assert not any(k in on_disk for k in OBSOLETE_KEYS)
    assert on_disk["gmail_refresh_token"] == "rt-gmail"
