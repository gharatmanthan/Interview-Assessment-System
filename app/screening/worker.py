"""
Background workers for the screening pipeline (daemon threads, no Celery).

  * screening loop  : claims queued screening_jobs and runs screen_application
  * outbox loop     : drains notification_outbox via the Gmail email worker

Both are best-effort daemon threads started from the FastAPI lifespan.
Idempotency and retry caps live in the database layer, so a crash anywhere
is safely recoverable on the next poll.
"""
import logging
import os
import threading
import time

from app.screening.email_worker import send_pending_notifications
from app.screening.service import run_screening_jobs

logger = logging.getLogger(__name__)

SCREENING_POLL_SECONDS = 5
OUTBOX_POLL_SECONDS = 5

_worker_threads: list[threading.Thread] = []


def workers_enabled() -> bool:
    """Background workers run unless the operator explicitly disables them.
    Tests set INTERVIEWIQ_DISABLE_WORKERS so they can drive the pipeline
    deterministically instead of racing daemon threads."""
    return os.environ.get("INTERVIEWIQ_DISABLE_WORKERS", "") != "1"


def _screening_loop():
    while True:
        try:
            run_screening_jobs(limit=5)
        except Exception as exc:  # never let a bad job kill the loop
            logger.exception("screening worker crashed cycle: %s", exc)
        time.sleep(SCREENING_POLL_SECONDS)


def _outbox_loop():
    while True:
        try:
            send_pending_notifications(limit=20)
        except Exception as exc:
            logger.exception("outbox worker crashed cycle: %s", exc)
        time.sleep(OUTBOX_POLL_SECONDS)


def start_workers() -> list[threading.Thread]:
    """Start (or reuse) the daemon workers. Idempotent. No-op when workers are
    disabled via INTERVIEWIQ_DISABLE_WORKERS."""
    global _worker_threads
    if not workers_enabled():
        return []
    if all(t.is_alive() for t in _worker_threads):
        return _worker_threads

    targets = [("screening-worker", _screening_loop), ("outbox-worker", _outbox_loop)]
    _worker_threads = []
    for name, target in targets:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        _worker_threads.append(t)
        logger.info("started %s", name)
    return _worker_threads