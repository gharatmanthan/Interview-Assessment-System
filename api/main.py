"""
FastAPI application entry point.
Spawns as a child process from Electron, serves on a random port.
"""
import sys
import os
import asyncio
import argparse
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core import db
from api.routes import auth, jobs, candidates, sessions, scoring, reports, integrity, settings, devices, candidate_flow, email_intake

logger = logging.getLogger(__name__)

_bg_poll_task = None


async def _background_poll():
    """Periodically check Gmail for new applications (remote mode only)."""
    while True:
        await asyncio.sleep(600)  # every 10 minutes
        try:
            from app.core.settings_store import load_settings
            from app.engine.email_intake import check_for_new_applications
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
                    invited = sum(1 for r in results if r.get("status") == "invited")
                    below = sum(1 for r in results if r.get("status") == "below_threshold")
                    skipped = sum(1 for r in results if r.get("status") in ("skipped", "error"))
                    failed = sum(1 for r in results if r.get("status") == "invite_send_failed")
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
    db.init_db()
    global _bg_poll_task
    _bg_poll_task = asyncio.create_task(_background_poll())
    yield
    _bg_poll_task.cancel()
    try:
        await _bg_poll_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="InterviewIQ API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

# Uploaded interview recordings (data/uploads/<session_id>/<file>) are served
# back at /media/uploads/... so the recruiter's Reports page can play or
# download them even when the central server runs on a different machine.
MEDIA_DIR = Path(__file__).parent.parent / "data" / "uploads"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/health")
def health_check():
    return {"status": "ok"}


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
