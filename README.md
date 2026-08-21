# InterviewIQ — AI-Powered Interview Assessment System

Academic project (Computer Engineering, group project) exploring **explainability + bias auditing**
combined with **integrity / AI-assisted-answer detection** for automated interview assessment tools.

## Current status: v0.3 — Electron + Next.js + FastAPI stack

The app has migrated from a monolithic PySide6 desktop UI to a three-tier architecture:
**Electron shell → Next.js frontend → FastAPI backend** (Python engine unchanged underneath).

What works right now:

- **Recruiter flow** — login/register (salted-hash auth), job postings, candidate management
  with invite codes and resume upload/parsing
- **Candidate flow** — invite-code entry, consent screen, preflight camera/mic check,
  face enrollment & verification (OpenCV), guided interview session
- **Interview session** — video/audio capture, Whisper (faster-whisper) transcription,
  answer scoring against rubrics, heuristic explanations per score
- **Live monitor** — recruiters watch in-progress interviews with live frames
- **Integrity checks** — port scan, suspicious-process scan, external device monitoring,
  single-face verification; flags logged to SQLite
- **Reports** — dashboard stats, session scores/explanations, PDF export (fpdf2)
- **Bias audit** — counterfactual fairness checks producing fairness flags

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Electron shell (electron/main.ts)                       │
│  • picks a free port, spawns the FastAPI backend        │
│  • polls /health until ready, then opens the window     │
│  • loads frontend/out (prod) or localhost:3000 (dev)    │
│  • kills the Python process on quit                     │
└───────────────┬─────────────────────────────────────────┘
                │ HTTP (127.0.0.1:<random port>)
┌───────────────▼─────────────────────────────────────────┐
│ Next.js 14 frontend (frontend/) — static export         │
│  React 18 + Tailwind CSS + Radix UI (shadcn-style)      │
└───────────────┬─────────────────────────────────────────┘
                │ fetch /api/*
┌───────────────▼─────────────────────────────────────────┐
│ FastAPI backend (api/)                                  │
│  routes: auth, jobs, candidates, sessions, scoring,     │
│          reports, integrity, settings, devices,         │
│          candidate-flow                                 │
└───────────────┬─────────────────────────────────────────┘
                │ imports
┌───────────────▼─────────────────────────────────────────┐
│ Core engine (app/)                                      │
│  core/       SQLite db, models, auth, question bank     │
│  candidate/  capture, face recognition, integrity       │
│  engine/     Whisper STT, resume parser, JD matcher,    │
│              RAG rubrics, scoring, explainability,      │
│              fairness, LLM client                       │
│  reports/    analytics, PDF export                      │
└─────────────────────────────────────────────────────────┘
```

## Project structure

```
interview-assessment-system/
├── api/                     # FastAPI app
│   ├── main.py              # Entry point (spawns on a random port from Electron)
│   ├── schemas.py           # Pydantic request/response models
│   └── routes/              # One router per feature area
├── app/
│   ├── core/
│   │   ├── db.py            # SQLite persistence (data/app.db)
│   │   ├── models.py        # The 5 shared data shapes (see docs/INTERFACES.md)
│   │   ├── auth.py          # Recruiter register/verify (salted hashes)
│   │   ├── question_bank.py # Interview questions
│   │   └── settings_store.py# App settings (data/settings.json)
│   ├── candidate/
│   │   ├── capture.py       # Video/audio recording (MediaCapture)
│   │   ├── face_recognition.py # Face enroll / verify / single-face check
│   │   └── integrity.py     # Port scan, process scan, device monitor
│   ├── engine/
│   │   ├── stt.py           # faster-whisper transcription
│   │   ├── resume_parser.py # PDF/DOCX resume parsing
│   │   ├── jd_matcher.py    # Resume ↔ job-description matching
│   │   ├── rag.py           # Rubric retrieval per job/category
│   │   ├── scoring.py       # Answer scoring → CompetencyScore
│   │   ├── explainability.py# Score explanations → ExplanationItem
│   │   ├── fairness.py      # Counterfactual bias audit → FairnessFlag
│   │   └── llm_client.py    # Optional LLM backend hook
│   ├── reports/
│   │   ├── analytics.py     # Dashboard stats
│   │   └── pdf_export.py    # Report PDF generation
│   ├── ui/                  # Legacy PySide6 UI (pre-migration, kept for reference)
│   └── utils/
│       └── port_scanner.py  # Unauthorized-device detection helper
├── frontend/                # Next.js 14 app (static export to frontend/out)
│   └── app/                 # login, dashboard, jobs, candidates, candidate,
│                            # interview, reports, bias-audit, integrity, settings
├── electron/                # Desktop shell (TypeScript → dist/)
├── data/                    # Runtime data (gitignored): app.db, resumes, face profiles
├── docs/                    # INTERFACES.md (data contracts), design specs & plans
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

## Data contracts

All modules exchange five shapes defined in `app/core/models.py`:
`InterviewSession`, `IntegrityFlag`, `CompetencyScore`, `ExplanationItem`, `FairnessFlag`.
See `docs/INTERFACES.md` for the end-to-end pipeline and how team members build in parallel.

## Roadmap

- Replace heuristic scoring/explanations with real model-backed scoring (SHAP/LIME overlays)
- Wire `llm_client.py` into scoring as an optional backend
- Gaze-tracking signals (mediapipe face mesh) for the integrity module
- Package the Electron app into installers (electron-builder)
- Remove the legacy PySide6 UI once feature parity is confirmed

## Team

Manthan Gharat, Atharv Shigwan, Riddhi Verma, Ayush — under faculty supervision.
