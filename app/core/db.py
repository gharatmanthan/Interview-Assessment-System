"""
Shared SQLite persistence layer.

Owner: Member C (owns the schema), but every module calls into this —
that's expected and fine. The rule is: add a new save_x()/get_x() function
here if you need one, don't reach into another file's internals.

This is intentionally a thin wrapper (no ORM) so it's easy for all three
of you to read at a glance.
"""
import sqlite3
import json
import os
from pathlib import Path
from dataclasses import asdict

from app.core.remote_api import RemoteApiClient
from app.core.settings_store import load_settings

DB_PATH = Path(__file__).parent.parent.parent / "data" / "app.db"


def _remote_client() -> RemoteApiClient | None:
    settings = load_settings()
    backend_mode = os.environ.get(
        "INTERVIEWIQ_BACKEND_MODE", settings.get("backend_mode", "local")
    ).strip().lower()
    if backend_mode != "remote":
        return None
    base_url = os.environ.get(
        "INTERVIEWIQ_API_URL", settings.get("remote_api_url", "")
    ).strip()
    if not base_url:
        raise RuntimeError("Remote backend is enabled but remote API URL is empty.")
    return RemoteApiClient(base_url)


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        candidate_name TEXT,
        job_title TEXT,
        video_path TEXT,
        audio_path TEXT,
        transcript TEXT,
        started_at TEXT,
        completed_at TEXT,
        status TEXT
    );
    CREATE TABLE IF NOT EXISTS integrity_flags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        flag_type TEXT,
        detail TEXT,
        severity TEXT,
        timestamp TEXT
    );
    CREATE TABLE IF NOT EXISTS competency_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        question_id TEXT,
        category TEXT,
        score REAL,
        confidence REAL
    );
    CREATE TABLE IF NOT EXISTS explanations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        question_id TEXT,
        summary TEXT,
        supporting_phrases TEXT
    );
    CREATE TABLE IF NOT EXISTS fairness_flags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        question_id TEXT,
        score_delta REAL,
        note TEXT
    );
    CREATE TABLE IF NOT EXISTS job_postings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS candidate_accounts (
        candidate_id TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS candidate_profiles (
        candidate_id TEXT PRIMARY KEY,
        resume_path TEXT NOT NULL,
        profile_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (candidate_id) REFERENCES candidate_accounts(candidate_id)
    );
    CREATE TABLE IF NOT EXISTS live_interviews (
        session_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        question TEXT NOT NULL,
        question_index INTEGER NOT NULL DEFAULT 0,
        transcript TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'live',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        pending_question TEXT NOT NULL DEFAULT '',
        pending_status TEXT NOT NULL DEFAULT 'none',
        question_count INTEGER NOT NULL DEFAULT 0,
        interview_context TEXT NOT NULL DEFAULT '[]'
    );
    """)
    conn.execute(
        """INSERT OR IGNORE INTO candidate_accounts
        (candidate_id, password, full_name)
        VALUES (?, ?, ?)""",
        ("candidate01", "interview123", "Demo Candidate"),
    )
    default_jobs = [
        (
            "Python Backend Developer",
            "Build reliable REST APIs and backend services with Python. Work with FastAPI or Django, PostgreSQL, automated tests, Git, and cloud deployment. We are looking for strong problem-solving, clean coding, and API design skills.",
        ),
        (
            "Frontend React Developer",
            "Create accessible, responsive interfaces with React and modern JavaScript or TypeScript. Collaborate with designers and backend engineers, integrate APIs, write maintainable components, and improve user experience through thoughtful testing.",
        ),
    ]
    for title, description in default_jobs:
        conn.execute(
            """INSERT INTO job_postings (title, description, created_at, is_active)
            SELECT ?, ?, datetime('now'), 1
            WHERE NOT EXISTS (SELECT 1 FROM job_postings WHERE title = ?)""",
            (title, description, title),
        )
    conn.commit()
    # Migrate existing databases that lack the new columns
    existing = {row[1] for row in conn.execute("PRAGMA table_info(live_interviews)").fetchall()}
    for col, definition in [
        ("pending_question",  "TEXT NOT NULL DEFAULT ''"),
        ("pending_status",    "TEXT NOT NULL DEFAULT 'none'"),
        ("question_count",    "INTEGER NOT NULL DEFAULT 0"),
        ("interview_context", "TEXT NOT NULL DEFAULT '[]'"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE live_interviews ADD COLUMN {col} {definition}")
    conn.commit()
    conn.close()


# --- writes (called by whoever produces that data type) ---

def save_session(session):
    conn = get_connection()
    d = asdict(session)
    conn.execute(
        """INSERT OR REPLACE INTO sessions
        (session_id, candidate_name, job_title, video_path, audio_path,
         transcript, started_at, completed_at, status)
        VALUES (:session_id, :candidate_name, :job_title, :video_path, :audio_path,
                :transcript, :started_at, :completed_at, :status)""",
        {**d, "started_at": str(d["started_at"]), "completed_at": str(d["completed_at"])},
    )
    conn.commit()
    conn.close()


def authenticate_candidate(candidate_id, password):
    remote = _remote_client()
    if remote:
        return remote.authenticate_candidate(candidate_id, password)
    conn = get_connection()
    account = conn.execute(
        """SELECT candidate_id, full_name FROM candidate_accounts
        WHERE candidate_id = ? AND password = ?""",
        (candidate_id, password),
    ).fetchone()
    conn.close()
    return dict(account) if account else None


def create_candidate_account(candidate_id, password, full_name):
    remote = _remote_client()
    if remote:
        return remote.create_candidate_account(candidate_id, password, full_name)
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO candidate_accounts (candidate_id, password, full_name)
            VALUES (?, ?, ?)""",
            (candidate_id, password, full_name),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()
    return True


def get_candidate_accounts():
    remote = _remote_client()
    if remote:
        return remote.get_candidate_accounts()
    conn = get_connection()
    rows = conn.execute(
        "SELECT candidate_id, full_name FROM candidate_accounts ORDER BY full_name"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_candidate_profile(candidate_id: str, resume_path: str, profile_json: str):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO candidate_profiles
        (candidate_id, resume_path, profile_json, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
        (candidate_id, resume_path, profile_json),
    )
    conn.commit()
    conn.close()


def get_candidate_profile(candidate_id: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM candidate_profiles WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    profile = dict(row)
    profile["profile"] = json.loads(profile.pop("profile_json"))
    return profile


def save_integrity_flag(flag):
    conn = get_connection()
    d = asdict(flag)
    conn.execute(
        """INSERT INTO integrity_flags (session_id, flag_type, detail, severity, timestamp)
        VALUES (:session_id, :flag_type, :detail, :severity, :timestamp)""",
        {**d, "timestamp": str(d["timestamp"])},
    )
    conn.commit()
    conn.close()


def save_competency_score(score):
    conn = get_connection()
    conn.execute(
        """INSERT INTO competency_scores (session_id, question_id, category, score, confidence)
        VALUES (:session_id, :question_id, :category, :score, :confidence)""",
        asdict(score),
    )
    conn.commit()
    conn.close()


def save_explanation(item):
    conn = get_connection()
    d = asdict(item)
    d["supporting_phrases"] = json.dumps(d["supporting_phrases"])
    conn.execute(
        """INSERT INTO explanations (session_id, question_id, summary, supporting_phrases)
        VALUES (:session_id, :question_id, :summary, :supporting_phrases)""",
        d,
    )
    conn.commit()
    conn.close()


def save_fairness_flag(flag):
    conn = get_connection()
    conn.execute(
        """INSERT INTO fairness_flags (session_id, question_id, score_delta, note)
        VALUES (:session_id, :question_id, :score_delta, :note)""",
        asdict(flag),
    )
    conn.commit()
    conn.close()


# --- reads (called by app/reports/ for dashboard + report pages) ---

def get_all_sessions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def start_live_interview(session_id, candidate_id, candidate_name, question, question_index=0):
    remote = _remote_client()
    if remote:
        remote.start_live_interview(
            session_id, candidate_id, candidate_name, question, question_index
        )
        return
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO live_interviews
        (session_id, candidate_id, candidate_name, question, question_index,
         transcript, status, updated_at)
        VALUES (?, ?, ?, ?, ?, '', 'live', CURRENT_TIMESTAMP)""",
        (session_id, candidate_id, candidate_name, question, question_index),
    )
    conn.commit()
    conn.close()


def update_live_interview(session_id, **fields):
    allowed = {
        "question", "question_index", "transcript", "status",
        "pending_question", "pending_status", "question_count", "interview_context",
    }
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
        return
    remote = _remote_client()
    if remote:
        remote.update_live_interview(session_id, **changes)
        return
    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values()) + [session_id]
    conn = get_connection()
    conn.execute(
        f"UPDATE live_interviews SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
        values,
    )
    conn.commit()
    conn.close()


def save_pending_question(session_id: str, question: str) -> None:
    """Save an AI-generated question as pending interviewer approval."""
    update_live_interview(session_id, pending_question=question, pending_status="pending")


def approve_pending_question(session_id: str, question: str | None = None) -> None:
    """Approve (and optionally overwrite) the pending question — makes it visible to the candidate."""
    remote = _remote_client()
    if remote:
        remote.approve_pending_question(session_id, question)
        return
    conn = get_connection()
    row = conn.execute(
        "SELECT pending_question, question_index, question_count, interview_context, transcript FROM live_interviews WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    if not row:
        return
    approved_q = question if question is not None else row["pending_question"]
    new_index = row["question_index"] + 1
    new_count = row["question_count"] + 1
    update_live_interview(
        session_id,
        question=approved_q,
        question_index=new_index,
        question_count=new_count,
        transcript="",
        pending_question="",
        pending_status="approved",
    )


def get_pending_question(session_id: str) -> dict | None:
    """Return the pending question info for a session, or None if not pending."""
    conn = get_connection()
    row = conn.execute(
        "SELECT pending_question, pending_status, question_count FROM live_interviews WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_live_interviews():
    remote = _remote_client()
    if remote:
        return remote.list_live_interviews()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM live_interviews WHERE status = 'live' ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_live_interview(session_id):
    remote = _remote_client()
    if remote:
        return remote.get_live_interview(session_id)
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM live_interviews WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_job_posting(title: str, description: str):
    remote = _remote_client()
    if remote:
        return remote.save_job_posting(title, description)
    conn = get_connection()
    conn.execute(
        "INSERT INTO job_postings (title, description, created_at, is_active) VALUES (?, ?, datetime('now'), 1)",
        (title, description),
    )
    conn.commit()
    conn.close()


def get_active_job_postings():
    remote = _remote_client()
    if remote:
        return remote.get_active_job_postings()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, description, created_at FROM job_postings WHERE is_active = 1 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def deactivate_job_posting(job_id: int):
    conn = get_connection()
    conn.execute("UPDATE job_postings SET is_active = 0 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


def get_session_scores(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM competency_scores WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_flags(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM integrity_flags WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_explanations(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM explanations WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    explanations = []
    for row in rows:
        item = dict(row)
        item["supporting_phrases"] = json.loads(item["supporting_phrases"] or "[]")
        explanations.append(item)
    return explanations


def get_all_integrity_flags():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM integrity_flags ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_fairness_flags():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM fairness_flags ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]
