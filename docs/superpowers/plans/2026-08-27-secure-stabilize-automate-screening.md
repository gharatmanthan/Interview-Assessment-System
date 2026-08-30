# Secure, Stabilize & Automate Screening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a candidate-first Application lifecycle with asynchronous, idempotent ATS screening, an email outbox worker, secure invites, and JWT-style auth + ownership checks — without breaking the existing interview workflow.

**Architecture:** Raw `sqlite3` persistence (app/core/db.py) + FastAPI router layer + `app/screening/*` service package + lightweight daemon-thread workers for screening jobs and email outbox. No Redis/Celery (local FYA). Tokens are stdlib-HMAC signed (no new dependency).

**Tech Stack:** Python 3.12, FastAPI, sqlite3 (stdlib), pydantic, Next.js 14 frontend.

**Spec:** User "MASTER PROMPT" (audit.md is this plan); key section = automated application screening + outbox + security.

## Global Constraints
- Storage stays raw sqlite3; schema created idempotently in `init_db()` + `PRAGMA table_info` migrations.
- No new third-party Python dependencies. HMAC token signing with stdlib only.
- Screening must never call Gmail directly; all email goes through `notification_outbox` + email worker.
- Screening decisions must be deterministic + explainable (decision, decision_reason, scoring_method, matcher_method persisted).
- HTTP semantics: apply endpoint returns 202 (store-first), auth failures 401, ownership failures 403, duplicates 409, validation 422, not found 404.
- Frontend `npm run build` + `npx tsc --noEmit` must pass; `pytest -q` must pass.
- Preserve legacy interview flow (candidate/consent/start/submit/complete, integrity, scoring, scheduling) and legacy `app/core`+`app/engine` contracts where possible. Do not import PySide6 in new code.

---

## Stage 1 — Application-first domain model
**Files:** `app/core/models.py`, `app/core/db.py`, `api/schemas.py`.

New dataclasses in `app/core/models.py`: `Application`, `ScreeningJob`, `ScreeningResult`,
`NotificationOutbox`, `InterviewInvite`. Extend `JobPosting` with screening config:
`screening_enabled: bool = True`, `auto_invite_enabled: bool = True`,
`minimum_experience_years: Optional[float] = None`, `required_education: str = ""`,
`screening_weights: dict = field(default_factory=lambda: {"skills":40,"experience":20,"semantic":20,"education":10,"keyword":10})`,
`created_by: str = "recruiter"`. Extend `Candidate` with `application_id: Optional[str] = None`.

New tables + migration (`created_by` on job_postings) + helper functions in `db.py`:
`create_application`, `get_application`, `get_applications_for_job`,
`get_application_by_email_job`, `update_application`, `create_screening_job`,
`get_due_screening_jobs`, `claim_screening_job`, `complete_screening_job`,
`fail_screening_job`, `save_screening_result`, `get_screening_result`,
`get_screening_result_for_application`, `enqueue_notification`,
`get_pending_notifications`, `mark_notification_sent`, `bump_notification_attempt`,
`create_interview_invite`, `get_interview_invite_by_token`,
`consume_interview_invite`, `get_interview_invites_for_candidate`,
`get_owned_jobs`, `get_owned_candidates`, `get_owned_sessions`, `job_owned_by` helpers.
Enable `PRAGMA foreign_keys` + `PRAGMA journal_mode=WAL` in `get_connection`.

UNIQUE constraints: `screening_jobs(application_id)`, `screening_results(application_id)`,
`notification_outbox(application_id, notification_type, recipient)`,
`interview_invites(token)`, index `applications(job_id)` + `applications(email, job_id)`.

## Stage 2 — Screening service (`app/screening/`)
Files: `app/screening/__init__.py`, `app/screening/scoring.py`, `app/screening/rules.py`,
`app/screening/service.py`.

- `scoring.py`: `component_scores(resume_data, job, match_result) -> dict` computing
  skills/experience/semantic/education/keyword report scoring with job `screening_weights`.
  Any unavailable criterion → `None` + `reason`.
- `rules.py`: `eval_hard_requirements(resume_data, job) -> dict{passed, failures, checks}`;
  `decide(ats, hard_passed, threshold, job) -> (decision, reason)` — hard fail → rejected,
  ats ≥ threshold → passed, else rejected.
- `service.py`: `screen_application(application_id) -> dict` (idempotent via job state +
  unique result). On pass: `ensure_candidate` (dedupe by email+job+application),
  `ensure_interview_invite` (expiry=30d, token stored), `enqueue_notifications`
  (hr_shortlist + interview_invite when auto_invite_enabled), best-effort calendar
  auto-booking (calendar disconnect does not fail the flow).

## Stage 3 — Workers
Files: `app/screening/worker.py`, `app/screening/email_worker.py`.

- `worker.py`: `_process_screening_job(job_id)`; `run_screening_jobs(limit)` claims due
  queued jobs, screens, retries up to MAX_ATTEMPTS (3) with attempts + last_error.
