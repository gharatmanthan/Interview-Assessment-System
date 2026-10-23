"""SQLite persistence for the local-network desktop API.

The interviewer PC owns this database. Candidate and interviewer desktop
clients communicate with it over the private local network.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from api.auth import hash_password, verify_password

DB_PATH = Path(
    os.getenv("INTERVIEWIQ_API_DB", str(Path(__file__).parent.parent / "data" / "network.db"))
)
DEFAULT_INTERVIEWER_ID = "interviewer01"
DEFAULT_INTERVIEWER_PASSWORD = "interviewer123"
DEFAULT_INTERVIEWER_NAME = "Local Interviewer"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_accounts (
    candidate_id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interviewer_accounts (
    interviewer_id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER NOT NULL DEFAULT 1
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
CREATE TABLE IF NOT EXISTS integrity_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    flag_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'open',
    review_note TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS live_interview_frames (
    session_id TEXT PRIMARY KEY,
    image BLOB NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO interviewer_accounts (interviewer_id, password_hash, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(interviewer_id) DO UPDATE SET
                password_hash = excluded.password_hash,
                full_name = excluded.full_name,
                is_active = 1
            """,
            (
                DEFAULT_INTERVIEWER_ID,
                hash_password(DEFAULT_INTERVIEWER_PASSWORD),
                DEFAULT_INTERVIEWER_NAME,
            ),
        )
        conn.execute(
            """
            INSERT INTO candidate_accounts (candidate_id, password_hash, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(candidate_id) DO NOTHING
            """,
            ("candidate01", hash_password("interview123"), "Demo Candidate"),
        )
        for title, description in (
            (
                "Python Backend Developer",
                "Build reliable REST APIs and backend services with Python.",
            ),
            (
                "Frontend React Developer",
                "Create accessible, responsive interfaces with React.",
            ),
        ):
            conn.execute(
                """
                INSERT INTO job_postings (title, description)
                VALUES (?, ?)
                ON CONFLICT(title) DO NOTHING
                """,
                (title, description),
            )


def check_connection() -> None:
    with connection() as conn:
        conn.execute("SELECT 1").fetchone()


def get_candidate_accounts() -> list[dict]:
    with connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT candidate_id, full_name FROM candidate_accounts ORDER BY full_name"
            )
        ]


def create_candidate_account(candidate_id: str, password: str, full_name: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            """
            INSERT INTO candidate_accounts (candidate_id, password_hash, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(candidate_id) DO NOTHING
            """,
            (candidate_id, hash_password(password), full_name),
        )
        return result.rowcount == 1


def authenticate_candidate(candidate_id: str, password: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT candidate_id, full_name, password_hash FROM candidate_accounts WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return {"candidate_id": row["candidate_id"], "full_name": row["full_name"]}
    return None


def authenticate_interviewer(interviewer_id: str, password: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT interviewer_id, full_name, password_hash
            FROM interviewer_accounts
            WHERE interviewer_id = ? AND is_active = 1
            """,
            (interviewer_id,),
        ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return {"interviewer_id": row["interviewer_id"], "full_name": row["full_name"]}
    return None


def get_active_job_postings() -> list[dict]:
    with connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, description, created_at
                FROM job_postings WHERE is_active = 1
                ORDER BY created_at DESC
                """
            )
        ]


def save_job_posting(title: str, description: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO job_postings (title, description)
            VALUES (?, ?)
            ON CONFLICT(title) DO UPDATE SET
                description = excluded.description, is_active = 1
            """,
            (title, description),
        )


def get_live_interviews() -> list[dict]:
    with connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM live_interviews WHERE status = 'live' ORDER BY updated_at DESC"
            )
        ]


def get_live_interview(session_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM live_interviews WHERE session_id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def save_live_frame(session_id: str, image: bytes) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO live_interview_frames (session_id, image)
            VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                image = excluded.image, updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, image),
        )


def get_live_frame(session_id: str) -> bytes | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT image FROM live_interview_frames WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return bytes(row["image"]) if row else None


def start_live_interview(
    session_id: str, candidate_id: str, candidate_name: str,
    question: str, question_index: int,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO live_interviews
            (session_id, candidate_id, candidate_name, question, question_index)
            VALUES (?, ?, ?, ?, ?)
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
    assignments = ", ".join(f"{key} = ?" for key in changes)
    with connection() as conn:
        conn.execute(
            f"UPDATE live_interviews SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
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
    session_id: str, flag_type: str, detail: str, severity: str,
    confidence: float, timestamp: str,
) -> dict:
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO integrity_flags
            (session_id, flag_type, detail, severity, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, flag_type, detail, severity, confidence, timestamp),
        )
        row = conn.execute(
            "SELECT * FROM integrity_flags WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_session_flags(session_id: str) -> list[dict]:
    with connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM integrity_flags
                WHERE session_id = ? ORDER BY timestamp DESC, id DESC
                """,
                (session_id,),
            )
        ]


def review_integrity_flag(
    session_id: str, flag_id: int, review_status: str, review_note: str
) -> dict | None:
    reviewed_at = None if review_status == "open" else "CURRENT_TIMESTAMP"
    with connection() as conn:
        if reviewed_at is None:
            conn.execute(
                """
                UPDATE integrity_flags
                SET review_status = ?, review_note = ?, reviewed_at = NULL
                WHERE id = ? AND session_id = ?
                """,
                (review_status, review_note, flag_id, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE integrity_flags
                SET review_status = ?, review_note = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND session_id = ?
                """,
                (review_status, review_note, flag_id, session_id),
            )
        row = conn.execute(
            "SELECT * FROM integrity_flags WHERE id = ? AND session_id = ?",
            (flag_id, session_id),
        ).fetchone()
        return dict(row) if row else None
