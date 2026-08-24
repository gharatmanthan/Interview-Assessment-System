# Deployment Guide — Remote Access via Electron

This app is a **desktop application** (Electron + Next.js + FastAPI). Candidates and
recruiters both install the same Electron app. The frontend is **never served as a
standalone website** — this is deliberate, not an oversight: integrity checks
(remote-access port scanning and process scanning) only produce real signals when
they execute locally on the machine being monitored, so the candidate's interview UI
must always run inside Electron on their own laptop.

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
then uploaded to `POST /api/sessions/{id}/upload` and streamed back from `/media/...`.

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
- For anything beyond a student project, swap SQLite for Postgres and add auth
  tokens before exposing the API publicly.

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
├─ recording uploaded ────────────────►    ├─ POST /api/sessions/{id}/upload │   (/media/uploads/...)
└─ questions/scores fetched ◄─────────     └─ serves /media/uploads/**       └─ PDF/CSV export
```

## Acceptance checklist

- [x] Local mode unchanged: Electron still spawns the sidecar on a random port; no regressions for single-machine use (`DEPLOY_MODE` unset keeps `127.0.0.1`).
- [x] Remote mode: candidate's app fetches job/question data from the central server (`frontend/lib/api.ts` resolves the base URL from Electron config).
- [x] Port/process scans detect real local signals even with `backend_mode=remote` (test: start AnyDesk/TeamViewer on the test machine, watch device-check + live monitor flag it).
- [x] Locally-generated flags appear in the recruiter's Integrity Log (stored centrally).
- [x] Recordings upload and play back through the recruiter's Reports page.
- [x] No code path requires or assumes a plain web browser.
