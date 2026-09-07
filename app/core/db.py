"""
Shared persistence layer — supports both SQLite (dev/local) and PostgreSQL (production).

Owner: Member C (owns the schema), but every module calls into this —
that's expected and fine. The rule is: add a new save_x()/get_x() function
here if you need one, don't reach into another file's internals.

This is intentionally a thin wrapper (no ORM) so it's easy for all three
of you to read at a glance.
"""
import json
import hashlib
import secrets
import uuid
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Optional

from app.core.database import get_db, get_database_engine, init_db as _init_db
from app.core.paths import get_db_path

DB_PATH = get_db_path()


def get_connection():
    """Backward-compatible function — returns a new connection each time.
    
    This is kept for any code that directly calls get_connection()
    but all new code should use the context manager from app.core.database
    """
    engine = get_database_engine()
    if engine.is_postgresql:
        return engine._get_pg_connection()
    else:
        return engine.new_sqlite_connection()


def close_connection():
    """Close the persistent connection (for testing)."""
    engine = get_database_engine()
    engine.close()


def init_db():
    """Initialize the database using the new abstraction layer."""
    _init_db()
    # Run additional migrations using the engine's cached connection
    # to avoid SQLite locking issues with multiple connections
    engine = get_database_engine()
    if engine.is_postgresql:
        # For PostgreSQL, use a new connection from the pool
        conn = engine._get_pg_connection()
        try:
            _migrate_candidates_resume_columns(conn)
            _migrate_job_postings_active_column(conn)
            _migrate_email_intake_columns(conn)
            _migrate_screening_columns(conn)
            _migrate_candidates_application_link(conn)
            _migrate_screening_results_threshold(conn)
            _migrate_application_events(conn)
            _migrate_job_postings_empty_ids(conn)
            _migrate_candidates_unique_email_job(conn)
            _migrate_score_tables_unique(conn)
            _migrate_integrity_flags_unique(conn)
            _migrate_linkedin_job_columns(conn)
            _migrate_linkedin_tables(conn)
            _migrate_question_transcripts(conn)
            _migrate_session_questions(conn)
            _migrate_live_state(conn)
            _migrate_routing_fields(conn)
            conn.commit()
        finally:
            engine._return_pg_connection(conn)
    else:
        # For SQLite, use the cached connection that was used for initial schema creation
        conn = engine._get_sqlite_connection()
        try:
            _migrate_candidates_resume_columns(conn)
            _migrate_job_postings_active_column(conn)
            _migrate_email_intake_columns(conn)
            _migrate_screening_columns(conn)
            _migrate_candidates_application_link(conn)
            _migrate_screening_results_threshold(conn)
            _migrate_application_events(conn)
            _migrate_job_postings_empty_ids(conn)
            _migrate_candidates_unique_email_job(conn)
            _migrate_score_tables_unique(conn)
            _migrate_integrity_flags_unique(conn)
            _migrate_linkedin_job_columns(conn)
            _migrate_linkedin_tables(conn)
            _migrate_question_transcripts(conn)
            _migrate_session_questions(conn)
            _migrate_live_state(conn)
            _migrate_routing_fields(conn)
            conn.commit()
        finally:
            # Don't close the cached connection - it's reused for regular operations
            pass


def _migrate_question_transcripts(conn):
    """Per-question transcript storage for STT integration (Phase 2A).

    sessions.transcript is a single TEXT column that would overwrite across
    questions.  This table stores one row per (session_id, question_id) so
    each answer's transcript is preserved independently.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS question_transcripts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        question_id TEXT NOT NULL,
        transcript TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(session_id, question_id)
    )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qtranscripts_session "
        "ON question_transcripts(session_id)"
    )


def _migrate_session_questions(conn):
    """Locked question set per interview session (Phase 2B).

    Each row is one question in the session's immutable question set.
    Once generated/selected and persisted, the candidate receives exactly
    these questions in question_index order — no regeneration on refresh.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS session_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        question_index INTEGER NOT NULL,
        question_id TEXT NOT NULL,
        question_text TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        competency TEXT NOT NULL DEFAULT '',
        difficulty TEXT NOT NULL DEFAULT 'medium',
        source TEXT NOT NULL DEFAULT 'bank',
        created_at TEXT NOT NULL,
        UNIQUE(session_id, question_index),
        UNIQUE(session_id, question_id)
    )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sq_session "
        "ON session_questions(session_id)"
    )


