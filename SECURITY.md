# SECURITY.md

Security model of InterviewIQ (academic project). This documents what is protected,
what is intentionally open, and the known limitations before real-world deployment.

## Threat model / assumptions

- The primary deployment is a **local sidecar** (Electron spawns FastAPI on
  `127.0.0.1:<random-port>`) used by a single recruiter on their own machine.
- Optional **central-server** mode (`DEPLOY_MODE=remote`) hosts the API for multiple
  recruiters; candidly, this setup is meant for a classroom/demo setting, not public
  production traffic.
- We treat the network as hostile only in central mode; on the loopback sidecar we
  assume an already-compromised machine can read process memory anyway.

## What is protected (recruiter side)

- **Recruiter authentication** — PBKDF2-salted passwords (`app/core/auth.py`) and
  signed bearer tokens (`app/core/tokens.py`). Tokens are HMAC-SHA256 over a
  `{sub, iat, exp}` payload (7-day TTL), NOT JWT — deliberate stdlib-only choice.
  Signing secret is generated once and persisted as `auth_secret` in
  `data/settings.json` so tokens survive restarts.
- **Authentication is enforced at the router level** via
  `Depends(get_current_recruiter)` (`api/deps.py`):
  - `auth/me` — profile
  - `jobs/*` (recruiter CRUD)
  - `candidates/*`, `applications/*`, `sessions/*` (recruiter views)
  - `scheduling/*` — list / allocate / available
  - `reports/*`, `integrity/flags` + `bias/flags` (GET)
  - `settings/*`, `email-intake` check + poll-logs
  - `media/sign` (issues signed media URLs)
  Missing/invalid tokens → `401`.
- **Ownership scoping** — root is `job_postings.created_by`. Jobs, candidates,
  applications, scheduled interviews, reports and integrity flags are filtered by the
  authenticated recruiter. Cross-recruiter reads/writes → `403`. Ownership helpers
  live in `app/core/db.py` (`get_owned_*`, `job_owned_by`, `_owned_session_ids`).
- **Signed media** — the old open `StaticFiles("/media")` mount is gone. Files are
  served by `serve_media_file()` (`api/routes/media.py`) only when the URL carries a
  valid, unexpired HMAC signature issued by `GET /api/media/sign` (auth required).
  Paths are resolved inside the media roots (`MEDIA_DIR` for recordings, `RESUMES_DIR`
  for stored resumes; traversal → 404) and signatures are verified over the exact served
  path. Stored absolute resume paths are normalized to relative media paths both on
  write and read (`to_relative_media_path`).
- **Interview access tokens** — the candidate invite code never enters consent or
  session-start as a bearer secret. `POST /candidate/validate-code` exchanges a valid,
  unconsumed invite code for a short-lived (4 h TTL) purpose-scoped HMAC token
  (`typ: "interview"`) minted by `create_interview_token()`. `consent` and
  `start-session` re-derive the candidate/job identity server-side from that token
  (`_identity_from_token` → 401 on missing/expired/reused tokens) and ignore any
  client-supplied candidate/job ids. Invites are consume-once per candidate/job; a
  second `start-session` with the same invite → 409. Resend/revoke clears superseded
  codes and re-queues a fresh email, so stale or consumed codes cannot be replayed.
- **Rate limiting** — in-memory fixed window (10 req / 60 s per client IP) with
  **per-endpoint buckets** (`rate_limited("auth")`, `"invite_code"`, `"public_apply"`)
  so a burst on login cannot exhaust the public-apply budget and vice-versa. See
  `api/rate_limit.py`. A burst on any single endpoint → `429`.
- **Token type confusion defense** — `verify_token` rejects any token whose payload
  carries an explicit `typ` other than `"recruiter"`, so the short-lived `interview`
  tokens minted for the candidate flow can never authenticate recruiter routes
  (`app/core/tokens.py`).
- **Consistent credential errors** — unknown username and wrong password return the
  same generic `"Invalid username or password."`, closing the login username
  enumeration oracle (`app/core/auth.py`).
- **Path neutralization on hostile inputs** — session ids and file names are
  sanitized against a strict character whitelist before any `os.path.join`, so an
  upload traversal (e.g. `session_id = "../evil"`) can never escape the uploads root
  (`api/routes/sessions.py`).
- **Media ownership, not just access** — `sign_media` verifies the requesting
  recruiter actually owns the job/session the media belongs to before issuing a
  signature; flat resumes are matched through their owning application. Unmatched →
  `403` (`api/routes/media.py`).
- **One candidate per (email, job)** — enforced by a UNIQUE index plus an upsert that
  adopts an existing candidate instead of erroring on the concurrent intake race
  (`app/core/db.py` `idx_candidates_email_job`, `save_candidate`);
  `app/screening/service.py` has a matching IntegrityError fallback.
- **Screening eligibility re-checked at the door** — `validate-code` / `start-session`
  consult the candidate's *latest* screening decision; un-screened or
  below-threshold applicants are refused (invalid response / `409`), not admitted
  (`api/routes/candidate_flow.py`).
