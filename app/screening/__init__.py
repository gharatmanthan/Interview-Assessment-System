"""
Application screening pipeline (candidate-first, asynchronous).
Replaces the old inline threshold check in app/engine/application_processor.py.

Flow: Application -> ScreeningJob (queue) -> screen_application() ->
      ScreeningResult (idempotent) -> Candidate + InterviewInvite -> outbox.
"""
from app.screening.service import (
    create_application_and_queue,
    screen_application,
    run_screening_jobs,
)

MAX_SCREENING_ATTEMPTS = 3

__all__ = [
    "create_application_and_queue",
    "screen_application",
    "run_screening_jobs",
    "MAX_SCREENING_ATTEMPTS",
]