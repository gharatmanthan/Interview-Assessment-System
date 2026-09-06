"""
Independent background worker process for InterviewIQ.

This module runs as a standalone process (python -m app.workers) and handles:
1. Screening queue - processes pending screening jobs
2. Notification outbox - sends pending emails via Gmail
3. Gmail label polling - checks for new applications every 10 minutes (remote mode only)

This process is designed to run independently from the FastAPI web service
to ensure workers survive web process restarts and can scale separately.

Usage:
    python -m app.workers

Environment:
    INTERVIEWIQ_DISABLE_WORKERS=1 - Disable all workers (for testing)
    DEPLOY_MODE=remote - Enable Gmail polling (only in remote mode)
"""
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Polling intervals
SCREENING_POLL_SECONDS = 5
OUTBOX_POLL_SECONDS = 5
GMAIL_POLL_SECONDS = 600  # 10 minutes

# Global shutdown flag
_shutdown = False
_worker_threads: list[threading.Thread] = []


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    _shutdown = True


def workers_enabled() -> bool:
    """Check if workers should run."""
    return os.environ.get("INTERVIEWIQ_DISABLE_WORKERS", "") != "1"


def is_remote_mode() -> bool:
    """Check if running in remote/deployed mode."""
    return os.environ.get("DEPLOY_MODE") == "remote"


def _screening_loop():
    """Process screening jobs from the queue."""
    from app.screening.service import run_screening_jobs
    
    while not _shutdown:
        try:
            run_screening_jobs(limit=5)
        except Exception as exc:
            logger.exception("screening worker error: %s", exc)
        if _shutdown:
            break
        time.sleep(SCREENING_POLL_SECONDS)


def _outbox_loop():
    """Process notification outbox (emails)."""
    from app.screening.email_worker import send_pending_notifications
    from app.screening.routing import route_pending_assignments
    
    while not _shutdown:
        try:
            send_pending_notifications(limit=20)
            # Also handle mode assignment for AUTO cohorts
            route_pending_assignments(limit=20)
        except Exception as exc:
            logger.exception("outbox worker error: %s", exc)
        if _shutdown:
            break
        time.sleep(OUTBOX_POLL_SECONDS)


def _gmail_poll_loop():
    """Poll Gmail for new applications (remote mode only)."""
    from app.core.settings_store import load_settings
    from app.engine.email_intake import (
        check_for_new_applications,
        summarize_poll_results,
    )
    from app.core import db
    
    if not is_remote_mode():
        logger.info("Gmail polling disabled (not in remote mode)")
        return
    
    while not _shutdown:
        try:
            settings = load_settings()
            if not settings.get("gmail_connected"):
                logger.debug("Gmail not connected, skipping poll")
            else:
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
                                "Gmail poll for %s: %d checked, %d invited, %d below, %d skipped, %d failed",
                                job["title"], total, invited, below, skipped, failed,
                            )
                    except Exception as e:
                        logger.error("Gmail poll error for job %s: %s", job["job_id"], e)
        except Exception as e:
            logger.error("Gmail poll loop error: %s", e)
        
        if _shutdown:
            break
        time.sleep(GMAIL_POLL_SECONDS)


def start_workers() -> list[threading.Thread]:
    """Start all worker threads."""
    global _worker_threads
    
    if not workers_enabled():
        logger.info("Workers disabled via INTERVIEWIQ_DISABLE_WORKERS=1")
        return []
    
    logger.info("Starting background workers...")
    
    targets = [
        ("screening-worker", _screening_loop),
        ("outbox-worker", _outbox_loop),
        ("gmail-poll-worker", _gmail_poll_loop),
    ]
    
    _worker_threads = []
    for name, target in targets:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        _worker_threads.append(t)
        logger.info("Started %s", name)
    
    return _worker_threads


def wait_for_shutdown():
    """Wait for shutdown signal and clean up."""
    global _shutdown
    
    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    logger.info("Workers running. Press Ctrl+C to stop.")
    
    # Keep main thread alive
    while not _shutdown:
        time.sleep(1)
    
    logger.info("Shutdown initiated, waiting for workers to finish...")
    
    # Wait for worker threads to finish (with timeout)
    for t in _worker_threads:
        t.join(timeout=10)
        if t.is_alive():
            logger.warning("Worker %s did not shut down gracefully", t.name)
    
    logger.info("All workers stopped")


def main():
    """Main entry point for the worker process."""
    logger.info("=" * 50)
    logger.info("InterviewIQ Background Workers Starting")
    logger.info("=" * 50)
    logger.info("Deploy mode: %s", "remote" if is_remote_mode() else "local")
    logger.info("Workers enabled: %s", workers_enabled())
    
    if not workers_enabled():
        logger.info("Workers disabled, exiting")
        return 0
    
    try:
        start_workers()
        wait_for_shutdown()
        return 0
    except Exception as e:
        logger.exception("Fatal error in worker process: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())