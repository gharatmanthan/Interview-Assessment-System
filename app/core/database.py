"""
Database abstraction layer supporting both SQLite (dev/local) and PostgreSQL (production).

This module provides a unified interface for database operations while
allowing the underlying engine to be swapped via DATABASE_URL environment variable.

Usage:
    from app.core.database import get_db, init_db
    
    with get_db() as conn:
        conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = conn.fetchone()
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, List, Dict, Tuple, Union
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.paths import get_app_data_dir


class DatabaseConfig:
    """Database configuration from environment."""
    
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL", "").strip()
        self.is_postgresql = self.database_url.startswith("postgresql://") or self.database_url.startswith("postgres://")
        self._sqlite_path_override: Optional[Path] = None
        
    def get_sqlite_path(self) -> Path:
        """Get SQLite database path for local development."""
        if self._sqlite_path_override:
            return self._sqlite_path_override
        return get_app_data_dir() / "app.db"
    
    def set_sqlite_path(self, path: Path) -> None:
        """Override SQLite path (for testing)."""
        self._sqlite_path_override = path
    
    def get_connection_params(self) -> dict:
        """Parse PostgreSQL connection parameters from DATABASE_URL."""
        if not self.is_postgresql:
            return {}
        parsed = urlparse(self.database_url)
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "user": parsed.username,
            "password": parsed.password,
            "dbname": parsed.path.lstrip("/"),
        }


# Global config instance
_db_config = DatabaseConfig()


def get_db_config() -> DatabaseConfig:
    """Get the global database configuration."""
    return _db_config


def set_db_config(config: DatabaseConfig) -> None:
    """Set the global database configuration (for testing)."""
    global _db_config
    _db_config = config


# SQLite ? -> PostgreSQL %s placeholder translation
_PLACEHOLDER_RE = re.compile(r'\?')


def _translate_placeholders(query: str, is_postgresql: bool) -> str:
    """Translate SQLite ? placeholders to PostgreSQL %s placeholders."""
    if not is_postgresql:
        return query
    return _PLACEHOLDER_RE.sub('%s', query)


class DatabaseConnection:
    """Unified database connection interface."""
    
    def __init__(self, conn: Any, is_postgresql: bool):
        self._conn = conn
        self._is_postgresql = is_postgresql
        self._cursor = None
    
    def execute(self, query: str, params: tuple = ()) -> 'DatabaseConnection':
        """Execute a query and return self for chaining."""
        translated_query = _translate_placeholders(query, self._is_postgresql)
        if self._is_postgresql:
            self._cursor = self._conn.execute(translated_query, params)
        else:
            self._cursor = self._conn.execute(translated_query, params)
        return self
    
    def executemany(self, query: str, params_list: list) -> 'DatabaseConnection':
        """Execute a query multiple times with different parameters."""
        translated_query = _translate_placeholders(query, self._is_postgresql)
        if self._is_postgresql:
            self._cursor = self._conn.executemany(translated_query, params_list)
        else:
            self._cursor = self._conn.executemany(translated_query, params_list)
        return self
    
    def executescript(self, script: str) -> 'DatabaseConnection':
        """Execute a script (SQLite only)."""
        if self._is_postgresql:
            # For PostgreSQL, split by semicolon and execute each statement
            statements = [s.strip() for s in script.split(';') if s.strip()]
            for stmt in statements:
                self._conn.execute(stmt)
        else:
            self._conn.executescript(script)
        return self
    
    def fetchone(self) -> Optional[dict]:
        """Fetch one row as dict."""
        if self._cursor is None:
            return None
        row = self._cursor.fetchone()
        return dict(row) if row else None
    
    def fetchall(self) -> list[dict]:
        """Fetch all rows as list of dicts."""
        if self._cursor is None:
            return []
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]
    
    def commit(self) -> None:
        """Commit transaction."""
        self._conn.commit()
    
    def rollback(self) -> None:
        """Rollback transaction."""
        self._conn.rollback()
    
    def close(self) -> None:
        """Close connection (return to pool for PostgreSQL)."""
        if self._cursor:
            self._cursor.close()
        if not self._is_postgresql:
            self._conn.close()
    
    def rowcount(self) -> int:
        """Get rowcount from last operation."""
        if self._cursor:
            return self._cursor.rowcount
        return 0
    
    def lastrowid(self) -> int:
        """Get last insert rowid (SQLite only)."""
        if self._is_postgresql:
            return 0
        return self._conn.lastrowid
    
    def __enter__(self) -> 'DatabaseConnection':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class DatabaseEngine:
    """Main database engine supporting SQLite and PostgreSQL."""
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or _db_config
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._pg_pool: Optional[ConnectionPool] = None
    
    @property
    def is_postgresql(self) -> bool:
        return self.config.is_postgresql
    
    def _get_sqlite_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection (cached for reuse)."""
        if self._sqlite_conn is None:
            db_path = self.config.get_sqlite_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._sqlite_conn.row_factory = sqlite3.Row
            self._sqlite_conn.execute("PRAGMA foreign_keys = ON")
            self._sqlite_conn.execute("PRAGMA journal_mode = WAL")
        return self._sqlite_conn
    
    def new_sqlite_connection(self) -> sqlite3.Connection:
        """Create a fresh SQLite connection (not cached).
        
        Use this for operations that will call close() on the connection,
        such as migration functions or one-off scripts.
        """
        db_path = self.config.get_sqlite_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    
    def _get_pg_connection(self) -> psycopg.Connection:
        """Get a connection from the PostgreSQL pool."""
        if self._pg_pool is None:
            params = self.config.get_connection_params()
            self._pg_pool = ConnectionPool(
                min_size=2,
                max_size=10,
                kwargs=params,
            )
        return self._pg_pool.getconn()
    
    def _return_pg_connection(self, conn: psycopg.Connection) -> None:
        """Return a connection to the PostgreSQL pool."""
        if self._pg_pool:
            self._pg_pool.putconn(conn)
    
    def init(self) -> None:
        """Initialize database (create tables if needed)."""
        if self.is_postgresql:
            self._init_postgresql()
        else:
            self._init_sqlite()
    
    def _init_sqlite(self) -> None:
        """Initialize SQLite database with full schema."""
        conn = self._get_sqlite_connection()
        self._run_migrations(conn)
        conn.commit()
    
    def _run_migrations(self, conn) -> None:
        """Run SQLite migrations (schema creation)."""
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
            missing_skills TEXT,
            source TEXT DEFAULT 'manual',
            screening_status TEXT DEFAULT 'pending',
            invite_email_sent INTEGER DEFAULT 0,
            application_id TEXT,
            interview_mode TEXT DEFAULT '',
            mode_status TEXT DEFAULT '',
            mode2_score REAL,
            overall_score REAL,
            rank INTEGER,
            ranked_at TEXT,
            promoted_at TEXT,
            mode_assignment_source TEXT DEFAULT ''
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
            created_at TEXT,
            screening_threshold REAL DEFAULT 60.0,
            application_gmail_label TEXT DEFAULT '',
            screening_enabled INTEGER DEFAULT 1,
            auto_invite_enabled INTEGER DEFAULT 1,
            minimum_experience_years REAL,
            required_education TEXT DEFAULT '',
            screening_weights TEXT DEFAULT '{"skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10}',
            created_by TEXT DEFAULT 'recruiter',
            linkedin_post_status TEXT DEFAULT 'NOT_POSTED',
            linkedin_post_id TEXT,
            linkedin_post_url TEXT,
            linkedin_posted_at TEXT,
            linkedin_author_urn TEXT,
            linkedin_last_error TEXT,
            linkedin_claim_started_at TEXT,
            interview_strategy TEXT DEFAULT 'AUTO',
            recommended_strategy TEXT DEFAULT '',
            strategy_confirmed INTEGER DEFAULT 0,
            strategy_confirmed_at TEXT DEFAULT '',
            cohort_finalized_at TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
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
            status TEXT,
            live_question_id TEXT DEFAULT ''
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
        CREATE TABLE IF NOT EXISTS question_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(session_id, question_id)
        );
        CREATE INDEX IF NOT EXISTS idx_qtranscripts_session ON question_transcripts(session_id);
        CREATE TABLE IF NOT EXISTS session_questions (
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
            asked INTEGER NOT NULL DEFAULT 0,
            UNIQUE(session_id, question_index),
            UNIQUE(session_id, question_id)
        );
        CREATE INDEX IF NOT EXISTS idx_sq_session ON session_questions(session_id);
        """)
        
        # Add default candidate account for testing
        try:
            conn.execute(
                """INSERT OR IGNORE INTO candidate_accounts
                (candidate_id, password_hash, full_name)
                VALUES (?, ?, ?)""",
                ("candidate01", f"interviewiq${self._hash_password('interview123', 'interviewiq')}", "Demo Candidate"),
            )
        except Exception:
            pass
    
    def _init_postgresql(self) -> None:
        """Initialize PostgreSQL connection pool and run migrations."""
        # Ensure pool is created
        self._get_pg_connection()
        # Run migrations in a connection
        with self.connect() as conn:
            self._run_migrations_pg(conn._conn)
    
    def _run_migrations_pg(self, conn) -> None:
        """Run PostgreSQL migrations."""
        conn.execute("""
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
            missing_skills TEXT,
            source TEXT DEFAULT 'manual',
            screening_status TEXT DEFAULT 'pending',
            invite_email_sent INTEGER DEFAULT 0,
            application_id TEXT,
            interview_mode TEXT DEFAULT '',
            mode_status TEXT DEFAULT '',
            mode2_score REAL,
            overall_score REAL,
            rank INTEGER,
            ranked_at TEXT,
            promoted_at TEXT,
            mode_assignment_source TEXT DEFAULT ''
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
            created_at TEXT,
            screening_threshold REAL DEFAULT 60.0,
            application_gmail_label TEXT DEFAULT '',
            screening_enabled INTEGER DEFAULT 1,
            auto_invite_enabled INTEGER DEFAULT 1,
            minimum_experience_years REAL,
            required_education TEXT DEFAULT '',
            screening_weights TEXT DEFAULT '{"skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10}',
            created_by TEXT DEFAULT 'recruiter',
            linkedin_post_status TEXT DEFAULT 'NOT_POSTED',
            linkedin_post_id TEXT,
            linkedin_post_url TEXT,
            linkedin_posted_at TEXT,
            linkedin_author_urn TEXT,
            linkedin_last_error TEXT,
            linkedin_claim_started_at TEXT,
            interview_strategy TEXT DEFAULT 'AUTO',
            recommended_strategy TEXT DEFAULT '',
            strategy_confirmed INTEGER DEFAULT 0,
            strategy_confirmed_at TEXT DEFAULT '',
            cohort_finalized_at TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
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
            status TEXT,
            live_question_id TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS integrity_flags (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            flag_type TEXT,
            detail TEXT,
            severity TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS competency_scores (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            question_id TEXT,
            category TEXT,
            score REAL,
            confidence REAL
        );
        CREATE TABLE IF NOT EXISTS explanations (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            question_id TEXT,
            summary TEXT,
            supporting_phrases TEXT
        );
        CREATE TABLE IF NOT EXISTS fairness_flags (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            application_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS screening_results (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            application_id TEXT NOT NULL,
            event TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_app_events_application ON application_events(application_id);
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
        CREATE TABLE IF NOT EXISTS question_transcripts (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(session_id, question_id)
        );
        CREATE INDEX IF NOT EXISTS idx_qtranscripts_session ON question_transcripts(session_id);
        CREATE TABLE IF NOT EXISTS session_questions (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            question_text TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            competency TEXT NOT NULL DEFAULT '',
            difficulty TEXT NOT NULL DEFAULT 'medium',
            source TEXT NOT NULL DEFAULT 'bank',
            created_at TEXT NOT NULL,
            asked INTEGER NOT NULL DEFAULT 0,
            UNIQUE(session_id, question_index),
            UNIQUE(session_id, question_id)
        );
        CREATE INDEX IF NOT EXISTS idx_sq_session ON session_questions(session_id);
        """)
    
    def _hash_password(self, password: str, salt: str) -> str:
        import hashlib
        return hashlib.sha256((salt + password).encode()).hexdigest()


# Global database engine instance
_db_engine: Optional[DatabaseEngine] = None


def get_database_engine() -> DatabaseEngine:
    """Get the global database engine instance."""
    global _db_engine
    if _db_engine is None:
        _db_engine = DatabaseEngine()
    return _db_engine


def set_database_engine(engine: DatabaseEngine) -> None:
    """Set the global database engine instance (for testing)."""
    global _db_engine
    _db_engine = engine


@contextmanager
def get_db() -> Generator[DatabaseConnection, None, None]:
    """Get a database connection (context manager)."""
    engine = get_database_engine()
    with engine.connect() as conn:
        yield conn


def init_db() -> None:
    """Initialize the database (create tables)."""
    engine = get_database_engine()
    engine.init()


def get_db_engine() -> DatabaseEngine:
    """Get the database engine instance (alias for get_database_engine)."""
    return get_database_engine()