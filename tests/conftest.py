import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    import app.core.db as db
    import app.core.settings_store as settings_store
    import api.routes.candidates as candidates_route

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_app.db")
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(candidates_route, "RESUME_DIR", tmp_path / "resumes")
    # llm_client reads GROQ_API_KEY live from the environment each call, so
    # removing it here guarantees tests exercise the heuristic path unless a
    # test explicitly sets a fake key.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture
def fresh_db():
    from app.core import db

    db.init_db()
    return db


@pytest.fixture
def client(fresh_db):
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client