def _migrate_live_state(conn):
    """Phase 3A: live-interview state on the existing session tables.

    Minimal additive schema — no redundant interview table. Adds:
      * session_questions.asked        — whether that question has been asked
      * sessions.live_question_id      — the currently-active question ('' = none)
    Reuses sessions.status ('live') for the in-progress live state.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(session_questions)").fetchall()}
    if "asked" not in cols:
        conn.execute("ALTER TABLE session_questions ADD COLUMN asked INTEGER NOT NULL DEFAULT 0")
    s_cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "live_question_id" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN live_question_id TEXT NOT NULL DEFAULT ''")


def _migrate_routing_fields(conn):
    """Interview-routing/cohort fields for the hybrid mode-allocation workflow.

    Job-scope strategy (the recruiter confirms one strategy per cohort):
      * interview_strategy   — AUTO | MODE_1_ONLY | MODE_2_THEN_MODE_1
      * recommended_strategy — the computed recommendation (AUTO only)
      * strategy_confirmed   — 0 until the recruiter explicitly confirms
      * strategy_confirmed_at
      * cohort_finalized_at  — set once the job's screening cohort is final

    Candidate-scope progression (kept on candidates to avoid a redundant row):
      * interview_mode   — MODE_1 | MODE_2 ('' until assigned)
      * mode_status      — the mode progression state machine
      * mode2_score      — aggregated Mode 2 overall score (for ranking)
      * overall_score    — same numeric value, kept for ranking/compare
      * rank             — within-job rank (1 is best)
      * ranked_at / promoted_at
      * mode_assignment_source — SYSTEM | RECRUITER
    """

    jcols = {row["name"] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    for col, col_type, default in [
        ("interview_strategy", "TEXT", "'AUTO'"),
        ("recommended_strategy", "TEXT", "''"),
        ("strategy_confirmed", "INTEGER", "0"),
        ("strategy_confirmed_at", "TEXT", "''"),
        ("cohort_finalized_at", "TEXT", "''"),
    ]:
        if col not in jcols:
            conn.execute(f"ALTER TABLE job_postings ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")

    ccols = {row["name"] for row in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    for col, col_type in [
        ("interview_mode", "TEXT"),
        ("mode_status", "TEXT"),
        ("mode2_score", "REAL"),
        ("overall_score", "REAL"),
        ("rank", "INTEGER"),
        ("ranked_at", "TEXT"),
        ("promoted_at", "TEXT"),
        ("mode_assignment_source", "TEXT"),
    ]:
        if col not in ccols:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {col} {col_type}")


def _migrate_candidates_unique_email_job(conn):
    """Enforce one candidate per (email, job_id).

    A race between the background screening worker and the email-intake's
    synchronous screen could previously mint two candidate rows for the same
    applicant. Dedupes any rows that already slipped in (keeps the earliest),
    then adds a unique index so the race can never recur.
    """
    conn.execute(
        """DELETE FROM candidates WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM candidates GROUP BY email, job_id
        )"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_email_job "
        "ON candidates(email, job_id)"
    )


def _migrate_score_tables_unique(conn):
    """Enforce one score/explanation/fairness row per (session_id, question_id).

    A double-submit — the candidate's /submit-answer racing a recruiter's
    /scoring/run, or a client retry — previously created duplicate rows that
    skew per-question reports. Dedupes existing rows (keeps the latest by id)
    then pins the constraint so the race can never recur. The save_* writers
    are switched to UPSERT (INSERT ... ON CONFLICT DO UPDATE), so re-scoring
    the same question overwrites rather than duplicates.
    """
    for table in ("competency_scores", "explanations", "fairness_flags"):
        conn.execute(
            f"DELETE FROM {table} WHERE id NOT IN ("
            f"  SELECT MAX(id) FROM {table} GROUP BY session_id, question_id)"
        )
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table.rstrip('s')}_session_question "
            f"ON {table}(session_id, question_id)"
        )


