"""PostgreSQL persistence for the deployed API.

The desktop client keeps its local SQLite store, while the API uses Neon (or
another PostgreSQL-compatible service) when DATABASE_URL is configured.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from api.auth import hash_password, verify_password


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_accounts (
    candidate_id TEXT PRIMARY KEY,
    password TEXT,
    password_hash TEXT,
    full_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interviewer_accounts (
    interviewer_id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS job_postings (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS live_interviews (
    session_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    candidate_name TEXT NOT NULL,
    question TEXT NOT NULL,
    question_index INTEGER NOT NULL DEFAULT 0,
    transcript TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'live',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pending_question TEXT NOT NULL DEFAULT '',
    pending_status TEXT NOT NULL DEFAULT 'none',
    question_count INTEGER NOT NULL DEFAULT 0,
    interview_context TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS integrity_flags (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES live_interviews(session_id) ON DELETE CASCADE,
    flag_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS integrity_flags_session_timestamp_idx
    ON integrity_flags (session_id, timestamp DESC);
"""


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    if not value:
        raise RuntimeError("DATABASE_URL is required for API persistence.")
    return value


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        yield conn


def init_db() -> None:
    with connection() as conn:
        conn.execute(SCHEMA)
        conn.execute(
            "ALTER TABLE integrity_flags ADD COLUMN IF NOT EXISTS confidence "
            "DOUBLE PRECISION NOT NULL DEFAULT 0"
        )
        conn.execute("ALTER TABLE candidate_accounts ADD COLUMN IF NOT EXISTS password_hash TEXT")
        conn.execute("ALTER TABLE candidate_accounts ALTER COLUMN password DROP NOT NULL")
        legacy = conn.execute(
            "SELECT candidate_id, password FROM candidate_accounts "
            "WHERE password_hash IS NULL AND password IS NOT NULL"
        ).fetchall()
        for account in legacy:
            conn.execute(
                "UPDATE candidate_accounts SET password_hash = %s, password = NULL "
                "WHERE candidate_id = %s",
                (hash_password(account["password"]), account["candidate_id"]),
            )
        interviewer_id = os.getenv("INTERVIEWER_ID", "").strip()
        interviewer_password = os.getenv("INTERVIEWER_PASSWORD", "")
        if interviewer_id and interviewer_password:
            conn.execute(
                """
                INSERT INTO interviewer_accounts (interviewer_id, password_hash, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (interviewer_id) DO NOTHING
                """,
                (
                    interviewer_id,
                    hash_password(interviewer_password),
                    os.getenv("INTERVIEWER_NAME", "Interviewer").strip() or "Interviewer",
                ),
            )
        conn.execute(
            """
            INSERT INTO candidate_accounts (candidate_id, password_hash, full_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (candidate_id) DO NOTHING
            """,
            ("candidate01", hash_password("interview123"), "Demo Candidate"),
        )
        for title, description in (
            (
                "Python Backend Developer",
                "Build reliable REST APIs and backend services with Python. Work with FastAPI or Django, PostgreSQL, automated tests, Git, and cloud deployment. We are looking for strong problem-solving, clean coding, and API design skills.",
            ),
            (
                "Frontend React Developer",
                "Create accessible, responsive interfaces with React and modern JavaScript or TypeScript. Collaborate with designers and backend engineers, integrate APIs, write maintainable components, and improve user experience through thoughtful testing.",
            ),
        ):
            conn.execute(
                """
                INSERT INTO job_postings (title, description)
                VALUES (%s, %s)
                ON CONFLICT (title) DO NOTHING
                """,
                (title, description),
            )


def check_connection() -> None:
    with connection() as conn:
        conn.execute("SELECT 1")


def get_candidate_accounts() -> list[dict]:
    with connection() as conn:
        return conn.execute(
            "SELECT candidate_id, full_name FROM candidate_accounts ORDER BY full_name"
        ).fetchall()


