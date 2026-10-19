"""FastAPI entry point for local and cloud deployment."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from api.routes.interviews import router as interviews_router
from api.routes.shared_data import router as shared_data_router


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
    return application


app = create_app()


@app.on_event("startup")
def initialize_database() -> None:
    db.init_db()


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "interviewiq-api"}