def _migrate_integrity_flags_unique(conn):
    """Deduplicate integrity flags on (session_id, flag_type, detail) and add unique index.
    
    Server-side polling (run_checks every 5s) and client retries were producing
    massive duplicate flags. This migration deduplicates existing rows and adds
    a unique constraint so duplicates can never recur.
    """
    conn.execute(
        """DELETE FROM integrity_flags WHERE id NOT IN (
            SELECT MAX(id) FROM integrity_flags 
            GROUP BY session_id, flag_type, detail
        )"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_integrity_flag_session_type_detail "
        "ON integrity_flags(session_id, flag_type, detail)"
    )


def _migrate_linkedin_job_columns(conn):
    """Adds the DB-authoritative LinkedIn publication columns to job_postings.

    A job is never published twice: the status column is the single source of
    truth, mutated only through row-locked transitions (see
    try_claim_linkedin_publish). Columns are added idempotently per the
    standard in-project migration pattern.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    if "linkedin_post_status" not in cols:
        conn.execute(
            "ALTER TABLE job_postings ADD COLUMN "
            "linkedin_post_status TEXT NOT NULL DEFAULT 'NOT_POSTED'"
        )
    for col in (
        "linkedin_post_id",
        "linkedin_post_url",
        "linkedin_posted_at",
        "linkedin_author_urn",
        "linkedin_last_error",
        "linkedin_claim_started_at",
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE job_postings ADD COLUMN {col} TEXT")


def _migrate_linkedin_tables(conn):
    """Adds per-recruiter LinkedIn OAuth connection + one-time OAuth state tables.

    Unlike the machine-wide Gmail/Calendar settings.json tokens, LinkedIn is
    stored per recruiter so Recruiter A can never see or reuse Recruiter B's
    connection. OAuth state rows are single-use, TTL-bounded CSRF protection.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS linkedin_connections (
            recruiter_username TEXT PRIMARY KEY,
            linkedin_member_id TEXT NOT NULL,
            member_name TEXT NOT NULL DEFAULT '',
            member_email TEXT NOT NULL DEFAULT '',
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL DEFAULT '',
            token_expires_at TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT '',
            connected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS linkedin_oauth_states (
            state TEXT PRIMARY KEY,
            recruiter_username TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        );
        """
    )


def generate_job_id() -> str:
    """Canonical job identifier, generated server-side (never trusted from the
    client). The job is the storage/authorization root, so the backend must
    own its id before any application link can be built from it."""
    return uuid.uuid4().hex


def _migrate_job_postings_empty_ids(conn):
    """Repair rows created when the backend trusted a client-supplied (blank)
    job_id. Assigns a fresh server-generated id and propagates it to every
    table that references job_postings.job_id so linked data survives."""
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


def _migrate_screening_columns(conn):
    """Adds the application-first screening config to an existing
    job_postings table (screening_enabled, auto_invite_enabled,
    minimum_experience_years, required_education, screening_weights,
    created_by).
    """
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


def _migrate_screening_results_threshold(conn):
    """Adds the auditable threshold_used column to screening_results so the
    threshold applied to a decision is persisted at screening time."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(screening_results)").fetchall()}
    if "threshold_used" not in cols:
        conn.execute("ALTER TABLE screening_results ADD COLUMN threshold_used REAL")


def _migrate_application_events(conn):
    """Ensures the application_events audit-trail table exists on upgraded DBs."""
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


def _migrate_candidates_application_link(conn):
    """Adds application_id to candidates for the application->candidate link."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    if "application_id" not in cols:
        conn.execute("ALTER TABLE candidates ADD COLUMN application_id TEXT")


def _hash_password(password: str, salt: str) -> str:
    """Same salted SHA-256 scheme as app/core/auth.py (kept local to avoid a
    circular import — auth.py imports this module)."""
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _migrate_job_postings_active_column(conn):
    """Adds the is_active flag to an existing job_postings table from before
    the candidate-facing active-postings view existed. Covers upgrades from
    an older DB file, same as _migrate_candidates_resume_columns().
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
    if "is_active" not in existing:
        conn.execute("ALTER TABLE job_postings ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")


def _migrate_candidates_resume_columns(conn):
    """Adds resume columns to an existing candidates table from before this
    feature existed. CREATE TABLE IF NOT EXISTS alone won't add columns to
    an already-created table, so this covers upgrades from an older DB file.
    """
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


def _migrate_email_intake_columns(conn):
    """Adds source, screening_status, invite_email_sent to candidates and
    screening_threshold, application_gmail_label to job_postings for the
    email-to-invite pipeline feature.
    """
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
             source, screening_status, invite_email_sent, application_id,
             interview_mode, mode_status, mode2_score, overall_score, rank, ranked_at, promoted_at,
             mode_assignment_source)
            VALUES (:candidate_id, :job_id, :name, :email, :invite_code, :status, :session_id, :invited_at,
                    :resume_path, :resume_skills, :experience_years, :match_score, :matched_skills, :missing_skills,
                    :source, :screening_status, :invite_email_sent, :application_id,
                    :interview_mode, :mode_status, :mode2_score, :overall_score, :rank, :ranked_at, :promoted_at,
                    :mode_assignment_source)
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
                application_id = excluded.application_id,
                interview_mode = excluded.interview_mode,
                mode_status = excluded.mode_status,
                mode2_score = excluded.mode2_score,
                overall_score = excluded.overall_score,
                rank = excluded.rank,
                ranked_at = excluded.ranked_at,
                promoted_at = excluded.promoted_at,
                mode_assignment_source = excluded.mode_assignment_source""",
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


def update_candidate_screening_status(candidate_id, screening_status):
    conn = get_connection()
    conn.execute(
        "UPDATE candidates SET screening_status = ? WHERE candidate_id = ?",
        (screening_status, candidate_id),
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
    # INSERT OR REPLACE drops any column not in the SQL, so a job edit (PUT)
    # would otherwise wipe DB-authoritative LinkedIn publish state. Preserve it
    # from the existing row — REPLACE is only used here for upsert semantics.
    existing = get_job_posting(job.job_id) or {}
    linkedin_state = {
        "linkedin_post_status": existing.get("linkedin_post_status", "NOT_POSTED"),
        "linkedin_post_id": existing.get("linkedin_post_id"),
        "linkedin_post_url": existing.get("linkedin_post_url"),
        "linkedin_posted_at": existing.get("linkedin_posted_at"),
        "linkedin_author_urn": existing.get("linkedin_author_urn"),
        "linkedin_last_error": existing.get("linkedin_last_error"),
        "linkedin_claim_started_at": existing.get("linkedin_claim_started_at"),
    }
    # Routing/cohort state is DB-authoritative once confirmed — never clobber it
    # via a PUT/INSERT OR REPLACE. Only the dedicated confirm endpoint flips it.
    routing_state = {
        "interview_strategy": existing.get("interview_strategy", "AUTO"),
        "recommended_strategy": existing.get("recommended_strategy", ""),
        "strategy_confirmed": existing.get("strategy_confirmed", 0),
        "strategy_confirmed_at": existing.get("strategy_confirmed_at", ""),
        "cohort_finalized_at": existing.get("cohort_finalized_at", ""),
    }
    conn = get_connection()
    d = asdict(job)
    conn.execute(
        """INSERT OR REPLACE INTO job_postings
        (job_id, title, description, required_skills, experience_level, department,
         num_rounds, time_limit_seconds, adaptive_difficulty, competency_weights, created_at,
         screening_threshold, application_gmail_label,
         screening_enabled, auto_invite_enabled, minimum_experience_years, required_education,
         screening_weights, created_by,
         linkedin_post_status, linkedin_post_id, linkedin_post_url,
         linkedin_posted_at, linkedin_author_urn, linkedin_last_error,
         linkedin_claim_started_at,
         interview_strategy, recommended_strategy, strategy_confirmed,
         strategy_confirmed_at, cohort_finalized_at)
        VALUES (:job_id, :title, :description, :required_skills, :experience_level, :department,
                :num_rounds, :time_limit_seconds, :adaptive_difficulty, :competency_weights, :created_at,
                :screening_threshold, :application_gmail_label,
                :screening_enabled, :auto_invite_enabled, :minimum_experience_years, :required_education,
                :screening_weights, :created_by,
                :linkedin_post_status, :linkedin_post_id, :linkedin_post_url,
                :linkedin_posted_at, :linkedin_author_urn, :linkedin_last_error,
                :linkedin_claim_started_at,
                :interview_strategy, :recommended_strategy, :strategy_confirmed,
                :strategy_confirmed_at, :cohort_finalized_at)""",
        {
            **d,
            "required_skills": json.dumps(d["required_skills"]),
            "adaptive_difficulty": int(d["adaptive_difficulty"]),
            "competency_weights": json.dumps(d["competency_weights"]),
            "created_at": str(d["created_at"]),
            "screening_enabled": int(d["screening_enabled"]),
            "auto_invite_enabled": int(d["auto_invite_enabled"]),
            "screening_weights": json.dumps(d["screening_weights"]),
            **linkedin_state,
            **routing_state,
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
         transcript, started_at, completed_at, status, live_question_id)
        VALUES (:session_id, :candidate_name, :job_title, :job_id, :video_path, :audio_path,
                :transcript, :started_at, :completed_at, :status, :live_question_id)""",
        {**d, "started_at": str(d["started_at"]), "completed_at": str(d["completed_at"])},
    )
    conn.commit()
    conn.close()


def update_session(session_id, **fields):
    """Partial update of an existing session row (e.g. transcript as it streams)."""
    allowed = {"transcript", "status", "completed_at", "video_path", "audio_path", "live_question_id"}
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
        return
    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values()) + [session_id]
    conn = get_connection()
    conn.execute(f"UPDATE sessions SET {assignments} WHERE session_id = ?", values)
    conn.commit()
    conn.close()


class SessionResolutionError(Exception):
    """Raised by resolve_or_create_session when a session cannot be created or
    resolved for the requested candidate (missing candidate, job mismatch, or a
    pre-existing session bound to a different job child)."""


def resolve_or_create_session(candidate_id, job_id, candidate_name, job_title):
    """Return the single authoritative session_id for a candidate interview.

    The session id is derived server-side and never trusted from the client, so
    the recruiter and the candidate always converge on the SAME session (the one
    stored in candidates.session_id). Idempotent and race-safe: concurrent calls
    for the same candidate cannot produce two sessions because the read-check +
    insert + link happen inside one BEGIN IMMEDIATE write transaction.

    Raises SessionResolutionError on candidate-not-found or candidate/job
    mismatch. Returns the authoritative session_id otherwise.
    """
    candidate = get_candidate(candidate_id)
    if not candidate:
        raise SessionResolutionError("candidate not found")
    if candidate.get("job_id") != job_id:
        raise SessionResolutionError("candidate/job mismatch")

    existing = candidate.get("session_id")
    if existing:
        # If the stored link points at a real session, it is the authoritative
        # session regardless of anything the client claimed. Job context has
        # already been verified against candidate.job_id above. A dangling link
        # (session_id set but no sessions row — e.g. legacy seeded data) is
        # treated as empty and repaired below.
        if get_session(existing):
            return existing

    sid = str(uuid.uuid4())
    now = str(datetime.now().isoformat())
    conn = get_connection()
    try:
        # Serialize writers; re-read the candidate's link under the lock so two
        # near-simultaneous starts can never both create a fresh session. Only
        # reuse a stored id that actually points at an existing session row.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT session_id FROM candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        if row and row["session_id"] and get_session(row["session_id"]):
            conn.execute("COMMIT")
            return row["session_id"]
        conn.execute(
            """INSERT OR REPLACE INTO sessions
            (session_id, candidate_name, job_title, job_id, video_path, audio_path,
             transcript, started_at, completed_at, status)
            VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, 'in_progress')""",
            (sid, candidate_name, job_title, job_id, now),
        )
        conn.execute(
            "UPDATE candidates SET session_id = ? WHERE candidate_id = ?",
            (sid, candidate_id),
        )
        conn.execute("COMMIT")
        return sid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_session_for_candidate(candidate_id):
    """Resolve candidate_id -> candidates.session_id -> sessions row, or None."""
    candidate = get_candidate(candidate_id)
    if not candidate or not candidate.get("session_id"):
        return None
    return get_session(candidate["session_id"])


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
        VALUES (:session_id, :flag_type, :detail, :severity, :timestamp)
        ON CONFLICT(session_id, flag_type, detail) DO UPDATE SET
            severity = excluded.severity,
            timestamp = excluded.timestamp""",
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


# --- question transcripts (per-answer STT storage, Phase 2A) ---

def save_question_transcript(session_id: str, question_id: str, transcript: str):
    """Upsert one question's transcript. Idempotent: re-transcribing the same
    question overwrites rather than duplicates."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO question_transcripts (session_id, question_id, transcript, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, question_id) DO UPDATE SET
            transcript = excluded.transcript,
            created_at = excluded.created_at""",
        (session_id, question_id, transcript, str(datetime.utcnow())),
    )
    conn.commit()
    conn.close()


def get_question_transcript(session_id: str, question_id: str):
    """Return the transcript dict for one question, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM question_transcripts WHERE session_id = ? AND question_id = ?",
        (session_id, question_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_question_transcripts(session_id: str):
    """Return all transcripts for a session, ordered by question_id."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM question_transcripts WHERE session_id = ? ORDER BY question_id",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- session questions (per-session locked question set, Phase 2B) ---

def save_session_questions(session_id: str, questions: list[dict]):
    """Persist a locked question set for a session. Replaces any existing set.

    Each question dict must contain: question_index, question_id,
    question_text, category, competency, difficulty, source.
    """
    conn = get_connection()
    conn.execute("DELETE FROM session_questions WHERE session_id = ?", (session_id,))
    now = str(datetime.utcnow())
    for q in questions:
        conn.execute(
            """INSERT INTO session_questions
            (session_id, question_index, question_id, question_text,
             category, competency, difficulty, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                q["question_index"],
                q["question_id"],
                q["question_text"],
                q.get("category", ""),
                q.get("competency", ""),
                q.get("difficulty", "medium"),
                q.get("source", "bank"),
                now,
            ),
        )
    conn.commit()
    conn.close()


def get_session_questions(session_id: str) -> list[dict]:
    """Return the locked question set for a session, ordered by question_index."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM session_questions WHERE session_id = ? ORDER BY question_index",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def session_questions_exist(session_id: str) -> bool:
    """Check whether a session already has a locked question set."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM session_questions WHERE session_id = ? LIMIT 1",
        (session_id,),
    ).fetchone()
    conn.close()
    return row is not None


def get_session_question_by_id(session_id: str, question_id: str):
    """Return a single locked question by id, or None if it doesn't belong to
    this session. Used by the live interviewer to validate the question the
    recruiter asks actually belongs to the session's locked set."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM session_questions WHERE session_id = ? AND question_id = ?",
        (session_id, question_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_question_asked(session_id: str, question_id: str):
    """Mark a session question as asked (idempotent)."""
    conn = get_connection()
    conn.execute(
        "UPDATE session_questions SET asked = 1 WHERE session_id = ? AND question_id = ?",
        (session_id, question_id),
    )
    conn.commit()
    conn.close()


def set_live_question(session_id: str, question_id: str):
    """Persist the currently-active question for the live session ('' = none)."""
    update_session(session_id, live_question_id=question_id)


def get_live_question(session_id: str):
    """Return the currently-active question row for a live session, or None."""
    row = get_session(session_id)
    if not row:
        return None
    question_id = row.get("live_question_id", "")
    if not question_id:
        return None
    return get_session_question_by_id(session_id, question_id)


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


MANUAL_SCREENING_APPLICATION_PREFIX = "manual:"


def get_candidate_screening_result(candidate_id):
    """Canonical ScreeningResult for a candidate with no application row
    (manual resume upload). Stored under '{prefix}{candidate_id}' in the same
    screening_results table, so one authoritative result exists per candidate
    regardless of ingestion path.
    """
    return get_screening_result(f"{MANUAL_SCREENING_APPLICATION_PREFIX}{candidate_id}")


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


# --- interview routing / cohort helpers (hybrid mode-allocation) ---

VALID_INTERVIEW_STRATEGIES = ("AUTO", "MODE_1_ONLY", "MODE_2_THEN_MODE_1")
VALID_INTERVIEW_MODES = ("MODE_1", "MODE_2")
# Candidate interview-mode progression states.
MODE_STATUS_SHORTLISTED = "SHORTLISTED"          # cohort pending strategy confirm
MODE_STATUS_CONFIRMED = "CONFIRMED"              # strategy confirmed, mode assigned
MODE_STATUS_INVITED = "INVITED"                  # mode invite enqueued
MODE_STATUS_COMPLETED = "COMPLETED"              # their interview is done
MODE_STATUS_PROMOTED = "PROMOTED"                # Mode 2 → Mode 1 promotion applied
MODE_STATUS_NOT_PROMOTED = "NOT_PROMOTED"        # Mode 2 cohort done, not selected for Mode 1


def get_job_cohort_status(job_id):
    """Screening-cohort state for one job: finalized-flag, shortlist count,
    recommended strategy (AUTO), confirmed strategy, invitation progress.
    """
    job = get_job_posting(job_id)
    if job is None:
        return None
    conn = get_connection()
    row = conn.execute(
        """SELECT
            SUM(CASE WHEN ap.status IN ('invite_pending','invited','in_progress','completed') THEN 1 ELSE 0 END) AS shortlisted,
            SUM(CASE WHEN ap.screening_status IN ('queued','processing') THEN 1 ELSE 0 END) AS screening_pending
        FROM applications ap WHERE ap.job_id = ?""",
        (job_id,),
    ).fetchone()
    conn.close()
    return {
        "job_id": job_id,
        "cohort_finalized": bool(job.get("cohort_finalized_at")),
        "cohort_finalized_at": job.get("cohort_finalized_at"),
        "screening_pending": row["screening_pending"] or 0,
        "shortlisted": row["shortlisted"] or 0,
        "interview_strategy": job.get("interview_strategy", "AUTO"),
        "recommended_strategy": job.get("recommended_strategy", ""),
        "strategy_confirmed": bool(job.get("strategy_confirmed")),
        "strategy_confirmed_at": job.get("strategy_confirmed_at"),
    }


def set_job_cohort_finalized(job_id, finalized_at):
    """Mark a job's screening cohort as final (idempotent)."""
    conn = get_connection()
    conn.execute(
        "UPDATE job_postings SET cohort_finalized_at = ? WHERE job_id = ? AND cohort_finalized_at = ''",
        (finalized_at, job_id),
    )
    conn.commit()
    conn.close()


def set_job_strategy(job_id, strategy, strategy_confirmed=False, confirmed_at="",
                     recommended_strategy="", is_auto_recommendation=False):
    """Set the recruiter's interview strategy on a job. For AUTO the caller may
    persist a fresh recommendation; a manual strategy always clears it.
    Confirmation is idempotent (won't un-confirm if already confirmed)."""
    if strategy not in VALID_INTERVIEW_STRATEGIES:
        raise ValueError(f"Unknown interview strategy: {strategy!r}")
    confirmed = 1 if strategy_confirmed else 0
    conn = get_connection()
    conn.execute(
        """UPDATE job_postings
        SET interview_strategy = ?, recommended_strategy = ?,
            strategy_confirmed = ?,
            strategy_confirmed_at = CASE WHEN ? != '' AND strategy_confirmed = 0
                THEN ? ELSE strategy_confirmed_at END
        WHERE job_id = ?""",
        (
            strategy,
            recommended_strategy if is_auto_recommendation else "",
            confirmed,
            confirmed_at,
            confirmed_at,
            job_id,
        ),
    )
    conn.commit()
    conn.close()


def confirm_job_strategy(job_id, strategy, confirmed_at):
    """Persist the recruiter-confirmed strategy (separate from the PUT-on-job
    flow so a plain job edit can never silently re-confirm or overwrite it)."""
    if strategy not in VALID_INTERVIEW_STRATEGIES:
        raise ValueError(f"Unknown interview strategy: {strategy!r}")
    conn = get_connection()
    conn.execute(
        """UPDATE job_postings
        SET interview_strategy = ?, strategy_confirmed = 1, strategy_confirmed_at = ?
        WHERE job_id = ?""",
        (strategy, confirmed_at, job_id),
    )
    conn.commit()
    conn.close()


def get_strategy_recommendation(shortlist_count, capacity):
    """The AUTO recommendation a recruiter would be shown before confirming.
    Threshold: shortlisted <= capacity → everyone to a live Mode-1 interview.
    Otherwise → Mode-2 for the whole cohort, top-N (capacity) promoted to Mode 1."""
    return "MODE_1_ONLY" if shortlist_count <= capacity else "MODE_2_THEN_MODE_1"


def get_shortlisted_candidates(job_id):
    """Candidates eligible for interview-mode allocation (passed screening)."""
    return get_candidates_for_job(job_id)


def count_shortlisted_for_job(job_id):
    """Number of shortlisted (eligible) candidates for one job — the driver of
    the AUTO strategy recommendation."""
    return len(get_candidates_for_job(job_id))


def get_candidate_by_session(session_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM candidates WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    return _decode_candidate_row(dict(row)) if row else None


def set_candidate_route(candidate_id, interview_mode, mode_status, source="SYSTEM"):
    """Assign (or reassign) a candidate's interview mode + progression state."""
    if interview_mode not in {None, ""}.union(VALID_INTERVIEW_MODES):
        raise ValueError(f"Unknown interview mode: {interview_mode!r}")
    conn = get_connection()
    conn.execute(
        """UPDATE candidates
        SET interview_mode = ?, mode_status = ?, mode_assignment_source = ?
        WHERE candidate_id = ?""",
        (interview_mode or "", mode_status, source, candidate_id),
    )
    conn.commit()
    conn.close()


def set_candidate_mode2_result(candidate_id, mode2_score, overall_score):
    """Persist a candidate's Mode 2 aggregate score (computed from their
    completed session) ahead of cohort ranking."""
    conn = get_connection()
    conn.execute(
        """UPDATE candidates
        SET mode2_score = ?, overall_score = ?, ranked_at = ?
        WHERE candidate_id = ?""",
        (mode2_score, overall_score, str(_utcnow()), candidate_id),
    )
    conn.commit()
    conn.close()


def get_mode2_candidates_for_job(job_id):
    """Candidates routed to Mode 2 for a job (cohort members), invited order."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.*, s.status AS session_status, s.completed_at AS session_completed_at
        FROM candidates c
        LEFT JOIN sessions s ON c.session_id = s.session_id
        LEFT JOIN screening_results r ON c.application_id = r.application_id
        WHERE c.job_id = ?
          AND c.interview_mode = 'MODE_2'
          AND (c.application_id IS NULL OR r.decision = 'passed')
        ORDER BY c.invited_at ASC, c.candidate_id ASC""",
        (job_id,),
    ).fetchall()
    conn.close()
    return [_decode_candidate_row(dict(r)) for r in rows]


def apply_cohort_ranking(job_id, ranked, promoted, not_promoted, at):
    """Persist a Mode 2 cohort ranking in one transaction:
      * ranked       — [(candidate_id, rank_index)] every cohort member
      * promoted     — [candidate_id] of the top-N who advance to Mode 1
      * not_promoted — [candidate_id] who stay ranked but do not advance
    Idempotent by construction: routing never calls this twice with changed
    data because ranking runs exactly once per cohort (guarded upstream).
    """
    promoted_set = set(promoted)
    conn = get_connection()
    for candidate_id, rank_index in ranked:
        is_promoted = candidate_id in promoted_set
        conn.execute(
            """UPDATE candidates SET rank = ?, promoted_at = ?,
               mode_status = ?, interview_mode = ?
            WHERE candidate_id = ?""",
            (
                rank_index,
                at if is_promoted else None,
                "PROMOTED" if is_promoted else "NOT_PROMOTED",
                "MODE_1" if is_promoted else "MODE_2",
                candidate_id,
            ),
        )
    conn.commit()
    conn.close()


def set_job_recommended_strategy(job_id, recommended_strategy):
    conn = get_connection()
    conn.execute(
        "UPDATE job_postings SET recommended_strategy = ? WHERE job_id = ?",
        (recommended_strategy, job_id),
    )
    conn.commit()
    conn.close()


def get_pending_mode_assignments():
    """Candidates whose screening cohort is finalized & confirmed but who have
    not yet been routed to a Mode (used by the worker to pick up AUTO jobs)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.* FROM candidates c
        JOIN job_postings j ON c.job_id = j.job_id
        WHERE j.cohort_finalized_at != ''
          AND j.strategy_confirmed = 1
          AND c.interview_mode = ''
          AND c.mode_status = 'SHORTLISTED'""",
    ).fetchall()
    conn.close()
    return [_decode_candidate_row(dict(r)) for r in rows]


def mark_candidate_invited(candidate_id):
    """Record that a candidate's mode invite has been enqueued."""
    conn = get_connection()
    conn.execute(
        "UPDATE candidates SET mode_status = 'INVITED' WHERE candidate_id = ?",
        (candidate_id,),
    )
    conn.commit()
    conn.close()


def clear_candidate_route(candidate_id):
    """Reset routing fields when the recruiter re-assigns a candidate's mode
    before any invitation was sent (mode_status back to SHORTLISTED)."""
    conn = get_connection()
    conn.execute(
        """UPDATE candidates SET interview_mode = '', mode_status = 'SHORTLISTED',
           mode_assignment_source = '' WHERE candidate_id = ?""",
        (candidate_id,),
    )
    conn.commit()
    conn.close()


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


def get_outbox_messages():
    """Every outbox message across all applications (used by tests + the
    monitoring surface to enumerate modes/promotions without per-app queries)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notification_outbox ORDER BY id ASC"
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


# --- LinkedIn integration (member posting; DB-authoritative publication state) ---

def save_linkedin_connection(c):
    """Persists one recruiter's LinkedIn OAuth connection (upsert by username)."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO linkedin_connections
        (recruiter_username, linkedin_member_id, member_name, member_email,
         access_token, refresh_token, token_expires_at, scope, connected_at)
        VALUES (:recruiter_username, :linkedin_member_id, :member_name, :member_email,
                :access_token, :refresh_token, :token_expires_at, :scope, :connected_at)""",
        {
            "recruiter_username": c.recruiter_username,
            "linkedin_member_id": c.linkedin_member_id,
            "member_name": c.member_name,
            "member_email": c.member_email,
            "access_token": c.access_token,
            "refresh_token": c.refresh_token,
            "token_expires_at": c.token_expires_at,
            "scope": c.scope,
            "connected_at": str(c.connected_at),
        },
    )
    conn.commit()
    conn.close()


def get_linkedin_connection(username):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM linkedin_connections WHERE recruiter_username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_linkedin_connection(username):
    conn = get_connection()
    conn.execute(
        "DELETE FROM linkedin_connections WHERE recruiter_username = ?", (username,)
    )
    conn.commit()
    conn.close()


def save_linkedin_oauth_state(state, username, redirect_uri, created_at, expires_at):
    conn = get_connection()
    conn.execute(
        """INSERT INTO linkedin_oauth_states (state, recruiter_username, redirect_uri,
           created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)""",
        (state, username, redirect_uri, str(created_at), str(expires_at)),
    )
    conn.commit()
    conn.close()


def consume_linkedin_oauth_state(state, now=None):
    """Atomically claims a one-time OAuth state row.

    Returns the state row only when it was unused, unexpired, and this call won
    the single-use claim; otherwise None. Prevents replay of the callback."""
    now = now or _utcnow()
    ts = str(now)
    conn = get_connection()
    cur = conn.execute(
        """UPDATE linkedin_oauth_states SET used_at = ?
           WHERE state = ? AND used_at IS NULL AND expires_at > ?""",
        (ts, state, ts),
    )
    if cur.rowcount == 0:
        conn.close()
        return None
    row = conn.execute(
        "SELECT * FROM linkedin_oauth_states WHERE state = ?", (state,)
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def try_claim_linkedin_publish(job_id, allowed_from, stale_after_seconds=90):
    """Grants the single in-flight publish claim.

    One atomic UPDATE moves the job into 'PUBLISHING' only if its current
    status is in allowed_from; this status flip is the DB-level lock that makes
    double-click / retry produce a single LinkedIn post. A crash mid-publish
    (process dies between claim and terminal write) would otherwise leave the
    job stuck in PUBLISHING forever, so a claim older than stale_after_seconds
    may be re-claimed by a later caller. Returns True when this caller won the
    transition.
    """
    conn = get_connection()
    now = str(_utcnow())
    marks = ",".join("?" for _ in allowed_from)
    cur = conn.execute(
        f"""UPDATE job_postings
            SET linkedin_post_status = 'PUBLISHING', linkedin_claim_started_at = ?
            WHERE job_id = ? AND linkedin_post_status IN ({marks})""",
        (now, job_id, *allowed_from),
    )
    if cur.rowcount == 0:
        stale_before = str(_utcnow() - timedelta(seconds=stale_after_seconds))
        cur = conn.execute(
            """UPDATE job_postings
               SET linkedin_post_status = 'PUBLISHING', linkedin_claim_started_at = ?
               WHERE job_id = ? AND linkedin_post_status = 'PUBLISHING'
                 AND linkedin_claim_started_at IS NOT NULL
                 AND linkedin_claim_started_at < ?""",
            (now, job_id, stale_before),
        )
    conn.commit()
    conn.close()
    return cur.rowcount == 1


def set_job_linkedin_post(job_id, *, status, post_id=None, post_url=None,
                          posted_at=None, author_urn=None, last_error=None):
    conn = get_connection()
    conn.execute(
        """UPDATE job_postings SET
           linkedin_post_status = ?, linkedin_post_id = ?,
           linkedin_post_url = ?, linkedin_posted_at = ?,
           linkedin_author_urn = ?, linkedin_last_error = ?,
           linkedin_claim_started_at = NULL
           WHERE job_id = ?""",
        (status, post_id, post_url, posted_at, author_urn, last_error, job_id),
    )
    conn.commit()
    conn.close()
