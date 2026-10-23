"""FastAPI entry point for the local-network desktop system."""
import os

from fastapi import FastAPI, HTTPException, status

from api import persistence as db
from api.routes.interviews import router as interviews_router
from api.routes.shared_data import router as shared_data_router
from api.routes.auth import router as auth_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="InterviewIQ API",
        version="0.1.0",
        description="Shared interview-session API for candidate and interviewer clients.",
    )
    application.include_router(interviews_router, prefix="/api/v1")
    application.include_router(shared_data_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    return application


app = create_app()


@app.on_event("startup")
def initialize_database() -> None:
    if not os.getenv("AUTH_SECRET", "").strip():
        raise RuntimeError("AUTH_SECRET must be configured before starting the API.")
    db.init_db()


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "interviewiq-api"}


@app.get("/health/ready", tags=["system"])
def readiness() -> dict[str, str]:
    try:
        db.check_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not reachable.",
        ) from exc
    return {"status": "ready", "service": "interviewiq-api"}
