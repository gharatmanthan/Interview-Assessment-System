from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_current_recruiter
from api.rate_limit import rate_limited
from api.schemas import LoginRequest, RegisterRequest, AuthResponse, CurrentUserResponse
from app.core.auth import register_recruiter, verify_recruiter
from app.core import db
from app.core.tokens import create_token

router = APIRouter()


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(rate_limited("auth"))])
def login(req: LoginRequest):
    success, message = verify_recruiter(req.username, req.password)
    if not success:
        return AuthResponse(success=False, message=message)
    token, expires_at = create_token(req.username)
    return AuthResponse(
        success=True,
        message=message,
        username=req.username,
        token=token,
        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
    )


@router.post("/register", response_model=AuthResponse, dependencies=[Depends(rate_limited("auth"))])
def register(req: RegisterRequest):
    success, message = register_recruiter(req.username, req.password, req.full_name)
    if not success:
        return AuthResponse(success=False, message=message)
    token, expires_at = create_token(req.username)
    return AuthResponse(
        success=True,
        message=message,
        username=req.username,
        token=token,
        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(username: str = Depends(get_current_recruiter)):
    """Return the authenticated recruiter's profile. Also exercises the
    token path so clients can detect invalid/expired tokens early."""
    user = db.get_recruiter_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return CurrentUserResponse(username=user["username"], full_name=user.get("full_name", ""))