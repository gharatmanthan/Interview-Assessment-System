import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from api import persistence
from api.auth import create_token
from api.dependencies import require_role
from api.schemas import InvitationRequest, PublicRegistrationRequest

router = APIRouter(prefix="/public", tags=["public"])


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationRequest,
    user: dict = Depends(require_role("interviewer")),
) -> dict:
    token = secrets.token_urlsafe(32)
    try:
        invitation = persistence.create_invitation(
            token, payload.job_id, user["sub"], payload.expires_in_hours
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not create invitation.") from exc
    return {
        "token": token,
        "job_id": invitation["job_id"],
        "expires_at": invitation["expires_at"],
    }


@router.get("/invitations/{token}")
def get_invitation(token: str) -> dict:
    invitation = persistence.get_public_invitation(token)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation is invalid or expired.")
    return invitation


@router.post("/invitations/{token}/register")
def register_candidate(token: str, payload: PublicRegistrationRequest) -> dict:
    account = persistence.register_public_candidate(
        token, payload.full_name, payload.email, payload.password
    )
    if account is None:
        raise HTTPException(status_code=410, detail="Invitation is invalid or expired.")
    return {
        **account,
        "role": "candidate",
        "access_token": create_token(account["candidate_id"], "candidate"),
    }
