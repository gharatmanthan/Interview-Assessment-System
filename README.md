# InterviewIQ — AI-Powered Interview Assessment System

Academic project (Computer Engineering, group project) exploring **explainability + bias auditing**
combined with **integrity / AI-assisted-answer detection** for automated interview assessment tools.

## Current status: v0.7 — async application screening, recruiter auth & ownership

The app has migrated from a monolithic PySide6 desktop UI to a three-tier architecture:
**Electron shell → Next.js frontend → FastAPI backend** (Python engine unchanged underneath).
Both recruiter and candidate use the same desktop app, which can run against a
**local sidecar API** (single machine) or a **central deployed server** (remote interviews).
See `docs/DEPLOYMENT.md` for hosting and installer-build instructions.

What works right now:

- **Recruiter flow** — login/register (salted-hash auth), job postings, candidate management
  with invite codes and resume upload/parsing
- **Candidate flow** — invite-code entry, consent screen, preflight camera/mic check,
  face enrollment & verification (OpenCV), guided interview session
- **Interview session** — video/audio capture, Whisper (faster-whisper) transcription,
  answer scoring against rubrics, heuristic explanations per score
- **AI-based competency evaluation** — resume parsing, JD matching (LLM semantic
  matching with keyword-overlap fallback), RAG-style rubric retrieval over a
  hand-authored knowledge base (model2vec embeddings → TF-IDF fallback), LLM-based
  scoring/explanation/fairness-audit when `GROQ_API_KEY` is configured (heuristic
  fallback with logged reasons otherwise), and a trained RandomForest scorer
  surfaced as a third, optional score signal
- **Email-to-invite pipeline** — recruiters connect a Gmail account once; the system
  watches a configured Gmail label for job applications, auto-screens resumes through
  the existing resume parser + JD matcher pipeline, and invites qualified candidates
  (above a configurable threshold) via email with an invite code. Below-threshold
   candidates are recorded for transparency. Supports both manual trigger and automatic
   polling (remote mode). Gmail OAuth tokens stored in `data/settings.json`, never in
   SQLite — see `docs/DEPLOYMENT.md` for Google Cloud setup
- **Automatic interview scheduling** — when a candidate passes the screening threshold,
  the system queries the recruiter's **Google Calendar** free/busy, picks the next free
  slot (configured duration + buffer, within recruiter working hours, never overlapping
  already-booked interviews), books it (persisted to the DB **and** written back to the
  calendar so future auto-bookings avoid it), and includes the interview **date and time**
  in the auto-invite email. Recruiters configure duration/buffer/working hours in
  Settings and review all bookings on the new **Scheduled Interviews** page. No calendar
  connected → auto-scheduling is skipped gracefully and the invite email is sent without
  a date
- **Public "Apply Now" portal** — the primary application intake path. Each job posting
  gets a shareable application link (`/apply?jobId={jobId}`). Candidates apply through a
  public form that feeds the same async screening pipeline as the Gmail path
  (`app/screening/service.screen_application` → resume parser + JD matcher + hard
  requirements + weighted ATS threshold → candidate + invite outbox). Portal submissions
  are shown to recruiters with an **Apply Portal** source badge. The public page **never**
  reveals screening scores, pass/fail, or invite codes — candidates always see the generic
  "Thanks for applying, we'll be in touch by email if shortlisted" message. Gmail polling
  remains as a secondary intake path. Public endpoints are rate-limited and never leak
  internal job fields
- **Async screening pipeline** — `POST /api/public/apply/{job_id}` returns `202` plus an
  `application_id`; a background worker runs resume parsing → JD matching → threshold
  screening → candidate creation + invite code + outbox notification. Application status
  (queued → screening → completed/failed) is tracked per application and visible on the
  **Applications** page, together with a **per-job funnel** (applications, pending
  screening, shortlisted, rejected, manual review, invites sent, interviews completed,
  email failures), a **Re-screen** action that re-runs screening against the current job
  settings, and a per-application **audit trail** (`application_events`) covering every
  decision. Each screening result also persists the threshold that was actually applied
  (`threshold_used`), so which bar an applicant cleared is always auditable
