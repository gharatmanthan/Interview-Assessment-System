# InterviewIQ — AI-Powered Interview Assessment System

Academic project (Computer Engineering, group project) exploring **explainability + bias auditing**
combined with **integrity / AI-assisted-answer detection** for automated interview assessment tools.

## Current status: v0.5 — email-to-invite candidate pipeline

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
│          candidate-flow, email-intake                   │
│  static: /media/uploads/** (interview recordings)       │
│  background: Gmail poller (10 min, remote mode)         │
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
│   │                        # integrity, settings
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

```bash
npm run build:electron           # compiles TypeScript to electron/dist
cd electron && npm start         # production: spawns backend + loads frontend/out
npm run dev -- --dev             # dev: loads http://localhost:3000 instead
```

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

The scorer is trained on a synthetically generated dataset (~120 examples, 30 questions
× 4 quality tiers across 6 categories). An LLM generates candidate-style answers at
varying skill levels; each is assigned a target score with jitter. A human-validation
subset (~25% of examples, scored blind by team members) calibrates synthetic labels
against real judgment — corrections are applied where divergence exceeds 20 points.
See the training script docstring for the full methodology.

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

## Roadmap

Completed since v0.4 (previously listed here as pending):

- ✅ `llm_client.py` wired into scoring/explanations/fairness/JD matching — with
  retries, 15s timeout, markdown-fence-tolerant JSON parsing, and logged heuristic
  fallbacks; `.env` is now auto-loaded via python-dotenv
- ✅ RAG rubric retrieval: local embeddings (model2vec `potion-base-8M`; TF-IDF
  fallback) over a hand-authored ~50-snippet rubric knowledge base; top-8 snippets
  retrieved per job description + question category, static category lookup kept as
  fallback. NOT a vector DB — snippets are embedded in-process, no Chroma/FAISS
- ✅ JD matching: LLM semantic matching (`matched_by: "llm_semantic"`) over the old
  keyword-overlap heuristic (now fallback only)
- ✅ Trained classical ML scorer: RandomForest on transcript features, Leave-One-Out
  CV (pearson r / MAE / RMSE reported), surfaced as optional third signal — still on
  a placeholder dataset
- ✅ Replaced placeholder ML-scorer dataset with LLM-generated quality-tier dataset
  (~120 examples, human-validated subset with Pearson's r correlation reported)
- ✅ Email-to-invite pipeline: Gmail OAuth integration, automatic resume screening
  against job postings, threshold-based auto-invitation with email delivery, manual
  trigger + background polling (remote mode), source/screening visibility on
  candidates page, 6 mocked test cases (173 total tests passing)

Still open:

- SHAP/LIME overlays for score explainability
- Gaze-tracking signals (mediapipe face mesh) for the integrity module
- Harden the central server for production: Postgres instead of SQLite, auth tokens on the API
- Remove the legacy PySide6 UI once feature parity is confirmed

## Team

Manthan Gharat, Atharv Shigwan, Riddhi Verma, Ayush — under faculty supervision.
