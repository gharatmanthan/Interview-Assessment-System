"""
FastAPI dependencies — authentication + ownership for recruiter routes.

get_current_recruiter: parses the Bearer token and resolves the username.
Any router that must not be reachable by anonymous callers adds
    Depends(get_current_recruiter)
Public + candidate-facing endpoints intentionally stay open.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import db
from app.core.tokens import verify_interview_token, verify_token

_bearer = HTTPBearer(auto_error=False)


def get_current_recruiter(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """Resolve the authenticated recruiter username from the Bearer token."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = verify_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


def get_optional_recruiter(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Like get_current_recruiter but returns None instead of 401 — for
    routes that are public but show extra data when authenticated.
    """
    if credentials is None or not credentials.credentials:
        return None
    return verify_token(credentials.credentials)


class InterviewTokenInvalid(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Interview access token is missing, invalid, or expired.",
        )


def _interview_identity(token: str) -> tuple[str, str]:
    """Resolve (candidate_id, job_id) from an X-Interview-Token header value."""
    identity = verify_interview_token(token)
    if not identity:
        raise InterviewTokenInvalid()
    return identity


def require_interview_session(session_id: str, x_interview_token: str = Header(default="")):
    """Require the request to carry a valid interview token whose candidate
    owns the given session_id. Used by candidate upload/intake endpoints that
    operate on a session from the URL/body (recordings, live frames, flags)."""
    candidate_id, job_id = _interview_identity(x_interview_token)
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise InterviewTokenInvalid()
    if candidate.get("session_id") != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to this candidate.",
        )
    return candidate