- **Idempotent calendar booking** — `allocate_next_slot` returns the existing booking
  for an already-scheduled candidate and only persists the DB row after the calendar
  event is created, so retries cannot double-book; free/busy failures surface as
  errors instead of 500s, and `working_days` / `excluded_dates` bound when slots are
  offered (`app/engine/scheduling.py`).

## What is intentionally public (candidate side)

The candidate experience cannot require recruiter credentials. Instead it relies on a
**chained secret handoff**: invite code → (one-time, rate-limited) interview token →
signed session. Consent and session-start trust only the token and never client-supplied
candidate or job ids:

- `GET /api/public/jobs/{job_id}` and `POST /api/public/apply/{job_id}` — the apply
  portal. The GET leaks **only** public job fields (title, description, skills, level,
  department); the POST is rate-limited, rejects duplicates (409), and queues async
  screening.
- `/api/candidate/*` — validate-code (code → `interview_token` + `expires_at`),
  consent + start-session (require the token, 401 otherwise), submit-answer,
  complete-session, session upload.
- `POST /api/sessions/{id}/upload` — recordings are uploaded **unauthenticated** on the
  candidate path; playback is gated behind the signed-media check described above.
- `POST /api/integrity/flags` and the integrity/live-frame **WebSocket** — the desktop
  candidate client posts flags anonymously because there is no anonymous-identity
  channel available before a session starts.

These endpoints assume the chained handoff described above rather than an account. An
attacker who obtains an invite code can impersonate an applicant until the code is
consumed or superseded — the 4 h token TTL and consume-once semantics bound the window.
This is a documented design constraint for the academic scope, not a security guarantee.

## Known limitations (read before deploying publicly)

- **Cleartext credentials in `data/settings.json`** — Gmail/Calendar OAuth tokens and
  the `auth_secret` are stored in plaintext JSON (gitignored). Anyone with local file
  read access on a recruiter's machine can extract them. No OS-level keychain/DPAPI
  encryption is used.
- **SQLite `data/app.db` is unencrypted** — includes candidate PII (name, email,
  phone, resume text), interview recordings metadata, and integrity flags. Fine for an
  academic project; not for production PII.
- **No brute-force lockout / backoff** on login beyond the modest rate limit; no
  account lockout policy.
- **No token revocation or rotation** — a leaked bearer token is live until its 7-day
  expiry. `auth_secret` rotation invalidates all tokens only if it changes.
- **Rate limiting is in-memory and single-process** — one uvicorn worker per
  container; restarting clears counters; fine for the intended scale.
- **Transport security is external** — the app does not terminate TLS itself. Local
  sidecar mode uses HTTP on a loopback port; central mode must sit behind HTTPS
  (reverse proxy / platform TLS). Recommended: do not expose the API port directly.
- **Face check is not anti-spoof** — `app/candidate/face_recognition.py` does
  enrollment/verification and single-face detection, but has no liveness/anti-spoof
  classification. A photo printed on a screen can defeat it.
- **Frontend stores the bearer token in `localStorage`** (`interviewiq_token`) — an
  XSS on the frontend could exfiltrate it. Mitigations: keep the frontend dependency
  surface minimal, apply a CSP, and prefer httpOnly cookies in a hardened build.

## Recommended hardening before public use

1. Swap SQLite → Postgres (owned by the central server; one DB per tenant namespace).
2. Terminate TLS in front of the API and pin the public apply origin in `FRONTEND_ORIGIN`.
3. Encrypt `data/settings.json` (OS keychain or envelope-encrypted secret) and move
   secrets to a secrets manager; store OAuth tokens encrypted at rest.
4. Token rotation + a server-side revocation/capability list; short-lived tokens.
5. Redis (or equivalent) rate limiting with per-email+IP buckets and login backoff.
6. Add liveness/anti-spoof to the face verification stage.
7. Harden the frontend: strict CSP, avoid `eval`, review `dangerouslySetInnerHTML` usage.
8. Consider attribute-based access control beyond the single-owner model once
   multi-recruiter teams share jobs.

## Verification

- `tests/test_security_auth.py` — unauthenticated 401s on every recruiter route,
  cross-recruiter IDOR denial (403), signed-media serving/traversal, invite
  consume-once, and `start-session` rejecting missing/invalid interview tokens.
- `tests/test_screening_business_rules.py` — screening decision spectrum (hard gates vs
  weighted ATS), token-gated interview end-to-end, `screening_enabled` toggle,
  decision-aware shortlist, and cross-recruiter ownership scoping.
- `tests/test_core_auth.py`, `tests/test_api.py` — login/register/token paths.
- `tests/test_scheduling.py` — overlap avoidance, idempotent rebooking, calendar
  write/free-busy failure handling, `working_days` / `excluded_dates`.
- `tests/test_screening_service.py` — one candidate per (email, job) invariant.
- Full gates: `python -m pytest tests -q` (252 pass), `cd frontend && npx tsc --noEmit`,
  `npx vitest run` (25 pass), `npx next build` (static export), `cd electron && npm run build`.