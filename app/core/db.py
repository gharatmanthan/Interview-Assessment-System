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
from pathlib import Path
from dataclasses import asdict

DB_PATH = Path(__file__).parent.parent.parent / "data" / "app.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS recruiter_users (
        username TEXT PRIMARY KEY,
        password_hash TEXT,
        full_name TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id TEXT PRIMARY KEY,
        job_id TEXT,
        name TEXT,
        email TEXT,
        invite_code TEXT UNIQUE,
        status TEXT,
        session_id TEXT,
        invited_at TEXT
    );
    CREATE TABLE IF NOT EXISTS job_postings (
        job_id TEXT PRIMARY KEY,
        title TEXT,
        description TEXT,
        required_skills TEXT,
        experience_level TEXT,
        department TEXT,
        num_rounds INTEGER,
        time_limit_seconds INTEGER,
        adaptive_difficulty INTEGER,
        competency_weights TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        candidate_name TEXT,
        job_title TEXT,
        job_id TEXT,
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
    """)
    conn.commit()
    conn.close()


# --- writes (called by whoever produces that data type) ---

def save_recruiter_user(user):
    conn = get_connection()
    d = asdict(user)
    conn.execute(
        """INSERT OR REPLACE INTO recruiter_users (username, password_hash, full_name, created_at)
        VALUES (:username, :password_hash, :full_name, :created_at)""",
        {**d, "created_at": str(d["created_at"])},
    )
    conn.commit()
    conn.close()


def get_recruiter_user(username):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM recruiter_users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_candidate(candidate):
    conn = get_connection()
    d = asdict(candidate)
    conn.execute(
        """INSERT OR REPLACE INTO candidates
        (candidate_id, job_id, name, email, invite_code, status, session_id, invited_at)
        VALUES (:candidate_id, :job_id, :name, :email, :invite_code, :status, :session_id, :invited_at)""",
        {**d, "invited_at": str(d["invited_at"])},
    )
    conn.commit()
    conn.close()


def update_candidate_status(candidate_id, status, session_id=None):
    conn = get_connection()
    if session_id is not None:
        conn.execute(
            "UPDATE candidates SET status = ?, session_id = ? WHERE candidate_id = ?",
            (status, session_id, candidate_id),
        )
    else:
        conn.execute(
            "UPDATE candidates SET status = ? WHERE candidate_id = ?",
            (status, candidate_id),
        )
    conn.commit()
    conn.close()


def regenerate_invite_code(candidate_id, new_code):
    conn = get_connection()
    conn.execute(
        "UPDATE candidates SET invite_code = ?, status = 'invited' WHERE candidate_id = ?",
        (new_code, candidate_id),
    )
    conn.commit()
    conn.close()


def delete_candidate(candidate_id):
    conn = get_connection()
    conn.execute("DELETE FROM candidates WHERE candidate_id = ?", (candidate_id,))
    conn.commit()
    conn.close()


def get_candidate_by_invite_code(invite_code):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM candidates WHERE invite_code = ?", (invite_code,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_candidates_for_job(job_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM candidates WHERE job_id = ? ORDER BY invited_at DESC", (job_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_candidates():
    """All invited candidates across every job posting, with job title
    joined in — powers the unified candidate-status tracker on the dashboard.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, j.title AS job_title
        FROM candidates c
        LEFT JOIN job_postings j ON c.job_id = j.job_id
        ORDER BY c.invited_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_job_posting(job):
    conn = get_connection()
    d = asdict(job)
    conn.execute(
        """INSERT OR REPLACE INTO job_postings
        (job_id, title, description, required_skills, experience_level, department,
         num_rounds, time_limit_seconds, adaptive_difficulty, competency_weights, created_at)
        VALUES (:job_id, :title, :description, :required_skills, :experience_level, :department,
                :num_rounds, :time_limit_seconds, :adaptive_difficulty, :competency_weights, :created_at)""",
        {
            **d,
            "required_skills": json.dumps(d["required_skills"]),
            "adaptive_difficulty": int(d["adaptive_difficulty"]),
            "competency_weights": json.dumps(d["competency_weights"]),
            "created_at": str(d["created_at"]),
        },
    )
    conn.commit()
    conn.close()


def save_session(session):
    conn = get_connection()
    d = asdict(session)
    conn.execute(
        """INSERT OR REPLACE INTO sessions
        (session_id, candidate_name, job_title, job_id, video_path, audio_path,
         transcript, started_at, completed_at, status)
        VALUES (:session_id, :candidate_name, :job_title, :job_id, :video_path, :audio_path,
                :transcript, :started_at, :completed_at, :status)""",
        {**d, "started_at": str(d["started_at"]), "completed_at": str(d["completed_at"])},
    )
    conn.commit()
    conn.close()


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

def delete_job_posting(job_id):
    conn = get_connection()
    conn.execute("DELETE FROM job_postings WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()


def get_all_job_postings():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM job_postings ORDER BY created_at DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["required_skills"] = json.loads(d["required_skills"] or "[]")
        d["competency_weights"] = json.loads(d["competency_weights"] or "{}")
        d["adaptive_difficulty"] = bool(d["adaptive_difficulty"])
        out.append(d)
    return out


def get_all_sessions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_scores(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM competency_scores WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_explanations(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM explanations WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["supporting_phrases"] = json.loads(d["supporting_phrases"] or "[]")
        out.append(d)
    return out


def get_session_flags(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM integrity_flags WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_integrity_flags():
    """All integrity flags across every session, newest first — powers the
    Integrity Log page. Joined with session info so the page can show
    which candidate/job each flag belongs to.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT f.*, s.candidate_name, s.job_title
        FROM integrity_flags f
        LEFT JOIN sessions s ON f.session_id = s.session_id
        ORDER BY f.timestamp DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_fairness_flags():
    """All fairness/bias flags across every session — powers the Bias Audit page."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT f.*, s.candidate_name, s.job_title
        FROM fairness_flags f
        LEFT JOIN sessions s ON f.session_id = s.session_id
        ORDER BY f.id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
