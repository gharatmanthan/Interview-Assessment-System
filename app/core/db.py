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
import hashlib
import secrets
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
        invited_at TEXT,
        resume_path TEXT,
        resume_skills TEXT,
        experience_years REAL,
        match_score REAL,
        matched_skills TEXT,
        missing_skills TEXT
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
    CREATE TABLE IF NOT EXISTS candidate_accounts (
        candidate_id TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS live_interviews (
        session_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        question TEXT NOT NULL,
        question_index INTEGER NOT NULL DEFAULT 0,
        transcript TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'live',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS processed_emails (
        message_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        candidate_id TEXT,
        processed_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS email_poll_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT NOT NULL,
        job_id TEXT NOT NULL,
        job_title TEXT NOT NULL,
        total_checked INTEGER NOT NULL DEFAULT 0,
        invited INTEGER NOT NULL DEFAULT 0,
        below_threshold INTEGER NOT NULL DEFAULT 0,
        skipped INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0,
        mode TEXT NOT NULL DEFAULT 'auto'
    );
    """)
    conn.execute(
        """INSERT OR IGNORE INTO candidate_accounts
        (candidate_id, password_hash, full_name)
        VALUES (?, ?, ?)""",
        ("candidate01", f"interviewiq${_hash_password('interview123', 'interviewiq')}", "Demo Candidate"),
    )
    conn.commit()
    conn.close()
    _migrate_candidates_resume_columns()
    _migrate_job_postings_active_column()
    _migrate_email_intake_columns()


def _hash_password(password: str, salt: str) -> str:
    """Same salted SHA-256 scheme as app/core/auth.py (kept local to avoid a
    circular import — auth.py imports this module)."""
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _migrate_job_postings_active_column():
    """Adds the is_active flag to an existing job_postings table from before
    the candidate-facing active-postings view existed. Covers upgrades from
    an older DB file, same as _migrate_candidates_resume_columns().
    """
    conn = get_connection()
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    if "is_active" not in existing:
        conn.execute("ALTER TABLE job_postings ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    conn.commit()
    conn.close()


def _migrate_candidates_resume_columns():
    """Adds resume columns to an existing candidates table from before this
    feature existed. CREATE TABLE IF NOT EXISTS alone won't add columns to
    an already-created table, so this covers upgrades from an older DB file.
    """
    conn = get_connection()
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    new_columns = {
        "resume_path": "TEXT",
        "resume_skills": "TEXT",
        "experience_years": "REAL",
        "match_score": "REAL",
        "matched_skills": "TEXT",
        "missing_skills": "TEXT",
    }
    for col, col_type in new_columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()


def _migrate_email_intake_columns():
    """Adds source, screening_status, invite_email_sent to candidates and
    screening_threshold, application_gmail_label to job_postings for the
    email-to-invite pipeline feature.
    """
    conn = get_connection()
    cand_cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    for col, col_type, default in [
        ("source", "TEXT", "'manual'"),
        ("screening_status", "TEXT", "'pending'"),
        ("invite_email_sent", "INTEGER", "0"),
    ]:
        if col not in cand_cols:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
    job_cols = {row["name"] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    for col, col_type, default in [
        ("screening_threshold", "REAL", "60.0"),
        ("application_gmail_label", "TEXT", "''"),
    ]:
        if col not in job_cols:
            conn.execute(f"ALTER TABLE job_postings ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
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


def save_candidate_account(candidate_id, password, full_name):
    """Create or update a candidate sign-in account. The invite-code flow
    stays the primary credential; this backs the optional candidate login.
    """
    salt = secrets.token_hex(8)
    stored_hash = f"{salt}${_hash_password(password, salt)}"
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO candidate_accounts (candidate_id, password_hash, full_name)
        VALUES (?, ?, ?)""",
        (candidate_id, stored_hash, full_name),
    )
    conn.commit()
    conn.close()


def authenticate_candidate(candidate_id, password):
    """Returns dict(candidate_id, full_name) on success, else None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT candidate_id, password_hash, full_name FROM candidate_accounts WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        salt, hashed = row["password_hash"].split("$", 1)
    except ValueError:
        return None
    if _hash_password(password, salt) != hashed:
        return None
    return {"candidate_id": row["candidate_id"], "full_name": row["full_name"]}


def _decode_candidate_row(d: dict) -> dict:
    """Decode JSON-string columns back into Python lists for a candidate row."""
    for key in ("resume_skills", "matched_skills", "missing_skills"):
        raw = d.get(key)
        d[key] = json.loads(raw) if raw else []
    if "invite_email_sent" in d:
        d["invite_email_sent"] = bool(d["invite_email_sent"])
    return d


def save_candidate(candidate):
    conn = get_connection()
    d = asdict(candidate)
    conn.execute(
        """INSERT OR REPLACE INTO candidates
        (candidate_id, job_id, name, email, invite_code, status, session_id, invited_at,
         resume_path, resume_skills, experience_years, match_score, matched_skills, missing_skills,
         source, screening_status, invite_email_sent)
        VALUES (:candidate_id, :job_id, :name, :email, :invite_code, :status, :session_id, :invited_at,
                :resume_path, :resume_skills, :experience_years, :match_score, :matched_skills, :missing_skills,
                :source, :screening_status, :invite_email_sent)""",
        {
            **d,
            "invited_at": str(d["invited_at"]),
            "resume_skills": json.dumps(d["resume_skills"]),
            "matched_skills": json.dumps(d["matched_skills"]),
            "missing_skills": json.dumps(d["missing_skills"]),
            "invite_email_sent": int(d["invite_email_sent"]),
        },
    )
    conn.commit()
    conn.close()


def save_candidate_resume(candidate_id, resume_path, resume_skills,
                           experience_years, match_score, matched_skills, missing_skills):
    """Called after app/engine/resume_parser.py + jd_matcher.py have run
    on a candidate's uploaded resume, to persist the parsed + matched result.
    """
    conn = get_connection()
    conn.execute(
        """UPDATE candidates SET
            resume_path = ?, resume_skills = ?, experience_years = ?,
            match_score = ?, matched_skills = ?, missing_skills = ?
        WHERE candidate_id = ?""",
        (
            resume_path, json.dumps(resume_skills), experience_years,
            match_score, json.dumps(matched_skills), json.dumps(missing_skills),
            candidate_id,
        ),
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
    return _decode_candidate_row(dict(row)) if row else None


def get_candidates_for_job(job_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM candidates WHERE job_id = ? ORDER BY invited_at DESC", (job_id,)
    ).fetchall()
    conn.close()
    return [_decode_candidate_row(dict(r)) for r in rows]


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
    return [_decode_candidate_row(dict(r)) for r in rows]


def save_job_posting(job):
    conn = get_connection()
    d = asdict(job)
    conn.execute(
        """INSERT OR REPLACE INTO job_postings
        (job_id, title, description, required_skills, experience_level, department,
         num_rounds, time_limit_seconds, adaptive_difficulty, competency_weights, created_at,
         screening_threshold, application_gmail_label)
        VALUES (:job_id, :title, :description, :required_skills, :experience_level, :department,
                :num_rounds, :time_limit_seconds, :adaptive_difficulty, :competency_weights, :created_at,
                :screening_threshold, :application_gmail_label)""",
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


def update_session(session_id, **fields):
    """Partial update of an existing session row (e.g. transcript as it streams)."""
    allowed = {"transcript", "status", "completed_at", "video_path", "audio_path"}
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
        return
    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values()) + [session_id]
    conn = get_connection()
    conn.execute(f"UPDATE sessions SET {assignments} WHERE session_id = ?", values)
    conn.commit()
    conn.close()


def start_live_interview(session_id, candidate_id, candidate_name, question, question_index=0):
    """Registers a running interview so the recruiter's Live Monitor can
    watch it and push follow-up questions back to the candidate's screen.
    """
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
    allowed = {"question", "question_index", "transcript", "status"}
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
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


def get_live_interviews():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM live_interviews WHERE status = 'live' ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_live_interview(session_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM live_interviews WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


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


def get_job_posting(job_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM job_postings WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["required_skills"] = json.loads(d["required_skills"] or "[]")
    d["competency_weights"] = json.loads(d["competency_weights"] or "{}")
    d["adaptive_difficulty"] = bool(d["adaptive_difficulty"])
    return d


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


def get_active_job_postings():
    """Active postings only — powers the candidate's pre-interview job view."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE is_active = 1 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["required_skills"] = json.loads(d["required_skills"] or "[]")
        d["competency_weights"] = json.loads(d["competency_weights"] or "{}")
        d["adaptive_difficulty"] = bool(d["adaptive_difficulty"])
        out.append(d)
    return out


def set_job_posting_active(job_id, is_active):
    conn = get_connection()
    conn.execute(
        "UPDATE job_postings SET is_active = ? WHERE job_id = ?",
        (1 if is_active else 0, job_id),
    )
    conn.commit()
    conn.close()


def get_session(session_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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


# --- processed emails (email intake pipeline) ---

def save_processed_email(processed_email):
    """Record that a Gmail message has been processed, preventing re-processing."""
    conn = get_connection()
    d = asdict(processed_email)
    conn.execute(
        """INSERT OR IGNORE INTO processed_emails (message_id, job_id, candidate_id, processed_at)
        VALUES (:message_id, :job_id, :candidate_id, :processed_at)""",
        {**d, "processed_at": str(d["processed_at"])},
    )
    conn.commit()
    conn.close()


def is_email_processed(message_id):
    """Check whether a Gmail message has already been processed."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    return row is not None


def update_job_screening_threshold(job_id, screening_threshold):
    """Update the screening threshold for a specific job posting."""
    conn = get_connection()
    conn.execute(
        "UPDATE job_postings SET screening_threshold = ? WHERE job_id = ?",
        (screening_threshold, job_id),
    )
    conn.commit()
    conn.close()


def update_candidate_invite_email_sent(candidate_id, sent):
    """Mark whether the invite email was successfully sent."""
    conn = get_connection()
    conn.execute(
        "UPDATE candidates SET invite_email_sent = ? WHERE candidate_id = ?",
        (int(sent), candidate_id),
    )
    conn.commit()
    conn.close()


def get_jobs_with_gmail_labels():
    """Return all job postings that have a non-empty Gmail label configured."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE application_gmail_label != '' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["required_skills"] = json.loads(d["required_skills"] or "[]")
        d["competency_weights"] = json.loads(d["competency_weights"] or "{}")
        d["adaptive_difficulty"] = bool(d["adaptive_difficulty"])
        out.append(d)
    return out


# --- email poll log (background automation tracking) ---

def save_poll_log(job_id, job_title, total, invited, below_threshold, skipped, failed, mode="auto"):
    """Record one background poll run for auditing."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO email_poll_log
        (run_at, job_id, job_title, total_checked, invited, below_threshold, skipped, failed, mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(datetime.utcnow()), job_id, job_title, total, invited, below_threshold, skipped, failed, mode),
    )
    conn.commit()
    conn.close()


def get_poll_logs(limit=50):
    """Return the most recent poll run log entries."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM email_poll_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
