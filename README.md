# InterviewIQ — AI-Powered Interview Assessment System

Academic project (Computer Engineering, group project) exploring **explainability + bias auditing**
combined with **integrity / AI-assisted-answer detection** for automated interview assessment tools.

## Current status: v0.1 — App Shell + Interview Session MVP

What works right now:
- Full desktop app shell (sidebar navigation, 6 sections)
- Live webcam preview on the "New Interview" screen (via OpenCV)
- Question flow (next/previous navigation through question bank)
- Placeholder transcript box (ready to wire up to Whisper)
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
