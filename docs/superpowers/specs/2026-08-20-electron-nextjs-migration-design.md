# Electron + Next.js + FastAPI UI Migration — Design Spec

## Goal

Replace the PySide6 desktop UI with an Electron + Next.js + Tailwind CSS + shadcn/ui frontend, while wrapping the existing Python backend as a local FastAPI API. All existing Python code in `app/` remains untouched.

## Architecture

```
Electron Shell (main.ts)
  ├── Spawns FastAPI as child process on random port
  ├── Waits for /health check before loading UI
  └── Creates BrowserWindow loading Next.js static export

Next.js Renderer (React)
  ├── Tailwind CSS + shadcn/ui for all UI components
  ├── fetch() client (lib/api.ts) → http://localhost:{port}/api/*
  └── 9 pages: login, dashboard, jobs, candidates, interview, reports, bias-audit, integrity, settings

FastAPI Server (api/)
  ├── Thin route layer calling existing app/ functions
  ├── Pydantic schemas mirroring app/core/models.py dataclasses
  ├── WebSocket for live integrity polling
  └── File upload endpoint for resume attachment

Existing Python (app/)
  ├── UNTOUCHED — all modules remain as-is
  └── Imported by api/ routes
```

## Tech Stack

- **Electron** 33+ with electron-builder for packaging
- **Next.js** 14+ with App Router, static output (`output: 'export'`)
- **Tailwind CSS** 3.4+ with custom theme matching existing palette
- **shadcn/ui** — New York style, slate base color
- **FastAPI** with uvicorn, python-multipart, websockets
- **TypeScript** throughout frontend + electron

## API Surface

### Auth
- `POST /api/auth/login` → `auth.verify_recruiter()`
- `POST /api/auth/register` → `auth.register_recruiter()`

### Jobs
- `GET /api/jobs` → `db.get_all_job_postings()`
- `POST /api/jobs` → `db.save_job_posting()`
- `PUT /api/jobs/{job_id}` → `db.save_job_posting()`
- `DELETE /api/jobs/{job_id}` → `db.delete_job_posting()`

### Candidates
- `GET /api/candidates` → `db.get_all_candidates()`
- `GET /api/candidates/job/{job_id}` → `db.get_candidates_for_job()`
- `POST /api/candidates` → `db.save_candidate()`
- `DELETE /api/candidates/{candidate_id}` → `db.delete_candidate()`
- `POST /api/candidates/{candidate_id}/resend` → `db.regenerate_invite_code()`
- `POST /api/candidates/{candidate_id}/resume` → file upload + `resume_parser.parse_resume()` + `jd_matcher.match_resume_to_jd()`

### Sessions
- `POST /api/sessions` → `db.save_session()`
- `GET /api/sessions` → `db.get_all_sessions()`

### Scoring Pipeline
- `POST /api/scoring/run` → `scoring.score_answer()` + `explainability.explain_score()` + `fairness.audit_bias()`

### Reports
- `GET /api/reports/dashboard` → `analytics.get_dashboard_stats()`
- `GET /api/reports/candidate/{session_id}` → `analytics.get_candidate_report()`
- `GET /api/reports/compare?job_id=` → `analytics.get_candidate_comparison()`

### Export
- `GET /api/export/csv?job_id=` → CSV file response
- `GET /api/export/pdf/{session_id}` → PDF file response

### Integrity & Bias
- `GET /api/integrity/flags` → `db.get_all_integrity_flags()`
- `GET /api/bias/flags` → `db.get_all_fairness_flags()`
- `WS /ws/integrity/{session_id}` → live integrity polling

### Settings & Devices
- `GET /api/settings` → `settings_store.load_settings()`
- `PUT /api/settings` → `settings_store.save_settings()`
- `GET /api/devices` → camera/microphone list

## Electron Integration

- Main process spawns `python -m api.main --port 0`
- Polls `http://localhost:{port}/health` until 200 (15s timeout)
- `preload.ts` exposes `window.electronAPI.getSources()` via contextBridge for webcam
- On `will-quit`, kills the FastAPI child process
- Production: loads Next.js static export from `file://`
- Dev: loads `http://localhost:3000`

## Frontend Pages (9 total)

| Route | Page | Key Components |
|-------|------|----------------|
| `/login` | Login/Register | card, input, button, tabs |
| `/dashboard` | Dashboard | 5 stat cards, job posting table |
| `/jobs` | Job Postings | Form with sliders, CRUD table, dialog |
| `/candidates` | Candidates | Table, invite dialog, resume upload |
| `/interview` | Interview Session | Webcam, question nav, transcript, integrity badge |
| `/reports` | Reports | Session list, score breakdown, comparison, PDF/CSV export |
| `/bias-audit` | Bias Audit | Fairness flags table with delta badges |
| `/integrity` | Integrity Log | Flags table with severity badges |
| `/settings` | Settings | Device selects, API key, export dir |

## Color Theme (from existing theme.py)

| Token | Value | Tailwind |
|-------|-------|----------|
| sidebar | #1B1F2A | slate-900 |
| bg | #F4F5F8 | slate-50 |
| card | #FFFFFF | white |
| primary | #5B5FEF | Custom indigo |
| secondary | #14B8A6 | teal-500 |
| warning | #F59E0B | amber-500 |
| danger | #EF4444 | red-500 |
| text | #1B1F2A | slate-900 |
| text_muted | #6B7280 | slate-500 |
| border | #E5E7EB | slate-200 |

## Constraints

- Existing `app/` directory: ZERO modifications
- Python backend additions only in new `api/` directory
- All API responses use JSON (Pydantic models)
- File uploads via multipart/form-data
- WebSocket for real-time integrity polling
- Electron must work on Windows (primary target)
