import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    import app.core.db as db
    import app.core.settings_store as settings_store
    import api.routes.candidates as candidates_route
    import app.engine.llm_client as llm_client

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_app.db")
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(candidates_route, "RESUME_DIR", tmp_path / "resumes")
    monkeypatch.setattr(llm_client, "GROQ_API_KEY", None)


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
