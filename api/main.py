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
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from api.routes import (
    auth, jobs, candidates, sessions, scoring, reports, integrity, settings,
    devices, candidate_flow, email_intake, public_apply, scheduling,
    applications, media,
)

logger = logging.getLogger(__name__)

_bg_poll_task = None


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
    db.init_db()
    from app.screening.worker import start_workers, workers_enabled
    # Start the screening + email-outbox workers (daemon threads) unless the
    # operator disabled them (tests do) — otherwise they'd race our callers.
    start_workers()
    global _bg_poll_task
    _bg_poll_task = None
    if workers_enabled():
        _bg_poll_task = asyncio.create_task(_background_poll())
    yield
    if _bg_poll_task:
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
app.include_router(media.router, prefix="/api/media", tags=["media"])


# Uploaded interview recordings (data/uploads/<session_id>/<file>) are served
# back through signed URLs so only authenticated recruiters can load them,
# even when the central server runs on a different machine.
MEDIA_DIR = Path(__file__).parent.parent / "data" / "uploads"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/media/{path:path}")
def media_file(request: Request, path: str):
    """Signed media route: /media/{path}?sig=...&exp=..."""
    sig = request.query_params.get("sig", "")
    exp = request.query_params.get("exp", "")
    return media.serve_media_file(path, sig=sig, exp=exp)


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