- `email_worker.py`: `send_pending_notifications(max_attempts=3)` drains outbox using the
  existing `get_gmail_service()`; sends `hr_shortlist` (new `compose_hr_shortlist_email`)
  and `interview_invite` (`compose_invite_email`). Marks `sent`; failed → attempts++,
  status `failed` at max. No Gmail → messages stay `pending`.
- `app/main.py`-equivalent startup hook: `start_workers()` daemon threads started in
  `api/main.py` lifespan.

## Stage 4 — Public apply + email intake
Files: `api/routes/public_apply.py`, `api/routes/email_intake.py`, `app/engine/application_processor.py` -> replaced by `app/screening/service.create_application_and_queue()`.

- Public apply: GET job (active-only) + POST: validate (active job, file type/size, email),
  store resume + application, queue screening job, return **202** with
  `{application_id, status:"received"}`. Duplicate email+job → 409. Remove in-memory-only
  rate limit (keep DB unique constraint + add rate_limit dependency).
- Email intake `check_for_new_applications`: for each message → save resume → create
  application (idempotent by message_id via `processed_emails`) → queue screening job →
  return statuses `queued | error | skipped`. No Gmail send inside pipeline.

## Stage 5 — Auth, ownership, CORS, media, rate limit
Files: `app/core/tokens.py` (new, stdlib HMAC), `api/deps.py` (new), `api/routes/auth.py`,
`api/main.py`, `api/routes/jobs.py`, `api/routes/candidates.py`, `api/routes/reports.py`,
`api/routes/sessions.py`, `api/routes/settings.py`, `api/routes/scheduling.py`,
`api/routes/integrity.py`, `api/media.py` (signed media serving).

- Tokens: `create_token(username, ttl)`, `verify_token`; login returns `token`; add `/auth/me`.
- `get_current_recruiter` dependency; applied to recruiter routers. Ownership: job
  `created_by`; scope lists + guard object endpoints (403 on non-owner). Candidate-side +
  public endpoints remain open (documented limitation).
- CORS: `FRONTEND_ORIGIN` env (default localhost:3000, plus 127.0.0.1:3000 in dev).
- Media: replace open `StaticFiles` mount with signed-URL handler `GET /media/{path}` validating `?sig=&exp=`; add `issue_media_token(path)`.
- Rate limiting: `api/rate_limit.py` in-memory limiter on login, public apply, invite validate.

## Stage 6 — Frontend
Files: `frontend/lib/api.ts`, `frontend/lib/types.ts`, `frontend/app/login/page.tsx`,
`frontend/app/applications/page.tsx` (new), `frontend/components/sidebar.tsx`,
`frontend/app/apply/[jobId]/page.tsx` (phone field + 202 handling), scheduler media callers.

- Store auth token in localStorage (`interviewiq_token`); attach `Authorization: Bearer`.
- New `/applications` page: job selector + table of applications with ATS breakdown,
  decision, invite/email status. Nav link.
- `npx tsc --noEmit` and `npm run build` must pass.

## Stage 7 — Tests
New: `tests/test_screening_service.py`, `tests/test_screening_worker.py`,
`tests/test_notification_outbox.py`, `tests/test_auth.py`, `tests/test_authorization.py`,
`tests/test_invites.py`, `tests/test_media.py`.
Updated: `tests/conftest.py` (authed `client` fixture), `tests/test_public_apply.py`,
`tests/test_email_intake.py`, `tests/test_scheduling.py`, `tests/test_api.py`,
`tests/test_ui_flow.py`, `tests/test_candidate_entry.py`, `tests/test_core_auth.py`.

## Stage 8 — Docs
`.env.example`, `README.md`, `SECURITY.md`. Honest limitation statements.

---

## Self-review
- Spec coverage: application entity ✓(S1), screening config ✓(S1), multi-component ATS ✓(S2),
  hard vs soft ✓(S2), screening service ✓(S2), async ✓(S3), queue ✓(S1/S3), idempotency ✓(S1/S3),
  result entity ✓(S1), auto candidate creation ✓(S2), auto invite ✓(S2/S5), outbox ✓(S1/S3),
  retry ✓(S3), Gmail not SPOF ✓(S3/S4), HR email ✓(S3), dashboard ✓(S6), applicant UX ✓(S4),
  public API ✓(S4), duplicates ✓(S4), decision engine ✓(S2), matcher reuse ✓(S2), LLM validation
  (existing matcher structured+fallback) ✓(existing), auth ✓(S5), authorization ✓(S5),
  invite security ✓(S5/S2), media ✓(S5), CORS ✓(S5), secrets/env ✓(S8), pydantic ✓(S1/S4),
  errors/status codes ✓(multi), state machine ✓(S1 transitions), DB design ✓(S1), frontend ✓(S6),
  legacy PySide6 — isolated by convention (no imports; app/ won't be touched); tests ✓(S7),
  evaluation/limitations ✓(S8).
- Deliberately out of scope (honest): per-endpoint candidate-session auth on candidate
  upload/live-frame endpoints; encryption-at-rest of settings.json; biometric anti-spoof;
  production queue/infra; real training data.