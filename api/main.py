"""FastAPI entry point for local and cloud deployment."""
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from api import persistence as db
from api.routes.interviews import router as interviews_router
from api.routes.shared_data import router as shared_data_router
from api.routes.auth import router as auth_router
from api.routes.public import router as public_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="InterviewIQ API",
        version="0.1.0",
        description="Shared interview-session API for candidate and interviewer clients.",
    )
    configured_origins = os.getenv("CORS_ORIGINS", "*")
    allow_origins = [
        origin.strip() for origin in configured_origins.split(",") if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(interviews_router, prefix="/api/v1")
    application.include_router(shared_data_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(public_router, prefix="/api/v1")
    web_index = Path(__file__).parent.parent / "web" / "index.html"
    application.add_api_route(
        "/",
        lambda: FileResponse(web_index),
        methods=["GET"],
        include_in_schema=False,
    )
    return application


app = create_app()


@app.on_event("startup")
def initialize_database() -> None:
    if not os.getenv("DATABASE_URL", "").strip():
        return
    if not os.getenv("AUTH_SECRET", "").strip():
        raise RuntimeError("AUTH_SECRET must be configured before starting the API.")
    db.init_db()


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "interviewiq-api"}


@app.get("/health/ready", tags=["system"])
def readiness() -> dict[str, str]:
    if not os.getenv("DATABASE_URL", "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        )
    try:
        db.check_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not reachable.",
        ) from exc
    return {"status": "ready", "service": "interviewiq-api"}
