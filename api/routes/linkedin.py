import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from api.deps import get_current_recruiter
from api.schemas import LinkedInConnectResponse, LinkedInStatusResponse
from app.core import db
from app.core.models import LinkedinConnection
from app.core.settings_store import frontend_base_url
from app.engine import linkedin

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status", response_model=LinkedInStatusResponse)
def linkedin_status(username: str = Depends(get_current_recruiter)):
    """Whether THIS recruiter has LinkedIn connected. Tokens never leave the
    backend; only display-safe identity is returned."""
    conn = db.get_linkedin_connection(username)
    if not conn:
        return LinkedInStatusResponse(connected=False)
    return LinkedInStatusResponse(
        connected=True,
        member_name=conn["member_name"],
        member_email=conn["member_email"],
        connected_at=conn["connected_at"],
        member_author_urn=linkedin.member_author_urn(conn["linkedin_member_id"]),
    )


@router.get("/connect", response_model=LinkedInConnectResponse)
def linkedin_connect(username: str = Depends(get_current_recruiter)):
    """Start the server-side authorization-code flow.

    Generates a one-time CSRF state token, records it tied to this recruiter,
    and returns the LinkedIn consent URL. The frontend opens it in a new tab;
    the backend derives the member identity from the callback, never from the
    frontend."""
    try:
        linkedin.assert_configured()
    except linkedin.LinkedInNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    state = linkedin.generate_oauth_state()
    redirect = linkedin.redirect_uri()
    now = datetime.utcnow()
    db.save_linkedin_oauth_state(
        state=state,
        username=username,
        redirect_uri=redirect,
        created_at=now,
        expires_at=now + timedelta(minutes=linkedin.OAUTH_STATE_TTL_MINUTES),
    )
    return LinkedInConnectResponse(authorization_url=linkedin.build_authorization_url(state, redirect))


@router.get("/callback")
def linkedin_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
):
    """OAuth redirect target: validate state, exchange the code, resolve the
    authenticated member, persist the per-recruiter connection, and send the
    recruiter back to the frontend."""
    base = frontend_base_url()

    if error:
        reason = "denied" if error == "access_denied" else "error"
        return RedirectResponse(url=f"{base}/settings?linkedin=failed&reason={reason}",
                                status_code=302)

    claimed = db.consume_linkedin_oauth_state(state)
    if claimed is None:
        raise HTTPException(status_code=400, detail="Invalid, expired, or already-used OAuth state.")
    if claimed["redirect_uri"] != linkedin.redirect_uri():
        raise HTTPException(status_code=400, detail="Redirect URI does not match the configured value.")

    try:
        tokens = linkedin.exchange_code(code, claimed["redirect_uri"])
        if not tokens.get("access_token"):
            raise linkedin.LinkedInError("Token exchange returned no access token.")
        account = linkedin.get_userinfo(tokens["access_token"])
    except linkedin.LinkedInError as exc:
        # Log code/message only — never the token.
        logger.warning(
            "[linkedin] callback failed for recruiter=%s: %s",
            claimed["recruiter_username"], exc,
        )
        return RedirectResponse(url=f"{base}/settings?linkedin=failed", status_code=302)

    expires_at = ""
    if tokens.get("expires_in"):
        expires_at = (
            datetime.utcnow() + timedelta(seconds=int(tokens["expires_in"]))
        ).isoformat()
    db.save_linkedin_connection(LinkedinConnection(
        recruiter_username=claimed["recruiter_username"],
        linkedin_member_id=account["sub"],
        member_name=account["name"],
        member_email=account["email"],
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", "") or "",
        token_expires_at=expires_at,
        scope=tokens.get("scope", ""),
    ))
    return RedirectResponse(url=f"{base}/settings?linkedin=connected", status_code=302)


@router.post("/disconnect")
def linkedin_disconnect(username: str = Depends(get_current_recruiter)):
    db.delete_linkedin_connection(username)
    return {"success": True, "message": "LinkedIn disconnected"}