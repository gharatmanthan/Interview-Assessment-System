"""
FastAPI application entry point.
Spawns as a child process from Electron, serves on a random port.
"""
import sys
import os
import asyncio
import argparse
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from app.core.database import get_database_engine
from app.core.paths import get_uploads_dir
from api.routes import (
    auth, jobs, candidates, sessions, scoring, reports, integrity, settings,
    devices, candidate_flow, email_intake, public_apply, scheduling,
    applications, media, linkedin, questions, live,
)
logger = logging.getLogger(__name__)

_bg_poll_task = None


def _workers_enabled() -> bool:
    """Check if in-process workers should run."""
    return os.environ.get("INTERVIEWIQ_DISABLE_WORKERS", "") != "1"


def _is_remote_mode() -> bool:
    """Check if running in remote/deployed mode."""
    return os.environ.get("DEPLOY_MODE") == "remote"


async def _background_poll():
    """Periodically check Gmail for new applications (remote mode only)."""
    while True:
        await asyncio.sleep(600)  # every 10 minutes
        try:
            from app.core.settings_store import load_settings
            from app.engine.email_intake import (
                check_for_new_applications,
                summarize_poll_results,
            )
            settings = load_settings()
            if settings.get("backend_mode") != "remote":
                continue
            if not settings.get("gmail_connected"):
                continue
            jobs_with_labels = db.get_jobs_with_gmail_labels()
            for job in jobs_with_labels:
                try:
                    results = check_for_new_applications(job["job_id"])
                    total = len(results)
                    invited, below, skipped, failed = summarize_poll_results(results)
                    if total > 0:
                        db.save_poll_log(
                            job_id=job["job_id"],
                            job_title=job["title"],
                            total=total,
                            invited=invited,
                            below_threshold=below,
                            skipped=skipped,
                            failed=failed,
                            mode="auto",
                        )
                        logger.info(
                            "Background poll for %s: %d checked, %d invited, %d below, %d skipped, %d failed",
                            job["title"], total, invited, below, skipped, failed,
                        )
                except Exception as e:
                    logger.error("Background poll error for job %s: %s", job["job_id"], e)
        except Exception as e:
            logger.error("Background poll error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    db.init_db()
    
    # Get database engine for health checks
    engine = get_database_engine()
    
    # Start in-process workers unless disabled
    if _workers_enabled():
        from app.screening.worker import start_workers
        start_workers()
        logger.info("In-process workers started (screening, outbox)")
    else:
        logger.info("In-process workers disabled (INTERVIEWIQ_DISABLE_WORKERS=1)")
    
    # Start background Gmail poll for remote mode
    global _bg_poll_task
    _bg_poll_task = None
    if _workers_enabled() and _is_remote_mode():
        _bg_poll_task = asyncio.create_task(_background_poll())
        logger.info("Background Gmail polling started")
    
    yield
    
    # Cleanup
    if _bg_poll_task:
        _bg_poll_task.cancel()
        try:
            await _bg_poll_task
        except asyncio.CancelledError:
            pass
    logger.info("Application shutting down")


app = FastAPI(
    title="InterviewIQ API",
    version="1.0.0",
    lifespan=lifespan,
)


def _allowed_origins() -> list[str]:
    """CORS origins come from the FRONTEND_ORIGIN env var (comma separated).
    Defaults to local Next.js dev so a fresh checkout works, but production
    deployments must pin this to their real frontend origin.
    """
    raw = os.environ.get(
        "FRONTEND_ORIGIN",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(scoring.router, prefix="/api/scoring", tags=["scoring"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(integrity.router, prefix="/api", tags=["integrity"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(candidate_flow.router, prefix="/api", tags=["candidate-flow"])
app.include_router(email_intake.router, prefix="/api/email-intake", tags=["email-intake"])
app.include_router(public_apply.router, prefix="/api/public", tags=["public-apply"])
app.include_router(scheduling.router, prefix="/api/scheduling", tags=["scheduling"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(linkedin.router, prefix="/api/integrations/linkedin", tags=["linkedin-integration"])
app.include_router(questions.router, prefix="/api/questions", tags=["questions"])
app.include_router(live.router, prefix="/api", tags=["live-interview"])
app.include_router(media.router, prefix="/api/media", tags=["media"])


# Uploaded interview recordings (data/uploads/<session_id>/<file>) are served
# back through signed URLs so only authenticated recruiters can load them,
# even when the central server runs on a different machine.
@app.get("/media/{path:path}")
def media_file(request: Request, path: str):
    """Signed media route: /media/{path}?sig=...&exp=..."""
    sig = request.query_params.get("sig", "")
    exp = request.query_params.get("exp", "")
    return media.serve_media_file(path, sig=sig, exp=exp)


@app.get("/health")
def health_check():
    """Health check endpoint with diagnostic information.
    
    Returns:
        JSON with status, database connectivity, storage backend, worker mode,
        and deployment configuration. Does not expose secrets.
    """
    from app.core.database import get_database_engine
    from app.core.storage import get_storage
    
    # Check database connectivity
    db_status = "unknown"
    db_type = "unknown"
    try:
        engine = get_database_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        db_status = "connected"
        db_type = "postgresql" if engine.is_postgresql else "sqlite"
    except Exception as e:
        db_status = f"error: {type(e).__name__}"
        logger.warning("Health check: database error: %s", e)
    
    # Get storage backend info
    storage = get_storage()
    storage_type = type(storage).__name__
    if storage_type == "S3FileStorage":
        storage_info = {"backend": "s3", "bucket": storage.bucket}
    else:
        storage_info = {"backend": "local", "path": str(storage.base_dir)}
    
    # Worker status
    workers_disabled = os.environ.get("INTERVIEWIQ_DISABLE_WORKERS", "") == "1"
    worker_mode = "disabled" if workers_disabled else "in_process"
    
    # Deployment mode
    deploy_mode = "remote" if _is_remote_mode() else "local"
    
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": {
            "status": db_status,
            "type": db_type,
        },
        "storage": storage_info,
        "workers": worker_mode,
        "deploy_mode": deploy_mode,
    }


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    # DEPLOY_MODE=remote is set on the hosted central instance (Render/Railway):
    # bind all interfaces and honor the platform's PORT env var. Without it the
    # default stays loopback-only, exactly as the Electron sidecar expects.
    is_remote = os.environ.get("DEPLOY_MODE") == "remote"
    host = "0.0.0.0" if is_remote else "127.0.0.1"
    port = args.port or int(os.environ.get("PORT", 8000))

    uvicorn.run(app, host=host, port=port, log_level="warning")