- **Recruiter auth & ownership** — salted-hash login + HMAC bearer tokens. Every recruiter
  route is authenticated; jobs, candidates, applications, scheduled interviews, reports
  and integrity flags are scoped to the owning recruiter (cross-recruiter reads return
  403). Interview recordings are served only through short-lived HMAC-signed media URLs
  (`GET /api/media/sign`) instead of an open `/media` mount
- **Interview access security** — the invite code now exchanges for a short-lived,
  HMAC-signed **interview token** (4 h TTL, purpose-scoped so recruiter bearer tokens
  can't be reused for candidate sessions). Consent and session start derive the
  candidate identity server-side from the token; consuming the invite is one-time
  (reuse → 409), and the code is validated on a first-come basis per candidate/job.
  Recruiters revoking/resending an invite clears old codes and invites, so consumed or
  superseded codes can't be replayed
- **Live monitor** — recruiters watch in-progress interviews with live frames
- **Integrity checks** — port scan, suspicious-process scan, external device monitoring,
  single-face verification; scans run locally inside Electron so they work in both
  modes, flags land in the shared Integrity Log
- **Recordings** — captured locally via MediaRecorder, uploaded to the backend and
  played back from the recruiter's Reports page
- **Reports** — dashboard stats, session scores/explanations, PDF export (fpdf2), CSV export
- **Bias audit** — counterfactual fairness checks producing fairness flags
- **First-run setup** — one-time "Connect to Interview Server" screen when a fresh
  install is set to remote mode without a server address (skipped entirely when the
  URL is baked into the installer); changeable later from Settings → Connection

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Electron shell (electron/main.ts)                       │
│  • local mode: picks a free port, spawns FastAPI,       │
│    polls /health until ready                            │
│  • remote mode: no spawn; all traffic goes to the       │
│    configured central server URL                        │
│  • native port/process integrity scan (integrity.ts)    │
│  • loads frontend/out (prod) or localhost:3000 (dev)    │
│  • kills the Python process on quit                     │
└───────────────┬─────────────────────────────────────────┘
                │ HTTP ── 127.0.0.1:<random port> (local)
                │      └─ https://<central-server> (remote)
┌───────────────▼─────────────────────────────────────────┐
│ Next.js 14 frontend (frontend/) — static export         │
│  React 18 + Tailwind CSS + Radix UI (shadcn-style)      │
└───────────────┬─────────────────────────────────────────┘
                │ fetch /api/*
┌───────────────▼─────────────────────────────────────────┐
│ FastAPI backend (api/)                                  │
│  routes: auth, jobs, candidates, sessions, scoring,     │
│          reports, integrity, settings, devices,         │
│          candidate-flow, email-intake, public-apply,     │
│          scheduling                                      │
│  media: signed /media/uploads/** (interview recordings)│
│  background: Gmail poller (10 min, remote mode),       │
│              async screening + notification-outbox     │
└───────────────┬─────────────────────────────────────────┘
                │ imports
┌───────────────▼─────────────────────────────────────────┐
│ Core engine (app/)                                      │
│  core/       SQLite db, models, auth, question bank     │
│  candidate/  capture, face recognition, integrity       │
│  engine/     Whisper STT, resume parser, JD matcher,    │
│              RAG rubrics, scoring, explainability,      │
│              fairness, LLM client, email intake         │
│  reports/    analytics, PDF export                      │
└───────────────┬─────────────────────────────────────────┘
                │ Gmail API (OAuth2)
┌───────────────▼─────────────────────────────────────────┐
│ Gmail API (googleapis.com)                              │
│  • gmail.readonly  — scan application emails            │
│  • gmail.send      — send invite emails                 │
│  • gmail.labels    — mark processed messages            │
│  OAuth tokens stored in data/settings.json (gitignored) │
└─────────────────────────────────────────────────────────┘
```

## Project structure

```
interview-assessment-system/
├── api/                     # FastAPI app
│   ├── main.py              # Entry point; loopback sidecar or 0.0.0.0 (DEPLOY_MODE=remote)
│   ├── schemas.py           # Pydantic request/response models
│   └── routes/              # One router per feature area
├── app/
│   ├── core/
│   │   ├── db.py            # SQLite persistence (data/app.db)
│   │   ├── models.py        # Shared data shapes (see docs/INTERFACES.md)
│   │   ├── auth.py          # Recruiter register/verify (salted hashes)
│   │   ├── question_bank.py # Interview questions
│   │   └── settings_store.py# App settings incl. backend_mode, remote_api_url, Gmail tokens
│   ├── candidate/
│   │   ├── capture.py       # Video/audio recording (MediaCapture)
│   │   ├── face_recognition.py # Face enroll / verify / single-face check
│   │   └── integrity.py     # Port scan, process scan, device monitor
│   ├── engine/
│   │   ├── stt.py               # faster-whisper transcription
│   │   ├── resume_parser.py     # PDF/DOCX resume parsing (LLM or regex heuristic)
│   │   ├── jd_matcher.py        # LLM semantic JD matching, keyword-overlap fallback
│   │   ├── email_intake.py      # Gmail API integration, resume screening, auto-invite
│   │   ├── application_processor.py # Legacy sync screening path (kept for reference; the async
│   │   │                            #   pipeline in app/screening/ is used by both intake paths)
│   │   ├── scheduling.py        # Google Calendar OAuth + free-slot auto-booking
│   │   ├── rag.py               # Rubric retrieval: embedding similarity + static fallback
│   │   ├── rubric_kb.py         # Hand-authored rubric knowledge base (~50 snippets)
│   │   ├── embeddings.py        # model2vec → sentence-transformers → TF-IDF chain
│   │   ├── feature_extraction.py# Transcript features for the ML scorer
│   │   ├── trained_scorer.py    # RandomForest scorer, LOO cross-validated
│   │   ├── scoring.py           # Answer scoring → CompetencyScore (+ optional ML score)
│   │   ├── explainability.py    # Score explanations → ExplanationItem
│   │   ├── fairness.py          # Counterfactual bias audit → FairnessFlag
│   │   └── llm_client.py        # Groq client: retries, timeout, robust JSON parsing
│   ├── reports/
│   │   ├── analytics.py     # Dashboard stats
│   │   └── pdf_export.py    # Report PDF generation
│   ├── ui/                  # Legacy PySide6 UI (pre-migration, kept for reference)
│   └── utils/
│       └── port_scanner.py  # Unauthorized-device detection helper
├── frontend/                # Next.js 14 app (static export to frontend/out)
│   ├── app/                 # login, dashboard, jobs, candidates, setup,
│   │                        # candidate/*, interview, reports, bias-audit,
│   │                        # integrity, settings, scheduling (auto-booked
│   │                        # interview list)
│   ├── components/first-run-gate.tsx  # one-time server-address screen
│   └── lib/integrity.ts     # local scan bridge + flag upload
├── electron/                # Desktop shell (TypeScript → dist/)
│   ├── main.ts              # Window + sidecar lifecycle, IPC handlers
│   ├── config.ts            # backend_mode / remote_api_url (data/settings.json)
│   ├── integrity.ts         # Native port/process scan (no Python needed)
│   └── preload.ts           # contextBridge: desktopCapturer, integrity, config
├── data/                    # Runtime data (gitignored): app.db, settings.json,
│                            # resumes, face profiles, uploaded recordings,
│                            # client_secret.json (Gmail OAuth)
├── docs/                    # INTERFACES.md, DEPLOYMENT.md, design specs & plans
├── tests/
└── requirements.txt
```

## Setup

### 1. Backend (Python)

```bash
python -m venv venv
venv\Scripts\activate            # Windows (Git Bash: source venv/Scripts/activate)
pip install -r requirements.txt
```

Run standalone (useful for API development):

```bash
python -m api.main --port 8000   # then hit http://127.0.0.1:8000/health
```

### 2. Frontend (Node)

```bash
npm run install:all              # installs frontend/ and electron/ deps
npm run dev:frontend             # dev server on localhost:3000
npm run build:frontend           # static export to frontend/out (for Electron prod mode)
```

### 3. Desktop app (Electron)

The Electron shell is a TypeScript app that spawns the FastAPI backend (local mode) and
loads the Next.js frontend. Compile it once, then run:

```bash
npm run build:electron           # compiles TypeScript to electron/dist

# Option A — development (recommended while working on the frontend):
npm run dev:frontend             # terminal 1: Next.js dev server on localhost:3000
npm run dev:electron             # terminal 2: Electron loads http://localhost:3000

# Option B — production (static export, no dev server):
npm run build:frontend           # build once, generates frontend/out/
npm run start:electron           # Electron loads frontend/out/index.html
```

> **Note on production mode**: the static export uses absolute asset paths, which do not
> render under Electron's `file://` loader (a known Next.js + Electron limitation that
> yields a blank window). For local development always use **Option A (dev mode)** which
> loads the Next.js dev server and works reliably. Production/installer builds that load
> `frontend/out` may need to serve the export over HTTP (see `docs/DEPLOYMENT.md`).

Requires a webcam/microphone for the interview flow. The first Whisper run downloads
the model automatically.

### 4. LLM key (optional)

Copy `.env.example` to `.env` and set `GROQ_API_KEY` — it is auto-loaded at startup
(python-dotenv). Without a key the system falls back to rule-based heuristics for
scoring/explanations/fairness; every fallback is logged with its reason, never silent.

Verify the LLM path end-to-end (requires the key):

```bash
python scripts/verify_llm_live.py          # proves score/explain/fairness hit the API
python scripts/compare_heuristic_vs_llm.py # side-by-side heuristic vs LLM scores
```

### 5. Trained ML scorer (optional third signal)

```bash
python scripts/generate_training_dataset.py   # generates synthetic dataset (~5-10 min)
python scripts/validate_dataset.py --sample   # exports blind subset for human validation
python scripts/validate_dataset.py --apply-scores  # ingests human scores, applies corrections
python scripts/train_trained_scorer.py        # trains RandomForest, writes data/models/
```

The scorer is trained on a synthetically generated dataset: `data/datasets/synthetic_graded_answers.json`
currently has **70 examples** (27 questions × 4 quality tiers across 6 categories). An LLM generates
candidate-style answers at varying skill levels; each is assigned a target score with jitter.
Leave-one-out cross-validation metrics are in `data/models/trained_scorer_metrics.json`:
**Pearson r = 0.8209, MAE = 12.38, RMSE = 16.21 (n = 70)**.

A blind human-validation subset has been exported to `data/datasets/human_validation_subset.csv`
(the `--sample` step). Team members can score it and ingest corrections with
`python scripts/validate_dataset.py --apply-scores`; as of this writing no human scores have
been ingested yet, so the model is trained purely on the synthetic labels.

When `data/models/trained_scorer.joblib` exists, its score is returned as `ml_score`
in `/api/scoring/run` and shown in the interview UI next to the primary score.
No model → the signal is simply skipped.

All mocked LLM/RAG tests run without any API key or model: `pytest tests/`.

## Deployment (remote interviews)

By default every install runs fully offline against its local sidecar (`backend_mode: local`
in `data/settings.json`). For candidate ↔ recruiter on different networks, deploy one
central FastAPI instance and point desktop installs at it:

```bash
# 1. Host the API (Render/Railway): start command + env var
uvicorn api.main:app --host 0.0.0.0 --port $PORT     # DEPLOY_MODE=remote

# 2. Build an installer with the server URL baked in
$env:INTERVIEWIQ_DEFAULT_REMOTE_URL = "https://<your-server>"
npm run build:frontend ; npm run build:electron
cd electron ; npx electron-builder --win              # release/*.exe
```

Fresh installs then only need the `.exe` + an invite code; the one-time setup screen
only appears if no server URL is known. Full walkthrough, data-flow diagram and
acceptance checklist: **`docs/DEPLOYMENT.md`**.

## Data contracts

All modules exchange shapes defined in `app/core/models.py`:
`InterviewSession`, `IntegrityFlag`, `CompetencyScore`, `ExplanationItem`, `FairnessFlag`,
`Candidate`, `JobPosting`, `ProcessedEmail`. See `docs/INTERFACES.md` for the end-to-end
pipeline and how team members build in parallel.

## Security model

Recruiter routes require a bearer token; candidate-facing endpoints stay intentionally
open. Ownership, signed media, rate limiting, and the known limitations (including the
cleartext `data/settings.json` and biometric anti-spoof scope) are documented in
**`SECURITY.md`**.

## Gmail integration (email-to-invite pipeline)

Automatically screens incoming job applications and invites qualified candidates:

1. **One-time setup**: Create a Google Cloud project, enable Gmail API, configure OAuth
   consent screen, download `client_secret.json` to `data/`. See `docs/DEPLOYMENT.md`.
2. **Connect**: In Settings → Email Integration, click "Connect Gmail" and complete the
   OAuth flow. Tokens are stored in `data/settings.json` (gitignored).
3. **Configure per job**: In the job posting form, set a **Gmail Application Label**
   (e.g. "Applications/Senior-Backend") and a **Screening Threshold** (0-100, default 60).
4. **Run**: Click "Check {Job Title}" on the Candidates page, or let the automatic poller
   handle it (remote mode, every 10 minutes). The pipeline:
   - Scans the Gmail label for emails with resume attachments
   - Parses resumes and matches against the job description (reuses existing pipeline)
   - Above threshold: creates candidate, generates invite code, sends invite email
   - Below threshold: records candidate for transparency, does not invite
   - Marks emails as processed to prevent re-processing

A recruiter can still manually invite any candidate through the normal "Invite Candidate"
flow, overriding the automated screening — this is an intentional human-in-the-loop safeguard.

## Automatic interview scheduling (auto-book from recruiter availability)

Shortlisted (above-threshold) candidates are automatically booked into the recruiter's
next free slot from their Google Calendar, and the integ 
  bug (client_id/secret now persisted), 9 scheduling tests (193 total passing)
- ✅ Recruiter auth + ownership scoping: salted-hash login bound to the running server,
  HMAC bearer-token verification on every recruiter route, and owner-scoped reads for
  jobs, candidates, applications, scheduled interviews, reports and integrity flags
  (cross-recruiter access → 403). Signed medium: replaced the open `/media` StaticFiles
  mount with short-lived HMAC URLs issued by `GET /api/media/sign` (traversal + expiry
  checked at serve time)
- ✅ Async application intake: `POST /api/public/apply/{job_id}` now returns `202` +
  `application_id`, the screening pipeline runs in a background worker (store-first,
  resume → screening → outcome chained in one transaction), and application status /
  screening result is tracked per application and surfaced on a new **Applications** page
- ✅ Security test suite: `tests/test_security_auth.py` covers unauthenticated 401s,
  cross-recruiter IDOR denial (403), signed-media serving + traversal, and invite
  consume-once hardening; full backend suite green (216 tests) with `tsc` + static-export
  build green on the frontend (18 frontend tests)
- ✅ Screening audit & funnel: results persist the threshold used (`threshold_used`),
  per-job pipeline funnel stats (`GET /api/applications/stats` + stat bar on the
  Applications page), an explicit **Re-screen** action (`POST
  /api/applications/{id}/rescreen`) that recomputes a decision after a threshold/config
  change (409 while in flight, 403 cross-recruiter, never duplicates candidates), and a
  durable per-application **audit trail** (`application_events`, exposed in the
  application-detail API). The candidate shortlist is backend-enforced and tested:
  rejected / manual-review applicants never appear in the Candidates list
- ✅ Screening hardening & decision explainability: hard-requirement gates (education,
  experience) checked independently of the weighted ATS score; a per-job
  `screening_enabled` toggle that routes applications to manual review; the candidate
  shortlist now LEFT JOINs screening results so only `passed` applicants surface
  (admin ops like delete/resend still reach all candidates); interview access is
  token-gated (HMAC purpose-scoped token, 4 h TTL, consume-once invite, resend requeues
  the email and clears superseded codes); resumes served from the media root are
  normalized to relative media paths; dashboard shows a decision-oriented funnel
  (applications / shortlisted / invites sent / interviews completed) with attention
  badges, and the Candidates page explains **Why shortlisted?** per candidate (decision,
  ATS vs threshold, component scores, hard gates, matched/missing skills). Full backend
  suite green (235 tests), frontend green (18 vitest tests, `tsc`, static-export build)

Still open:

- SHAP/LIME overlays for score explainability
- Gaze-tracking signals (mediapipe face mesh) for the integrity module
- Harden the central server for production: Postgres instead of SQLite, token rotation/expiry
  and brute-force backoff on auth, HTTPS termination guidance in DEPLOYMENT.md
- Remove the legacy PySide6 UI once feature parity is confirmed
- Skip weekends/holidays during auto-scheduling (currently books any free calendar slot within working hours)
- Support rescheduling/cancellation of a booked interview (calendar event update/delete + re-invite email)

## Team

Manthan Gharat, Atharv Shigwan, Riddhi Verma, Ayush — under faculty supervision.
