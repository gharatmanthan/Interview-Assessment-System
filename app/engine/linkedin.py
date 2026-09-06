"""LinkedIn integration client — member posting only.

Encapsulates everything LinkedIn: OAuth app config, authorization-code flow,
authenticated member identity (OpenID Connect /v2/userinfo), and creating
posts via the current LinkedIn Posts API (POST /rest/posts). Route handlers
never talk to LinkedIn directly — they go through this module.

Security contract:
  * Client id/secret come from environment configuration, never from the
    frontend and never logged.
  * Access/refresh tokens are never logged, never returned to the frontend.
  * The author URN is derived server-side from the authenticated member id
    returned by LinkedIn at connect time — the frontend cannot choose it.
"""
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

from app.core.paths import get_env_file_path

PROJECT_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(PROJECT_ENV_PATH)  # noqa: F401 — parents read os.environ later
load_dotenv(get_env_file_path())  # per-user app-data .env (packaged)

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
POST_FEED_URL_PREFIX = "https://www.linkedin.com/feed/update/"

# Single centralized LinkedIn API version (YYYYMM). LinkedIn rolls this
# monthly; updates go in exactly this one place.
LINKEDIN_API_VERSION = "202608"

LINKEDIN_SCOPES = ["openid", "profile", "email", "w_member_social"]
OAUTH_STATE_TTL_MINUTES = 10
POST_TIMEOUT_SECONDS = 15
MAX_POST_CHARS = 3000


class LinkedInPostStatus:
    """DB-authoritative publication lifecycle for one job."""
    NOT_POSTED = "NOT_POSTED"
    DRAFT = "DRAFT"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class LinkedInError(Exception):
    """A LinkedIn API / OAuth failure with a safe, loggable description."""

    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status  # int or None (transport-level failures)
        self.code = code or ""
        self.message = message

    def __str__(self):
        bits = []
        if self.status is not None:
            bits.append(f"HTTP {self.status}")
        if self.code:
            bits.append(f"code={self.code}")
        bits.append(self.message)
        return " ".join(bits)


class LinkedInNotConfigured(LinkedInError):
    pass


class LinkedInTimeoutError(LinkedInError):
    """LinkedIn may or may not have accepted the request — the response was
    lost. Callers must NOT transition the job to a terminal state."""
    pass


# --- configuration ---------------------------------------------------------

def client_id() -> str:
    return os.environ.get("LINKEDIN_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.environ.get("LINKEDIN_REDIRECT_URI", "").strip()


def assert_configured():
    missing = [
        name for name, value in (
            ("LINKEDIN_CLIENT_ID", client_id()),
            ("LINKEDIN_CLIENT_SECRET", client_secret()),
            ("LINKEDIN_REDIRECT_URI", redirect_uri()),
        ) if not value
    ]
    if missing:
        raise LinkedInNotConfigured(
            "LinkedIn app is not configured (missing "
            + ", ".join(missing) + ")."
        )


def is_configured() -> bool:
    return bool(client_id() and client_secret() and redirect_uri())


# --- OAuth state (CSRF protection) ----------------------------------------

def generate_oauth_state() -> str:
    """Server-generated, cryptographically random one-time state token."""
    return secrets.token_urlsafe(32)


def build_authorization_url(state: str, redirect: str) -> str:
    """Build the LinkedIn consent URL for the server-side authorization-code
    flow. The state token is recorded server-side and bound to the recruiter;
    the callback only accepts an unused, unexpired value."""
    params = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect,
        "state": state,
        "scope": " ".join(LINKEDIN_SCOPES),
    }
    return f"{AUTH_URL}?{urlencode(params)}"


# --- token exchange + identity --------------------------------------------

def exchange_code(code: str, redirect: str) -> dict:
    """Exchange the authorization code for tokens. Never exposes the returned
    access/refresh token via logging or exceptions."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect,
        "client_id": client_id(),
        "client_secret": client_secret(),
    }
    try:
        resp = requests.post(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise LinkedInError(f"Token exchange request failed: {exc.__class__.__name__}") from exc
    data = _json(resp.json()) if resp.content else {}
    if resp.status_code != 200:
        raise LinkedInError(
            _oauth_error_message(data),
            status=resp.status_code,
            code=str(data.get("error", "")),
        )
    return {
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "expires_in": int(data.get("expires_in", 0) or 0),
        "scope": data.get("scope", ""),
    }


def get_userinfo(access_token: str) -> dict:
    """Resolve the authenticated member from the LinkedIn token (OpenID
    Connect /v2/userinfo). The 'sub' is the LinkedIn member id — the only
    trusted source for the person author URN."""
    try:
        resp = requests.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise LinkedInError(f"Member lookup failed: {exc.__class__.__name__}") from exc
    data = _json(resp.json()) if resp.content else {}
    if resp.status_code != 200:
        raise LinkedInError(
            _api_error_message(resp.status_code, data),
            status=resp.status_code,
            code=str(data.get("code", "")),
        )
    member_id = str(data.get("sub", "")).strip()
    if not member_id:
        raise LinkedInError("LinkedIn member lookup returned no member id.")
    return {
        "sub": member_id,
        "name": str(data.get("name", "") or ""),
        "email": str(data.get("email", "") or ""),
    }


def member_author_urn(member_id: str) -> str:
    return f"urn:li:person:{member_id}"


# --- post creation --------------------------------------------------------

def create_post(access_token: str, author_urn: str, commentary: str) -> str:
    """Publish a text post for the authenticated member via the current
    LinkedIn Posts API. Returns the created post URN from the x-restli-id
    response header on HTTP 201. Author and lifecycleState are backend-owned."""
    payload = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
    }
    try:
        resp = requests.post(
            POSTS_URL,
            json=payload,
            headers=headers,
            timeout=POST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        # LinkedIn may have accepted the post before our connection dropped.
        # This is deliberately NOT turned into FAILED (which would let a
        # duplicate post be created on retry).
        raise LinkedInTimeoutError(
            "LinkedIn did not respond in time; the post may have been "
            "accepted. Check LinkedIn before retrying."
        ) from exc
    except requests.RequestException as exc:
        raise LinkedInError(
            f"Post request failed: {exc.__class__.__name__}"
        ) from exc
    if resp.status_code == 201:
        post_id = (resp.headers.get("x-restli-id") or "").strip()
        if not post_id:
            raise LinkedInError(
                "LinkedIn returned 201 without a post id.", status=201
            )
        return post_id
    data = _json(resp.json()) if resp.content else {}
    raise LinkedInError(
        _api_error_message(resp.status_code, data),
        status=resp.status_code,
        code=str(data.get("code", "")),
    )


def post_feed_url(post_id: str) -> str:
    """A recruiter-visible link to the created post on LinkedIn."""
    return f"{POST_FEED_URL_PREFIX}{post_id}"


# --- helpers --------------------------------------------------------------

def _json(blob):
    if isinstance(blob, dict):
        return blob
    return {}


def _oauth_error_message(data: dict) -> str:
    desc = str(data.get("error_description", "") or "").strip()
    error = str(data.get("error", "") or "").strip()
    return f"LinkedIn OAuth error: {error} {desc}".strip() or "LinkedIn OAuth error"


def _api_error_message(status: int, data: dict) -> str:
    code = str(data.get("code", "") or "").strip()
    message = str(data.get("message", "") or "").strip()
    if code:
        return f"LinkedIn rejected the request ({status}): {code} {message}".strip()
    return f"LinkedIn rejected the request (HTTP {status})."


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()