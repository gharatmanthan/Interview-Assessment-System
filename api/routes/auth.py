from fastapi import APIRouter, HTTPException, status

from api import persistence
from api.auth import create_token
from api.schemas import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/candidate")
def candidate_login(payload: LoginRequest) -> dict:
    account = persistence.authenticate_candidate(payload.identity, payload.password)
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    return {**account, "role": "candidate", "access_token": create_token(payload.identity, "candidate")}


@router.post("/interviewer")
def interviewer_login(payload: LoginRequest) -> dict:
    account = persistence.authenticate_interviewer(payload.identity, payload.password)
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    return {**account, "role": "interviewer", "access_token": create_token(payload.identity, "interviewer")}