def create_candidate_account(candidate_id: str, password: str, full_name: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            """
            INSERT INTO candidate_accounts (candidate_id, password_hash, full_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (candidate_id) DO NOTHING
            """,
            (candidate_id, hash_password(password), full_name),
        )
        return result.rowcount == 1


def authenticate_candidate(candidate_id: str, password: str) -> dict | None:
    with connection() as conn:
        account = conn.execute(
            "SELECT candidate_id, full_name, password_hash FROM candidate_accounts "
            "WHERE candidate_id = %s",
            (candidate_id,),
        ).fetchone()
        if account and verify_password(password, account["password_hash"] or ""):
            return {"candidate_id": account["candidate_id"], "full_name": account["full_name"]}
        return None


def authenticate_interviewer(interviewer_id: str, password: str) -> dict | None:
    with connection() as conn:
        account = conn.execute(
            "SELECT interviewer_id, full_name, password_hash FROM interviewer_accounts "
            "WHERE interviewer_id = %s AND is_active = TRUE",
            (interviewer_id,),
        ).fetchone()
        if account and verify_password(password, account["password_hash"]):
            return {
                "interviewer_id": account["interviewer_id"],
                "full_name": account["full_name"],
            }
        return None


def get_active_job_postings() -> list[dict]:
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, title, description, created_at
            FROM job_postings
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            """
        ).fetchall()


def save_job_posting(title: str, description: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO job_postings (title, description)
            VALUES (%s, %s)
            ON CONFLICT (title) DO UPDATE SET description = EXCLUDED.description,
                is_active = TRUE
            """,
            (title, description),
        )


def get_live_interviews() -> list[dict]:
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM live_interviews WHERE status = 'live' ORDER BY updated_at DESC"
        ).fetchall()


def get_live_interview(session_id: str) -> dict | None:
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM live_interviews WHERE session_id = %s", (session_id,)
        ).fetchone()


def start_live_interview(
    session_id: str,
    candidate_id: str,
    candidate_name: str,
    question: str,
    question_index: int,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO live_interviews
            (session_id, candidate_id, candidate_name, question, question_index)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, candidate_id, candidate_name, question, question_index),
        )


def update_live_interview(session_id: str, **fields: Any) -> None:
    allowed = {
        "question", "question_index", "transcript", "status",
        "pending_question", "pending_status", "question_count", "interview_context",
    }
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
        return
    assignments = ", ".join(f"{key} = %s" for key in changes)
    with connection() as conn:
        conn.execute(
            f"UPDATE live_interviews SET {assignments}, updated_at = NOW() "
            "WHERE session_id = %s",
            (*changes.values(), session_id),
        )


def approve_pending_question(session_id: str, question: str | None = None) -> None:
    interview = get_live_interview(session_id)
    if not interview:
        return
    approved = question if question is not None else interview["pending_question"]
    update_live_interview(
        session_id,
        question=approved,
        question_index=interview["question_index"] + 1,
        question_count=interview["question_count"] + 1,
        transcript="",
        pending_question="",
        pending_status="approved",
    )


def save_integrity_flag(
    session_id: str,
    flag_type: str,
    detail: str,
    severity: str,
    confidence: float,
    timestamp: str,
) -> dict:
    with connection() as conn:
        return conn.execute(
            """
            INSERT INTO integrity_flags
                (session_id, flag_type, detail, severity, confidence, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s::timestamptz)
            RETURNING id, session_id, flag_type, detail, severity, confidence, timestamp
            """,
            (session_id, flag_type, detail, severity, confidence, timestamp),
        ).fetchone()


def get_session_flags(session_id: str) -> list[dict]:
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, session_id, flag_type, detail, severity, confidence, timestamp
            FROM integrity_flags
            WHERE session_id = %s
            ORDER BY timestamp DESC, id DESC
            """,
            (session_id,),
        ).fetchall()
