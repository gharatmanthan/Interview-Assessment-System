# Deployment Guide — Remote Access via Electron

This app has **two surfaces**: a **desktop application** (Electron + Next.js + FastAPI)
for recruiters, and a **public Next.js website** for external candidates.

- **Recruiters** run the Electron desktop app (or local dev) as the control surface.
  Electron can either spawn a local sidecar (`backend_mode=local`) or talk to a central
  server (`backend_mode=remote`).
- **External candidates do NOT install the Electron app.** They interact through the
  public website over HTTPS — applying at `/apply?jobId=...` and taking their online
  interview via invite codes from emailed links at `/candidate/entry?code=...`.

The integrity checks (remote-access port scanning and process scanning) only produce
real signals when they execute locally on the machine being monitored. For remote
candidates taking a live Mode 1 interview, the interview UI still runs locally on the
candidate's own machine; the web `/apply` and `/candidate/entry` pages are the public
entry points into the same system.

## External-candidate web deployment (candidates in the browser)

| What                                 | Where it lives                       | Env var                  |
|---------------------------------------|--------------------------------------|--------------------------|
| Application link, `/apply`, candidate pages | `NEXT_PUBLIC_APP_URL` (frontend) | `https://<frontend-domain>` |
| Backend API the candidate browser calls    | `NEXT_PUBLIC_API_URL` (frontend)    | `https://<backend-domain>` |
| Public apply URL in LinkedIn posts         | `PUBLIC_APP_URL` (backend)          | `https://<frontend-domain>` |
| CORS allow-list for the frontend origin    | `FRONTEND_ORIGIN` (backend)         | `https://<frontend-domain>` |
| Central bind host                          | `DEPLOY_MODE=remote` (backend)      | `remote`                 |

Flow:
1. Recruiter copies the application link (built from `NEXT_PUBLIC_APP_URL`) or posts to
   LinkedIn (built from `PUBLIC_APP_URL`). Both point at
   `https://<frontend-domain>/apply?jobId=...`.
2. A candidate opens that link in any browser → the public `/apply` page fetches job
   details from `NEXT_PUBLIC_API_URL` and submits the resume to
   `https://<backend-domain>/api/public/apply/...`.
3. The backend screens the application and, for invited candidates, emails a link at
   `https://<frontend-domain>/candidate/entry?code=...`.

**HTTPS is required in production.** Both the frontend and backend must be served over
HTTPS (terminate TLS with the platform's proxy or a reverse proxy). Never use
`http://localhost` for `NEXT_PUBLIC_*` / `PUBLIC_APP_URL` / `FRONTEND_ORIGIN` in a
real deployment — an external candidate's browser must not call its own localhost.

## Architecture overview

Two backend modes, chosen per desktop installation (`data/settings.json` →
`backend_mode`, shared by `app/core/settings_store.py` and `electron/config.ts`):

| Mode | Who uses it | What happens |
|------|-------------|--------------|
| `local` (default) | On-site / single-machine / walk-in use | Electron spawns `api/main.py` as a sidecar on a random loopback port. Zero setup, unchanged behavior. |
| `remote` | Candidate + recruiter on different networks | No sidecar. All shared data (jobs, candidates, scores, reports, recordings) goes to one central FastAPI server over HTTPS. |

**Integrity checks stay local in both modes.** Port/process scanning runs natively
inside Electron's main process (`electron/integrity.ts`, mirroring
`app/candidate/integrity.py`) because only the candidate's own machine can see its
own TeamViewer/RDP/VM processes. The central server never scans anything; it only
receives the resulting flags via `POST /api/integrity/flags` and stores them in the
shared DB for the recruiter's Integrity Log.

Recordings work the same way: captured locally with `MediaRecorder` inside Electron,
then uploaded to `POST /api/sessions/{id}/upload` and streamed back from `/media/...`
behind a short-lived HMAC-signed URL issued by `GET /api/media/sign` (recruiter auth required).

## Part 1 — Deploy the central API (Render / Railway free tier)

1. Push this repository to GitHub/GitLab.
2. Create a new **Web Service** pointing at the repo.
3. Configuration:
   - **Root directory:** leave as repo root (the app imports `api.main:app`)
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - **Environment variables:**
     - `DEPLOY_MODE=remote` ← required. Switches the default bind host to `0.0.0.0`
       (without it, `api/main.py` binds `127.0.0.1` for local-sidecar use).
     - `PYTHON_VERSION=3.11` (recommended)
4. Deploy. Note the public URL, e.g. `https://interviewiq-api.onrender.com`.
5. Sanity check: `curl https://<your-url>/health` should return `{"status":"ok"}`.

