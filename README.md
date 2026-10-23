# InterviewIQ - Desktop Interview Assessment System

InterviewIQ is a desktop-based interview assessment system for candidates and
interviewers. It combines live interview capture, speech-to-text, competency
scoring, explainability, fairness analysis, reporting, and integrity
monitoring.

The system has no browser client, public web registration flow, Render
deployment, or cloud database. Both roles use the same desktop application.

## Architecture

```text
Candidate desktop PC ── local network ── Interviewer desktop PC
                                      │
                              InterviewIQ desktop app
                                      │
                              Local FastAPI + SQLite
```

The interviewer PC runs the local API and shared SQLite database for a
two-PC interview. The candidate PC runs the same application and connects to
the interviewer's private LAN address. For a single-PC demonstration, use
local SQLite without starting the API.

## Desktop roles

### Candidate

- Sign in to the candidate desktop application.
- Complete assigned interview questions.
- Use the webcam and microphone.
- Record answers and generate local Whisper transcripts.
- Submit interview state and integrity signals to the interviewer PC.
- Run local checks for USB storage, serial devices, remote-access processes,
  and known remote-access ports.
- Record when the interview window loses focus because the candidate switches
  to another application or window. This is an advisory integrity signal, not
  automatic proof of misconduct.

### Interviewer

- Sign in to the interviewer desktop application.
- Create jobs and candidate accounts.
- Monitor active interviews over the local network.
- View the latest candidate camera frame.
- Approve the next question.
- Review integrity flags.
- Inspect assessment, explainability, fairness, and PDF reports.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

The application opens a role selector. Choose **Candidate** or
**Interviewer**. The optional command-line role is available for shortcuts:

```powershell
python -m app.main --role candidate
python -m app.main --role interviewer
```

The current temporary demo accounts are hardcoded for development:

```text
Interviewer ID: interviewer01
Interviewer password: interviewer123
Candidate ID: candidate01
Candidate password: interview123
```

## Local-only mode

Use **This PC (local SQLite)** in Settings when testing on one computer. This
mode needs no API, network, PostgreSQL, Docker, or cloud service.

Both role windows can be started on the same computer:

```powershell
python -m app.main
python -m app.main
```

Select a different role in each window.

## Local-network mode

For two computers, the interviewer PC hosts the API and its SQLite database.
Install the API dependencies on the interviewer PC:

```powershell
pip install -r requirements-api.txt
$env:INTERVIEWIQ_API_DB = "C:\InterviewIQ\data\network.db"
$env:AUTH_SECRET = "local-development-secret"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The database file is created automatically. Verify the service:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

On the interviewer PC, open the desktop application and select the
**Interviewer** role. On the candidate PC, open the same application and
select the **Candidate** role. On the candidate PC, open Settings, select
**Local network API**, and set the API URL to the interviewer's LAN address:

```text
http://192.168.1.100:8000/api/v1
```

Allow port `8000` through the interviewer PC's private-network firewall. Both
PCs must be connected to the same private network. The API must not be exposed
to the public internet.

To find the interviewer PC's LAN address:

```powershell
ipconfig
```

Use the **IPv4 Address** from the active Wi-Fi or Ethernet adapter.

## Two-PC test sequence

1. Start the API on the interviewer PC.
2. Verify `/health` and `/health/ready`.
3. Start InterviewIQ on the interviewer PC and select **Interviewer**.
4. Start InterviewIQ on the candidate PC and select **Candidate**.
5. Configure the candidate's **Local network API** URL.
6. Sign in with the temporary accounts above.
7. Create/select a job on the interviewer PC.
8. Start the interview on the candidate PC.
9. Confirm the interviewer sees the live session, transcript, camera frame,
   question updates, and integrity events.
10. Approve questions from the interviewer desktop.

## Project structure

```text
app/
  candidate/       Camera, microphone, resume, and integrity capture
  core/            SQLite, settings, models, question bank, LAN API client
  engine/          Transcription, matching, scoring, explainability, fairness
  reports/         Analytics and PDF export
  ui/              Candidate and interviewer desktop windows
api/               Local-network FastAPI service
data/              SQLite database, recordings, profiles, and reports
docs/              Data contracts and module ownership
```

## Data and privacy

- Local-only mode stores data in `data/app.db`.
- Local-network mode stores shared interview state in the SQLite database
  configured on the interviewer PC.
- Camera frames are used for live monitoring and the API keeps only the latest
  frame for an active session.
- Integrity checks are review signals, not automatic proof of misconduct.
- The `tab_switch` integrity tag records interview-window focus loss
  during an active candidate interview.
- The interviewer API uses the temporary development secret shown above.
- Change the secret and demo credentials before production use.
- Keep API secrets and LLM keys out of source control.

## Team documentation

- [Data contracts](docs/INTERFACES.md)
- [Module ownership](docs/OWNERSHIP.md)
