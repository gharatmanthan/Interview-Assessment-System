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
import uuid
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent.parent / "data" / "app.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Referential integrity + WAL for the screening/outbox workflow. Existing
    # tables predate FK declarations so this is additive, not breaking.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
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
    CREATE TABLE IF NOT EXISTS scheduled_interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id TEXT UNIQUE NOT NULL,
        job_id TEXT NOT NULL,
        scheduled_at TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL DEFAULT 45,
        gcal_event_id TEXT,
        status TEXT NOT NULL DEFAULT 'scheduled',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS applications (
        application_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NOT NULL DEFAULT '',
        resume_path TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'apply_portal',
        status TEXT NOT NULL DEFAULT 'received',
        screening_status TEXT NOT NULL DEFAULT 'queued',
        candidate_id TEXT,
        submitted_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_email_job ON applications(email, job_id);
    CREATE TABLE IF NOT EXISTS screening_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        last_error TEXT
    );
    CREATE TABLE IF NOT EXISTS screening_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT NOT NULL UNIQUE,
        ats_score REAL,
        skills_score REAL,
        experience_score REAL,
        semantic_score REAL,
        education_score REAL,
        keyword_score REAL,
        matched_skills TEXT NOT NULL DEFAULT '[]',
        missing_skills TEXT NOT NULL DEFAULT '[]',
        hard_requirements_passed INTEGER NOT NULL DEFAULT 0,
        hard_requirement_failures TEXT NOT NULL DEFAULT '[]',
        decision TEXT NOT NULL DEFAULT 'rejected',
        decision_reason TEXT NOT NULL DEFAULT '',
        threshold_used REAL,
        scoring_method TEXT NOT NULL DEFAULT '',
        matcher_method TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        completed_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT,
        candidate_id TEXT,
        job_id TEXT NOT NULL,
        notification_type TEXT NOT NULL,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        sent_at TEXT,
        last_error TEXT,
        UNIQUE(application_id, notification_type, recipient)
    );
    CREATE INDEX IF NOT EXISTS idx_outbox_status ON notification_outbox(status);
    CREATE TABLE IF NOT EXISTS interview_invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id TEXT NOT NULL,
        job_id TEXT NOT NULL DEFAULT '',
        application_id TEXT,
        token TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_invites_candidate ON interview_invites(candidate_id);
    CREATE TABLE IF NOT EXISTS application_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT NOT NULL,
        event TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_app_events_application ON application_events(application_id);
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
    _migrate_screening_columns()
    _migrate_candidates_application_link()
    _migrate_screening_results_threshold()
    _migrate_application_events()
    _migrate_job_postings_empty_ids()
    _migrate_candidates_unique_email_job()
    _migrate_score_tables_unique()


def _migrate_candidates_unique_email_job():
    """Enforce one candidate per (email, job_id).

    A race between the background screening worker and the email-intake's
    synchronous screen could previously mint two candidate rows for the same
    applicant. Dedupes any rows that already slipped in (keeps the earliest),
    then adds a unique index so the race can never recur.
    """
    conn = get_connection()
    conn.execute(
        """DELETE FROM candidates WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM candidates GROUP BY email, job_id
        )"""
    )
    conn.commit()
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_email_job "
        "ON candidates(email, job_id)"
    )
    conn.commit()
    conn.close()


def _migrate_score_tables_unique():
    """Enforce one score/explanation/fairness row per (session_id, question_id).

    A double-submit — the candidate's /submit-answer racing a recruiter's
    /scoring/run, or a client retry — previously created duplicate rows that
    skew per-question reports. Dedupes existing rows (keeps the latest by id)
    then pins the constraint so the race can never recur. The save_* writers
    are switched to UPSERT (INSERT ... ON CONFLICT DO UPDATE), so re-scoring
    the same question overwrites rather than duplicates.
    """
    conn = get_connection()
    for table in ("competency_scores", "explanations", "fairness_flags"):
        conn.execute(
            f"DELETE FROM {table} WHERE id NOT IN ("
            f"  SELECT MAX(id) FROM {table} GROUP BY session_id, question_id)"
        )
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table.rstrip('s')}_session_question "
            f"ON {table}(session_id, question_id)"
        )
    conn.commit()
    conn.close()


def generate_job_id() -> str:
    """Canonical job identifier, generated server-side (never trusted from the
    client). The job is the storage/authorization root, so the backend must
    own its id before any application link can be built from it."""
    return uuid.uuid4().hex


