import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Import every module that calls dotenv.load_dotenv() at import time BEFORE any
# test runs. A first-time import during a test would re-read the project .env
# and re-add a real GROQ_API_KEY after isolated_env has removed it, silently
# switching screening onto the non-deterministic LLM path. Pre-importing pins
# those side effects to session start so every test starts key-free.
from app.core import settings_store as _settings_store  # noqa: F401
from app.engine import linkedin as _linkedin  # noqa: F401
from app.engine import llm_client as _llm_client  # noqa: F401


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    import app.core.db as db
    import app.core.settings_store as settings_store
    import app.core.database as database
    import api.routes.candidates as candidates_route
    import api.routes.public_apply as public_apply_route
    import api.rate_limit as rate_limit

    # Override SQLite path for testing
    database.get_db_config().set_sqlite_path(tmp_path / "test_app.db")
    # Reset the database engine to pick up the new path
    database.set_database_engine(None)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(candidates_route, "RESUME_DIR", tmp_path / "resumes")
    monkeypatch.setattr(public_apply_route, "RESUME_DIR", tmp_path / "apply_resumes")
    # Background workers would race tests asynchronously; tests drive
    # run_screening_jobs()/send_pending_notifications() explicitly.
    monkeypatch.setenv("INTERVIEWIQ_DISABLE_WORKERS", "1")
    # In-memory rate limiter is shared across tests — reset every test.
    rate_limit.reset_rate_limits()
    # llm_client reads GROQ_API_KEY live from the environment each call, so
    # removing it here guarantees tests exercise the heuristic path unless a
    # test explicitly sets a fake key.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture
def fresh_db():
    from app.core import db

    db.init_db()
    return db


def _register_and_token(username: str = "recruiter", password: str = "secret123") -> str:
    """Create a recruiter directly in the DB and mint a token — avoids the
    HTTP rate limiter that guards /api/auth/register and /api/auth/login."""
    from app.core import db
    from app.core.auth import register_recruiter
    from app.core.tokens import create_token

    register_recruiter(username, password, "Test Recruiter")
    token, _ = create_token(username)
    return token


@pytest.fixture
def client(fresh_db):
    """Authenticated recruiter client — every request carries a Bearer token."""
    from api.main import app

    token = _register_and_token()
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client


@pytest.fixture
def public_client(fresh_db):
    """Unauthenticated client for genuinely public endpoints (apply, candidate flow)."""
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client