Notes:
- No code changes are needed for deployment — `api/routes/*` already talks to the
  SQLite DB through `app/core/db.py`. The central instance owns that SQLite file
  (`data/app.db`); every connected desktop app reads/writes it over HTTP.
- Free tiers sleep after inactivity; the first request of the day may take ~30s.
- Recruiter routes are already protected by salted-hash login + HMAC bearer tokens;
  candidate-facing endpoints (apply portal, candidate interview flow) intentionally
  remain open — see `SECURITY.md`.

## Part 2 — Build the installer with the server URL baked in

The default remote URL shown on the first-run setup screen comes from
`INTERVIEWIQ_DEFAULT_REMOTE_URL` (read in `electron/config.ts`). Bake it in at
build time:

```powershell
# Windows
$env:INTERVIEWIQ_DEFAULT_REMOTE_URL = "https://interviewiq-api.onrender.com"
cd frontend ; npm run build ; cd ..\electron
npx tsc                                          # compiles dist/
npx electron-builder --win                       # produces release/*.exe (see electron-builder.yml)
```

Candidates who install this build get the server pre-filled and never see manual
configuration. Anyone who does need to change it gets a **one-time setup screen**
("Connect to Interview Server") on first launch, reachable later from
Settings → Connection. Recruiters sharing the app just send:

1. the built `.exe` (any downloadable location works for a student project), and
2. the invite code, exactly as today.

## Data flow cheat sheet

```
Candidate laptop (Electron)                Central server (Render)           Recruiter laptop (Electron)
├─ webcam/mic capture (MediaRecorder)      ├─ SQLite: jobs, candidates,      ├─ Jobs / candidates CRUD
├─ port+process scan (local, native) ──►   │  scores, flags, sessions        ├─ Integrity Log ◄── reads flags
├─ flags POSTed ──────────────────────►    ├─ POST /api/integrity/flags      ├─ Reports + recording player
├─ recording uploaded ────────────────►    ├─ POST /api/sessions/{id}/upload │   (signed GET /media/uploads/...)
└─ questions/scores fetched ◄─────────     └─ serves signed /media/uploads/**  └─ PDF/CSV export
```

## Acceptance checklist

- [x] Local mode unchanged: Electron still spawns the sidecar on a random port; no regressions for single-machine use (`DEPLOY_MODE` unset keeps `127.0.0.1`).
- [x] Remote mode: candidate's app fetches job/question data from the central server (`frontend/lib/api.ts` resolves the base URL from Electron config).
- [x] Port/process scans detect real local signals even with `backend_mode=remote` (test: start AnyDesk/TeamViewer on the test machine, watch device-check + live monitor flag it).
- [x] Locally-generated flags appear in the recruiter's Integrity Log (stored centrally).
- [x] Recordings upload and play back through the recruiter's Reports page.
- [x] No code path requires or assumes a plain web browser.

## Gmail Integration (Email-to-Invite Pipeline)

### One-time Google Cloud setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. "InterviewIQ Email Integration").
3. Enable the **Gmail API** under APIs & Services → Library.
4. Go to APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID.
5. Configure the **OAuth consent screen**:
   - User type: External (Testing mode is fine for student projects).
   - Add your test Gmail accounts as test users.
6. Add scopes: `gmail.readonly`, `gmail.send`, `gmail.labels`.
7. Create a **Desktop app** OAuth client ID.
8. Download the `client_secret.json` file.

### Configure the application

1. Place `client_secret.json` in the `data/` directory (already gitignored).
2. In the app, go to **Settings → Email Integration → Connect Gmail**.
3. Complete the OAuth consent flow in the browser that opens.
4. Once connected, the status shows "Connected as your-email@gmail.com".

### Per-job configuration

1. Create a Gmail label in your inbox for applications (e.g. "Applications/Senior-Backend").
2. In the app, edit the job posting and set:
   - **Gmail Application Label**: the label name (e.g. "Applications/Senior-Backend")
   - **Screening Threshold**: minimum match score (0-100, default 60) to auto-invite
3. Forward or have applicants send resumes to the connected Gmail account, tagged with the label.

### How it works

- **Manual trigger**: Click "Check {Job Title}" on the Candidates page to scan for new applications.
- **Automatic polling** (remote mode only): The server checks every 10 minutes for new emails in configured labels.
- **Local mode**: Polling only runs while the app is open; use the manual button.
- Candidates scoring above the threshold are auto-invited with an email containing their invite code.
- Candidates scoring below the threshold are recorded for transparency but not invited.
- A recruiter can still manually invite any candidate through the normal "Invite Candidate" flow, overriding the automated screening.

### Security notes

- OAuth refresh tokens are stored in `data/settings.json` (gitignored), never in SQLite.
- The `client_secret.json` file must never be committed to version control.
- The connected Gmail account's refresh token gives read/send access — treat it as a secret.
