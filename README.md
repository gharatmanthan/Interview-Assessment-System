# InterviewIQ — AI-Powered Interview Assessment System

Academic project (Computer Engineering, group project) exploring **explainability + bias auditing**
combined with **integrity / AI-assisted-answer detection** for automated interview assessment tools.

## Current status: v0.1 — App Shell + Interview Session MVP

What works right now:
- Full desktop app shell (sidebar navigation, 6 sections)
- Candidate sign-in before accessing the candidate dashboard
- Live webcam preview on the "New Interview" screen (via OpenCV)
- Question flow (next/previous navigation through question bank)
- Microphone recording with local Whisper speech-to-text in the transcript panel
- Dashboard with stat cards (currently static — wire to real data next)
- Placeholder pages for Reports, Bias Audit, and Integrity Log describing exactly what
  each will contain once the backend pipelines are built

## Project structure

```
interview-assessment-system/
├── app/
│   ├── main.py              # Entry point
│   ├── core/
│   │   └── question_bank.py # Interview questions (swap for DB later)
│   ├── models/               # (empty) ML models will live here — scoring, SHAP, gaze, etc.
│   ├── ui/
│   │   ├── main_window.py   # Main window + page routing
│   │   ├── sidebar.py       # Navigation sidebar
│   │   └── pages/
│   │       ├── dashboard_page.py
│   │       ├── interview_page.py    # Core interview session screen
│   │       └── placeholder_page.py  # Reusable "coming soon" page
│   └── utils/
│       └── theme.py         # Colors + QSS stylesheet (single source of design truth)
├── assets/                   # Icons/images (empty for now)
├── data/                     # Session recordings/transcripts will be stored here
├── tests/                    # (empty) add unit tests here
└── requirements.txt
```

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

Requires a webcam for the interview screen to show a live preview (click "Start Camera").
If no webcam is available it will show an error message but the rest of the app still works.

The local demo candidate account is `candidate01` with password `interview123`.

## Start the API locally

The API is the first deployment layer for sharing live interview state between
the candidate and interviewer applications. It currently uses the existing
SQLite database, so it runs locally without cloud credentials. The database
layer can later be replaced with a managed PostgreSQL connection without
changing the HTTP contract.

Install the API dependencies and start the service:

```powershell
pip install -r requirements.txt
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The cloud container uses the smaller [`requirements-api.txt`](requirements-api.txt)
file because it does not need desktop camera, audio, or Qt packages.

Verify it from the host computer:

```powershell
curl http://127.0.0.1:8000/health
```

Interactive API documentation is available at `/docs`.

## Deploy the API to Render

The repository includes a `Dockerfile` and `render.yaml` for deploying the
API as a Render web service. The deployed API uses PostgreSQL for shared,
persistent interview data. Desktop clients may continue using local SQLite
when remote mode is disabled.

1. Rotate any API key that was previously stored in `data/settings.json`.
2. Push the repository to GitHub.
3. In Render, choose **New > Blueprint**, select the repository, and apply
   `render.yaml`.
4. Set `CORS_ORIGINS` to the exact URL of the future frontend, or use `*`
   temporarily for API-only testing.
5. Set `GROQ_API_KEY` using a newly generated key in Render's environment
   settings. Never commit it to the repository.
6. Set `DATABASE_URL` to the pooled connection string from Neon. Keep it as a
   Render secret and use the `postgresql://` or `postgres://` URL provided by
   Neon.
7. Set `AUTH_SECRET` to a long random value. Also set `INTERVIEWER_ID`,
   `INTERVIEWER_PASSWORD`, and optionally `INTERVIEWER_NAME`. These values
   create the initial interviewer account on first startup; never use the old
   demo credentials.
8. After deployment, verify:

```text
https://YOUR-SERVICE.onrender.com/health
https://YOUR-SERVICE.onrender.com/health/ready
https://YOUR-SERVICE.onrender.com/docs
```

The API base URL for future desktop/frontend clients will be:

```text
https://YOUR-SERVICE.onrender.com/api/v1
```

The deployed service also serves a candidate registration page at `/`. An
interviewer creates an invitation through `POST /api/v1/public/invitations`
with an authenticated interviewer token and a job ID. Share the returned URL:

```text
https://YOUR-SERVICE.onrender.com/?token=RETURNED_TOKEN
```

The invitation expires after the requested period (default 72 hours) and can
be used once. The public page never exposes the invitation token in server
logs beyond the URL request, so treat the link as confidential.

After registration, the page can start a browser interview, request camera
permission, publish the latest compressed preview frame, and share a typed
answer with the interviewer monitor. Browser mode cannot inspect running
processes or connected USB devices; use the native candidate client when
those host-integrity checks are required. Camera and device inspection require
candidate consent.

## Candidate device-monitoring policy

The native candidate client checks for USB storage, physical serial devices,
known remote-access processes, and known remote-access ports. These checks
produce review signals; they do not prove misconduct or automatically reject a
candidate. Bluetooth virtual COM ports are ignored because they are commonly
created by normal operating-system pairing.

If an organization has an approved serial device that should not be reported,
set this variable on the candidate PC as a comma-separated list of matching
device markers:

```powershell
$env:INTERVIEWIQ_ALLOWED_SERIAL = "Approved Reader,COM7"
```

Environment checks run at interview start and periodically during a live
interview. Camera and host checks are performed locally because browser
JavaScript cannot inspect operating-system processes or hardware reliably.

The live monitor stores only the latest compressed JPEG frame per active
session in the configured PostgreSQL database. Frames are replaced on upload,
are not an interview recording, and are deleted automatically when the
interview session is removed. The media endpoints require the candidate or
interviewer access token appropriate to the operation.

## Use two desktop PCs with the shared Render API

The desktop app uses local SQLite by default. To make a candidate PC and an
interviewer PC share accounts, jobs, and live interview state, configure both
PCs before starting the app:

```powershell
$env:INTERVIEWIQ_BACKEND_MODE = "remote"
$env:INTERVIEWIQ_API_URL = "https://interviewiq-api-736y.onrender.com/api/v1"
python -m app.main --role interviewer
```

On the candidate PC, use the same two environment variables and start:

```powershell
python -m app.main --role candidate
```

The Render URL must be replaced if your service has a different URL. The
Settings page also supports selecting **Shared Render API** and saving the
same URL after logging in.

## Architecture (planned modules)

1. **Interview Engine** (`app/ui/pages/interview_page.py`) — question flow, webcam/mic capture ✅ MVP done
2. **Transcription & NLP Scoring** — Whisper for speech-to-text, answer relevance scoring — not started
3. **Explainability Layer** — SHAP/LIME overlays explaining each score — not started
4. **Bias Audit Module** — fairness metrics across proxy groups — not started
5. **Integrity Detection Module** — gaze tracking, response-latency anomalies, AI-text fingerprinting
   — not started (this is the core novel research contribution)
6. **Reporting Dashboard** — candidate + evaluator views — static shell only

## Next steps

- Wire microphone recording + Whisper transcription into `interview_page.py`
- Add `app/models/scoring.py` for a first-pass answer scoring model
- Add `app/models/explainability.py` using SHAP against the scoring model
- Design gaze-tracking approach (mediapipe face mesh) for the integrity module
- Persist session data to `data/` (SQLite recommended over flat files)

## Team

Manthan Gharat, Atharv Shigwan, Riddhi Verma, Ayush — under faculty supervision.