def _migrate_job_postings_empty_ids():
    """Repair rows created when the backend trusted a client-supplied (blank)
    job_id. Assigns a fresh server-generated id and propagates it to every
    table that references job_postings.job_id so linked data survives."""
    conn = get_connection()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()}
    empty_rows = conn.execute(
        "SELECT job_id FROM job_postings WHERE job_id IS NULL OR TRIM(job_id) = ''"
    ).fetchall()
    for (old_id,) in empty_rows:
        new_id = generate_job_id()
        conn.execute("UPDATE job_postings SET job_id = ? WHERE job_id = ?", (new_id, old_id))
        for table in (
            "applications", "candidates", "sessions", "notification_outbox",
            "interview_invites", "scheduled_interviews", "email_poll_log",
            "processed_emails",
        ):
            if table in tables:
                conn.execute(f"UPDATE {table} SET job_id = ? WHERE job_id = ?", (new_id, old_id))
    conn.commit()
    conn.close()


def _migrate_screening_columns():
    """Adds the application-first screening config to an existing
    job_postings table (screening_enabled, auto_invite_enabled,
    minimum_experience_years, required_education, screening_weights,
    created_by).
    """
    conn = get_connection()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    if "created_by" not in cols:
        conn.execute("ALTER TABLE job_postings ADD COLUMN created_by TEXT NOT NULL DEFAULT 'recruiter'")
    for col, col_type, default in [
        ("screening_enabled", "INTEGER", "1"),
        ("auto_invite_enabled", "INTEGER", "1"),
        ("required_education", "TEXT", "''"),
        ("screening_weights", "TEXT", "'{\"skills\": 40, \"experience\": 20, \"semantic\": 20, \"education\": 10, \"keyword\": 10}'"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE job_postings ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
    if "minimum_experience_years" not in cols:
        # nullable on purpose (SQLite cannot add a NOT NULL column with a NULL default)
        conn.execute("ALTER TABLE job_postings ADD COLUMN minimum_experience_years REAL")
    conn.commit()
    conn.close()


def _migrate_screening_results_threshold():
    """Adds the auditable threshold_used column to screening_results so the
    threshold applied to a decision is persisted at screening time."""
    conn = get_connection()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(screening_results)").fetchall()}
    if "threshold_used" not in cols:
        conn.execute("ALTER TABLE screening_results ADD COLUMN threshold_used REAL")
    conn.commit()
    conn.close()


def _migrate_application_events():
    """Ensures the application_events audit-trail table exists on upgraded DBs."""
    conn = get_connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS application_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT NOT NULL,
        event TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_app_events_application ON application_events(application_id)"
    )
    conn.commit()
    conn.close()


def _migrate_candidates_application_link():
    """Adds application_id to candidates for the application->candidate link."""
    conn = get_connection()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    if "application_id" not in cols:
        conn.execute("ALTER TABLE candidates ADD COLUMN application_id TEXT")
    conn.commit()
    conn.close()


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
    """Insert or update a candidate.

    Uses an upsert keyed on candidate_id (NOT INSERT OR REPLACE): replace
    semantics would delete a conflicting row the moment two candidates share
    (email, job_id) — unique by index — and strand invites/outbox rows and
    scheduled interviews that reference the old id.
    """
    conn = get_connection()
    d = asdict(candidate)
    try:
        conn.execute(
            """INSERT INTO candidates
            (candidate_id, job_id, name, email, invite_code, status, session_id, invited_at,
             resume_path, resume_skills, experience_years, match_score, matched_skills, missing_skills,
             source, screening_status, invite_email_sent, application_id)
            VALUES (:candidate_id, :job_id, :name, :email, :invite_code, :status, :session_id, :invited_at,
                    :resume_path, :resume_skills, :experience_years, :match_score, :matched_skills, :missing_skills,
                    :source, :screening_status, :invite_email_sent, :application_id)
            ON CONFLICT(candidate_id) DO UPDATE SET
                job_id = excluded.job_id,
                name = excluded.name,
                email = excluded.email,
                invite_code = excluded.invite_code,
                status = excluded.status,
                session_id = excluded.session_id,
                invited_at = excluded.invited_at,
                resume_path = excluded.resume_path,
                resume_skills = excluded.resume_skills,
                experience_years = excluded.experience_years,
                match_score = excluded.match_score,
                matched_skills = excluded.matched_skills,
                missing_skills = excluded.missing_skills,
                source = excluded.source,
                screening_status = excluded.screening_status,
                invite_email_sent = excluded.invite_email_sent,
                application_id = excluded.application_id""",
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
    finally:
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


def get_candidate_by_email_job(email, job_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM candidates WHERE email = ? AND job_id = ?", (email, job_id)
    ).fetchone()
    conn.close()
    return _decode_candidate_row(dict(row)) if row else None


def get_candidate(candidate_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()
    conn.close()
    return _decode_candidate_row(dict(row)) if row else None


def get_candidates_for_job(job_id):
    """Shortlisted candidates for one job. Eligibility is enforced in SQL:
    manual/override candidates (no linked application) always count; screened
    candidates count only while their latest screening decision is 'passed' —
    a later re-screen that flips the decision to rejected hides them again.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.* FROM candidates c
        LEFT JOIN screening_results r ON c.application_id = r.application_id
        WHERE c.job_id = ?
          AND (c.application_id IS NULL OR r.decision = 'passed')
        ORDER BY c.invited_at DESC""",
        (job_id,),
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
         screening_threshold, application_gmail_label,
         screening_enabled, auto_invite_enabled, minimum_experience_years, required_education,
         screening_weights, created_by)
        VALUES (:job_id, :title, :description, :required_skills, :experience_level, :department,
                :num_rounds, :time_limit_seconds, :adaptive_difficulty, :competency_weights, :created_at,
                :screening_threshold, :application_gmail_label,
                :screening_enabled, :auto_invite_enabled, :minimum_experience_years, :required_education,
                :screening_weights, :created_by)""",
        {
            **d,
            "required_skills": json.dumps(d["required_skills"]),
            "adaptive_difficulty": int(d["adaptive_difficulty"]),
            "competency_weights": json.dumps(d["competency_weights"]),
            "created_at": str(d["created_at"]),
            "screening_enabled": int(d["screening_enabled"]),
            "auto_invite_enabled": int(d["auto_invite_enabled"]),
            "screening_weights": json.dumps(d["screening_weights"]),
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
        VALUES (:session_id, :question_id, :category, :score, :confidence)
        ON CONFLICT(session_id, question_id) DO UPDATE SET
            category = excluded.category,
            score = excluded.score,
            confidence = excluded.confidence""",
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
        VALUES (:session_id, :question_id, :summary, :supporting_phrases)
        ON CONFLICT(session_id, question_id) DO UPDATE SET
            summary = excluded.summary,
            supporting_phrases = excluded.supporting_phrases""",
        d,
    )
    conn.commit()
    conn.close()


def save_fairness_flag(flag):
    conn = get_connection()
    conn.execute(
        """INSERT INTO fairness_flags (session_id, question_id, score_delta, note)
        VALUES (:session_id, :question_id, :score_delta, :note)
        ON CONFLICT(session_id, question_id) DO UPDATE SET
            score_delta = excluded.score_delta,
            note = excluded.note""",
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


def _decode_job_row(d: dict) -> dict:
    """Decode JSON-string / boolean columns on a job_postings row."""
    d["required_skills"] = json.loads(d["required_skills"] or "[]")
    d["competency_weights"] = json.loads(d["competency_weights"] or "{}")
    d["adaptive_difficulty"] = bool(d["adaptive_difficulty"])
    if "screening_weights" in d:
        try:
            d["screening_weights"] = json.loads(d.get("screening_weights") or "null") or {}
        except json.JSONDecodeError:
            d["screening_weights"] = {}
    for key in ("screening_enabled", "auto_invite_enabled", "is_active"):
        if key in d:
            d[key] = bool(d[key])
    return d


def get_job_posting(job_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM job_postings WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _decode_job_row(dict(row))


def get_all_job_postings():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM job_postings ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_decode_job_row(dict(r)) for r in rows]


def get_owned_jobs(username):
    """Jobs owned by a recruiter (authorization root)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE created_by = ? ORDER BY created_at DESC",
        (username,),
    ).fetchall()
    conn.close()
    return [_decode_job_row(dict(r)) for r in rows]


def job_owned_by(job_id, username):
    job = get_job_posting(job_id)
    return bool(job and job.get("created_by") == username)


def get_active_job_postings():
    """Active postings only — powers the candidate's pre-interview job view."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE is_active = 1 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_decode_job_row(dict(r)) for r in rows]


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


# --- scheduled interviews (auto-scheduling from recruiter availability) ---

def _utcnow():
    """Separate helper so tests can pin the current time."""
    return datetime.utcnow()


STALE_PROCESSING_TIMEOUT_MINUTES = 15


def requeue_stale_screening_jobs(timeout_minutes: int = STALE_PROCESSING_TIMEOUT_MINUTES) -> int:
    """Recover jobs left 'processing' by a crashed worker: re-queue those past
    the timeout so the next claim re-runs them. Jobs already at the attempt cap
    are marked failed instead of retried forever. Returns the number re-queued."""
    from app.screening.service import MAX_SCREENING_ATTEMPTS
    conn = get_connection()
    cutoff = str(_utcnow() - timedelta(minutes=timeout_minutes))
    rows = conn.execute(
        "SELECT application_id, attempts FROM screening_jobs "
        "WHERE status = 'processing' AND started_at IS NOT NULL AND started_at < ?",
        (cutoff,),
    ).fetchall()
    requeued = 0
    for row in rows:
        attempts = (row["attempts"] or 0) + 1
        if attempts >= MAX_SCREENING_ATTEMPTS:
            conn.execute(
                "UPDATE screening_jobs SET status = 'failed', attempts = ?, "
                "completed_at = ?, last_error = ? WHERE application_id = ?",
                (attempts, str(_utcnow()), "max attempts reached after repeated crashes",
                 row["application_id"]),
            )
        else:
            conn.execute(
                "UPDATE screening_jobs SET status = 'queued', attempts = ?, "
                "started_at = NULL, last_error = ? WHERE application_id = ?",
                (attempts, "re-queued after worker crash", row["application_id"]),
            )
            requeued += 1
    conn.commit()
    conn.close()
    return requeued


def save_scheduled_interview(candidate_id, job_id, scheduled_at, duration_minutes,
                             gcal_event_id=None, status="scheduled"):
    """Insert or replace a scheduled interview for a candidate."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO scheduled_interviews
        (candidate_id, job_id, scheduled_at, duration_minutes, gcal_event_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (candidate_id, job_id, str(scheduled_at), int(duration_minutes),
         gcal_event_id, status, str(_utcnow())),
    )
    conn.commit()
    conn.close()


def get_scheduled_interview(candidate_id):
    """Return the scheduled interview for a candidate, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM scheduled_interviews WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_scheduled_interviews():
    """All scheduled interviews joined with candidate + job details, ordered by date."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*, c.name AS candidate_name, c.email AS candidate_email,
               c.status AS candidate_status, j.title AS job_title
        FROM scheduled_interviews s
        LEFT JOIN candidates c ON s.candidate_id = c.candidate_id
        LEFT JOIN job_postings j ON s.job_id = j.job_id
        ORDER BY s.scheduled_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_upcoming_scheduled_interviews():
    """All scheduled interviews starting at/after now, for overlap avoidance."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM scheduled_interviews
        WHERE scheduled_at >= ?
        ORDER BY scheduled_at ASC
    """, (str(_utcnow()),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_scheduled_interview(candidate_id):
    """Remove a scheduled interview (e.g. on reschedule or cancel)."""
    conn = get_connection()
    conn.execute("DELETE FROM scheduled_interviews WHERE candidate_id = ?", (candidate_id,))
    conn.commit()
    conn.close()


# --- applications (candidate-first lifecycle) ---

def create_application(app):
    """Insert an application. Raises sqlite3.IntegrityError on duplicate
    (email, job_id) — the port into duplicate detection.
    """
    conn = get_connection()
    conn.execute(
        """INSERT INTO applications
        (application_id, job_id, full_name, email, phone, resume_path, source, status,
         screening_status, candidate_id, submitted_at, updated_at)
        VALUES (:application_id, :job_id, :full_name, :email, :phone, :resume_path, :source, :status,
                :screening_status, :candidate_id, :submitted_at, :updated_at)""",
        {
            "application_id": app.application_id,
            "job_id": app.job_id,
            "full_name": app.full_name,
            "email": app.email,
            "phone": app.phone,
            "resume_path": app.resume_path,
            "source": app.source,
            "status": app.status,
            "screening_status": app.screening_status,
            "candidate_id": app.candidate_id,
            "submitted_at": str(app.submitted_at),
            "updated_at": str(app.updated_at),
        },
    )
    conn.commit()
    conn.close()


def _decode_application_row(d):
    d["submitted_at"] = d["submitted_at"]
    d["updated_at"] = d["updated_at"]
    return d


def get_application(application_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM applications WHERE application_id = ?", (application_id,)
    ).fetchone()
    conn.close()
    return _decode_application_row(dict(row)) if row else None


def get_application_by_email_job(email, job_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM applications WHERE email = ? AND job_id = ?",
        (email, job_id),
    ).fetchone()
    conn.close()
    return _decode_application_row(dict(row)) if row else None


def get_applications_for_job(job_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM applications WHERE job_id = ? ORDER BY submitted_at DESC",
        (job_id,),
    ).fetchall()
    conn.close()
    return [_decode_application_row(dict(r)) for r in rows]


def get_applications_by_candidate(candidate_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM applications WHERE candidate_id = ? ORDER BY submitted_at DESC",
        (candidate_id,),
    ).fetchall()
    conn.close()
    return [_decode_application_row(dict(r)) for r in rows]


def get_all_applications():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM applications ORDER BY submitted_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_application_status(application_id, status, updated_at=None):
    conn = get_connection()
    conn.execute(
        "UPDATE applications SET status = ?, updated_at = ? WHERE application_id = ?",
        (status, str(updated_at or datetime.utcnow()), application_id),
    )
    conn.commit()
    conn.close()


def update_application_screening_status(application_id, screening_status):
    conn = get_connection()
    conn.execute(
        "UPDATE applications SET screening_status = ?, updated_at = ? WHERE application_id = ?",
        (screening_status, str(datetime.utcnow()), application_id),
    )
    conn.commit()
    conn.close()


def update_application_candidate(application_id, candidate_id):
    conn = get_connection()
    conn.execute(
        "UPDATE applications SET candidate_id = ?, updated_at = ? WHERE application_id = ?",
        (candidate_id, str(datetime.utcnow()), application_id),
    )
    conn.commit()
    conn.close()


def delete_application(application_id):
    conn = get_connection()
    conn.execute("DELETE FROM applications WHERE application_id = ?", (application_id,))
    conn.commit()
    conn.close()


def get_owned_applications(username):
    """Applications whose job is owned by the recruiter (authorization root)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT ap.* FROM applications ap
        JOIN job_postings j ON ap.job_id = j.job_id
        WHERE j.created_by = ?
        ORDER BY ap.submitted_at DESC""",
        (username,),
    ).fetchall()
    conn.close()
    return [_decode_application_row(dict(r)) for r in rows]


# --- screening jobs (async queue) ---

def create_screening_job(application_id):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO screening_jobs (application_id, status, attempts, created_at)
        VALUES (?, 'queued', 0, ?)""",
        (application_id, str(_utcnow())),
    )
    conn.commit()
    conn.close()
    return get_screening_job(application_id)


def requeue_screening(application_id):
    """Reset an existing screening job to queued for an explicit re-screen
    (e.g. after a threshold change). Idempotent: re-running keeps one job row."""
    create_screening_job(application_id)  # INSERT OR IGNORE guarantees a row exists
    conn = get_connection()
    conn.execute(
        """UPDATE screening_jobs SET status = 'queued', attempts = 0, last_error = NULL,
           started_at = NULL, completed_at = NULL WHERE application_id = ?""",
        (application_id,),
    )
    conn.commit()
    conn.close()
    return get_screening_job(application_id)


def insert_application_event(application_id, event, detail=""):
    """Record one audit-trail event for an application (application_received,
    screening_started, screening_completed, screening_passed/rejected/manual_review,
    candidate_created, invite_created, screening_requeued, screening_failed)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO application_events (application_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
        (application_id, event, detail[:1000], str(_utcnow())),
    )
    conn.commit()
    conn.close()


def get_application_events(application_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT event, detail, created_at FROM application_events WHERE application_id = ? ORDER BY id ASC",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_screening_job(application_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM screening_jobs WHERE application_id = ?", (application_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def claim_next_screening_job():
    """Atomically claim one screening job for processing. Stale 'processing'
    jobs (crashed workers) are re-queued for recovery first."""
    requeue_stale_screening_jobs()
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM screening_jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    job_id = row["id"]
    cur = conn.execute(
        """UPDATE screening_jobs SET status = 'processing', started_at = ?, last_error = NULL
        WHERE id = ? AND status = 'queued'""",
        (str(_utcnow()), job_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return None
    conn = get_connection()
    claimed = conn.execute(
        "SELECT * FROM screening_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    return dict(claimed) if claimed else None


def get_due_screening_jobs():
    """Queued jobs for observability/dashboards."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM screening_jobs WHERE status IN ('queued', 'processing') ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fail_screening_job(application_id, error):
    """Increment attempts; mark failed after MAX_SCREENING_ATTEMPTS."""
    from app.screening.service import MAX_SCREENING_ATTEMPTS
    conn = get_connection()
    row = conn.execute(
        "SELECT attempts FROM screening_jobs WHERE application_id = ?", (application_id,)
    ).fetchone()
    attempts = (row["attempts"] or 0) + 1
    status = "failed" if attempts >= MAX_SCREENING_ATTEMPTS else "queued"
    conn.execute(
        "UPDATE screening_jobs SET attempts = ?, status = ?, last_error = ?, completed_at = ? WHERE application_id = ?",
        (attempts, status, error[:500] if error else None, str(_utcnow()), application_id),
    )
    conn.commit()
    conn.close()
    return status


def complete_screening_job(application_id):
    conn = get_connection()
    conn.execute(
        "UPDATE screening_jobs SET status = 'completed', completed_at = ? WHERE application_id = ?",
        (str(_utcnow()), application_id),
    )
    conn.commit()
    conn.close()


# --- screening results (explainable, idempotent per application) ---

def save_screening_result(result):
    conn = get_connection()
    conn.execute(
        """INSERT INTO screening_results
        (application_id, ats_score, skills_score, experience_score, semantic_score,
         education_score, keyword_score, matched_skills, missing_skills,
         hard_requirements_passed, hard_requirement_failures, decision, decision_reason,
         threshold_used, scoring_method, matcher_method, confidence, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(application_id) DO UPDATE SET
            ats_score=excluded.ats_score, skills_score=excluded.skills_score,
            experience_score=excluded.experience_score, semantic_score=excluded.semantic_score,
            education_score=excluded.education_score, keyword_score=excluded.keyword_score,
            matched_skills=excluded.matched_skills, missing_skills=excluded.missing_skills,
            hard_requirements_passed=excluded.hard_requirements_passed,
            hard_requirement_failures=excluded.hard_requirement_failures,
            decision=excluded.decision, decision_reason=excluded.decision_reason,
            threshold_used=excluded.threshold_used,
            scoring_method=excluded.scoring_method, matcher_method=excluded.matcher_method,
            confidence=excluded.confidence, completed_at=excluded.completed_at""",
        (
            result.application_id,
            result.ats_score,
            result.skills_score,
            result.experience_score,
            result.semantic_score,
            result.education_score,
            result.keyword_score,
            json.dumps(result.matched_skills),
            json.dumps(result.missing_skills),
            int(result.hard_requirements_passed),
            json.dumps(result.hard_requirement_failures),
            result.decision,
            result.decision_reason,
            result.threshold_used,
            result.scoring_method,
            result.matcher_method,
            float(result.confidence or 0.0),
            str(_utcnow()),
            str(_utcnow()),
        ),
    )
    conn.commit()
    conn.close()


def _decode_screening_result_row(d):
    d["matched_skills"] = json.loads(d["matched_skills"] or "[]")
    d["missing_skills"] = json.loads(d["missing_skills"] or "[]")
    d["hard_requirement_failures"] = json.loads(d["hard_requirement_failures"] or "[]")
    d["hard_requirements_passed"] = bool(d["hard_requirements_passed"])
    d["threshold_used"] = d.get("threshold_used")
    d["confidence"] = float(d["confidence"] or 0.0)
    return d


def get_screening_result(application_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM screening_results WHERE application_id = ?", (application_id,)
    ).fetchone()
    conn.close()
    return _decode_screening_result_row(dict(row)) if row else None


def get_screening_results_for_job(job_id):
    """All screening results for a job's applications, joined for the dashboard."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.*, ap.full_name, ap.email, ap.phone, ap.status AS application_status,
                  ap.source, ap.submitted_at
        FROM screening_results r
        JOIN applications ap ON r.application_id = ap.application_id
        WHERE ap.job_id = ?
        ORDER BY ap.submitted_at DESC""",
        (job_id,),
    ).fetchall()
    conn.close()
    return [_decode_screening_result_row(dict(r)) for r in rows]


# --- notification outbox (email side-effect queue) ---

def enqueue_notification(application_id, job_id, notification_type, recipient, subject, body,
                         candidate_id=None):
    """Queue a notification. INSERT OR IGNORE keeps re-enqueue idempotent
    (UNIQUE application_id, notification_type, recipient).
    """
    conn = get_connection()
    cur = conn.execute(
        """INSERT OR IGNORE INTO notification_outbox
        (application_id, candidate_id, job_id, notification_type, recipient, subject, body,
         status, attempts, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)""",
        (application_id, candidate_id, job_id, notification_type, recipient, subject, body,
         str(_utcnow())),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def requeue_resend_notification(candidate_id, application_id, job_id, notification_type,
                                recipient, subject, body):
    """Replace every earlier outbox message of this type for a candidate with a
    single fresh pending one. Used by Resend Invite: the prior pending/sent/
    failed row is removed first, so the UNIQUE(application_id, type, recipient)
    guard cannot swallow the replacement. Returns True when a new message is
    actually queued.
    """
    conn = get_connection()
    conn.execute(
        "DELETE FROM notification_outbox WHERE candidate_id = ? AND notification_type = ?",
        (candidate_id, notification_type),
    )
    cur = conn.execute(
        """INSERT OR IGNORE INTO notification_outbox
        (application_id, candidate_id, job_id, notification_type, recipient, subject, body,
         status, attempts, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)""",
        (application_id, candidate_id, job_id, notification_type, recipient, subject, body,
         str(_utcnow())),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_pending_notifications(limit=20):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notification_outbox WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def claim_pending_notification(limit=1):
    """Atomically claim the next-pending outbox message by flipping it to
    'sending'. Guards against two workers both grabbing the same message (which,
    combined with a crash between 'Gmail send' and 'mark sent', would otherwise
    cause duplicate emails on retry). Returns the claimed row or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM notification_outbox WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    cur = conn.execute(
        "UPDATE notification_outbox SET status = 'sending' WHERE id = ? AND status = 'pending'",
        (row["id"],),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return None
    conn = get_connection()
    claimed = conn.execute(
        "SELECT * FROM notification_outbox WHERE id = ?", (row["id"],)
    ).fetchone()
    conn.close()
    return dict(claimed) if claimed else None


STALE_SENDING_TIMEOUT_MINUTES = 15


def reclaim_stale_sending_notifications(timeout_minutes: int = STALE_SENDING_TIMEOUT_MINUTES) -> int:
    """Recover outbox messages stuck in 'sending' after a worker crashed between
    sending to Gmail and marking 'sent'. Re-queueing risks a duplicate email only
    in the rare crash window, but leaving them stuck risks a never-delivered
    invite — so we reclaim for retry, capped by the attempt limit. Returns the
    number reclaimed."""
    from app.screening.email_worker import MAX_NOTIFICATION_ATTEMPTS
    conn = get_connection()
    cutoff = str(_utcnow() - timedelta(minutes=timeout_minutes))
    rows = conn.execute(
        "SELECT id, attempts FROM notification_outbox "
        "WHERE status = 'sending' AND created_at < ?",
        (cutoff,),
    ).fetchall()
    reclaimed = 0
    for row in rows:
        attempts = (row["attempts"] or 0) + 1
        if attempts >= MAX_NOTIFICATION_ATTEMPTS:
            conn.execute(
                "UPDATE notification_outbox SET status = 'failed', attempts = ?, "
                "last_error = ?, sent_at = ? WHERE id = ?",
                (attempts, "max attempts reached after repeated crashes", str(_utcnow()), row["id"]),
            )
        else:
            conn.execute(
                "UPDATE notification_outbox SET status = 'pending', attempts = ?, "
                "last_error = ? WHERE id = ?",
                (attempts, "reclaimed after worker crash", row["id"]),
            )
            reclaimed += 1
    conn.commit()
    conn.close()
    return reclaimed


def get_notifications_for_application(application_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notification_outbox WHERE application_id = ? ORDER BY id ASC",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notification_sent(outbox_id):
    conn = get_connection()
    conn.execute(
        "UPDATE notification_outbox SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ?",
        (str(_utcnow()), outbox_id),
    )
    conn.commit()
    conn.close()


def mark_notification_failed(outbox_id, error):
    """Increment attempts; stay pending until MAX_NOTIFICATION_ATTEMPTS, then failed."""
    from app.screening.email_worker import MAX_NOTIFICATION_ATTEMPTS
    conn = get_connection()
    row = conn.execute(
        "SELECT attempts FROM notification_outbox WHERE id = ?", (outbox_id,)
    ).fetchone()
    attempts = (row["attempts"] or 0) + 1
    status = "failed" if attempts >= MAX_NOTIFICATION_ATTEMPTS else "pending"
    conn.execute(
        "UPDATE notification_outbox SET attempts = ?, status = ?, last_error = ? WHERE id = ?",
        (attempts, status, (error or "")[:500], outbox_id),
    )
    conn.commit()
    conn.close()
    return status


# --- interview invites (secure, expirable, one-time) ---

def create_interview_invite(invite):
    conn = get_connection()
    conn.execute(
        """INSERT INTO interview_invites
        (candidate_id, job_id, application_id, token, status, created_at, expires_at, consumed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (invite.candidate_id, invite.job_id, invite.application_id, invite.token,
         invite.status, str(invite.created_at), str(invite.expires_at),
         str(invite.consumed_at) if invite.consumed_at else None),
    )
    conn.commit()
    conn.close()


def get_interview_invite_by_token(token):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM interview_invites WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_interview_invites_for_candidate(candidate_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM interview_invites WHERE candidate_id = ? ORDER BY id DESC",
        (candidate_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def consume_interview_invite(invite_id):
    conn = get_connection()
    conn.execute(
        "UPDATE interview_invites SET status = 'consumed', consumed_at = ? WHERE id = ?",
        (str(_utcnow()), invite_id),
    )
    conn.commit()
    conn.close()


def clear_interview_invites(candidate_id):
    """Drop all prior invite rows for a candidate. Called on Resend Invite so a
    stale expired/consumed row can no longer block validate-code — the fresh
    invite row is the only one that counts."""
    conn = get_connection()
    conn.execute("DELETE FROM interview_invites WHERE candidate_id = ?", (candidate_id,))
    conn.commit()
    conn.close()


def expire_stale_invites():
    """Passively expire invites whose expires_at has passed (idempotent)."""
    conn = get_connection()
    conn.execute(
        "UPDATE interview_invites SET status = 'expired' WHERE status = 'active' AND expires_at <= ?",
        (str(_utcnow()),),
    )
    conn.commit()
    conn.close()


# --- ownership-scoped reads (authorization root = job created_by) ---

def _owned_job_ids(conn, username):
    return [r["job_id"] for r in conn.execute(
        "SELECT job_id FROM job_postings WHERE created_by = ?", (username,)
    ).fetchall()]


def get_owned_candidates(username):
    """Candidates whose job posting is owned by the recruiter, limited to the
    current shortlist: manual/override candidates always show; screened
    candidates show only while their latest decision is 'passed'."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.* FROM candidates c
        LEFT JOIN screening_results r ON c.application_id = r.application_id
        WHERE c.job_id IN (SELECT job_id FROM job_postings WHERE created_by = ?)
          AND (c.application_id IS NULL OR r.decision = 'passed')
        ORDER BY c.invited_at DESC""",
        (username,),
    ).fetchall()
    conn.close()
    return [_decode_candidate_row(dict(r)) for r in rows]


def get_job_pipeline_stats(username):
    """Per-job shortlisting funnel counts for the recruiter's own job postings."""
    conn = get_connection()
    jobs = conn.execute(
        "SELECT job_id, title FROM job_postings WHERE created_by = ? ORDER BY created_at DESC",
        (username,),
    ).fetchall()
    out = []
    for j in jobs:
        job_id = j["job_id"]

        def _count(sql):
            return conn.execute(sql, (job_id,)).fetchone()[0] or 0

        out.append(
            {
                "job_id": job_id,
                "title": j["title"],
                "applications": _count(
                    "SELECT COUNT(*) FROM applications WHERE job_id = ?"
                ),
                "screening_pending": _count(
                    "SELECT COUNT(*) FROM applications WHERE job_id = ? AND screening_status IN ('queued','processing')"
                ),
                "shortlisted": _count(
                    "SELECT COUNT(*) FROM candidates WHERE job_id = ?"
                ),
                "rejected": _count(
                    "SELECT COUNT(*) FROM applications WHERE job_id = ? AND status = 'rejected'"
                ),
                "manual_review": _count(
                    "SELECT COUNT(*) FROM applications WHERE job_id = ? AND status = 'manual_review'"
                ),
                "invites_sent": _count(
                    "SELECT COUNT(*) FROM notification_outbox WHERE job_id = ? AND notification_type = 'interview_invite' AND status = 'sent'"
                ),
                "interviews_completed": _count(
                    """SELECT COUNT(*) FROM sessions s
                    JOIN candidates c ON c.session_id = s.session_id
                    WHERE c.job_id = ? AND s.status = 'completed'"""
                ),
                "email_failures": _count(
                    "SELECT COUNT(*) FROM notification_outbox WHERE job_id = ? AND status = 'failed'"
                ),
            }
        )
    conn.close()
    return out


def get_owned_candidate(username, candidate_id):
    """Single candidate, ownership-checked."""
    conn = get_connection()
    row = conn.execute(
        """SELECT c.* FROM candidates c
        WHERE c.candidate_id = ? AND c.job_id IN
            (SELECT job_id FROM job_postings WHERE created_by = ?)""",
        (candidate_id, username),
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for key in ("resume_skills", "matched_skills", "missing_skills"):
        d[key] = json.loads(d[key] or "[]")
    d["invite_email_sent"] = bool(d["invite_email_sent"])
    return d


def get_owned_sessions(username):
    """Sessions belonging to candidates of the recruiter's jobs."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.* FROM sessions s
        JOIN candidates c ON c.session_id = s.session_id
        WHERE c.job_id IN (SELECT job_id FROM job_postings WHERE created_by = ?)
        ORDER BY s.started_at DESC""",
        (username,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_owned_session(username, session_id):
    conn = get_connection()
    row = conn.execute(
        """SELECT s.* FROM sessions s
        JOIN candidates c ON c.session_id = s.session_id
        WHERE s.session_id = ? AND c.job_id IN
            (SELECT job_id FROM job_postings WHERE created_by = ?)""",
        (session_id, username),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_owned_scheduled_interviews(username):
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, c.name AS candidate_name, c.email AS candidate_email,
                c.status AS candidate_status, j.title AS job_title
        FROM scheduled_interviews s
        LEFT JOIN candidates c ON s.candidate_id = c.candidate_id
        LEFT JOIN job_postings j ON s.job_id = j.job_id
        WHERE j.created_by = ?
        ORDER BY s.scheduled_at ASC""",
        (username,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
