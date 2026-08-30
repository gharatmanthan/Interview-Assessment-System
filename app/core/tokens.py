"""
Stdlib-only signed auth tokens (HMAC-SHA256, base64url payload).

Deliberately NOT JWT to keep the dependency footprint zero; the wire
format is a signed {sub, iat, exp} blob with the same properties the
routes need (tamper-proof, expiring, bearer). The signing secret is a
random value persisted in settings.json at first use so tokens survive
restarts.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.settings_store import load_settings, save_settings

ALGORITHM = "sha256"


def _get_or_create_secret() -> str:
    secret = load_settings().get("auth_secret") or ""
    if not secret:
        secret = secrets.token_hex(32)
        save_settings({"auth_secret": secret})
    return secret


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(message: bytes) -> bytes:
    return hmac.new(_get_or_create_secret().encode(), message, hashlib.sha256).digest()


def create_token(username: str, ttl_seconds: int = 7 * 24 * 3600) -> tuple[str, int]:
    """Return (token, expiry_epoch). Token expires after ttl_seconds."""
    now = int(time.time())
    payload = {"sub": username, "iat": now, "exp": now + ttl_seconds}
    raw = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(_sign(raw.encode()))
    return f"{raw}.{sig}", payload["exp"]


def verify_token(token: str):
    """Return the username on a valid, non-expired recruiter token; else None.

    Rejects tokens carrying an explicit type, so interview/consent tokens
    (typ == "interview") or any other typed token can never be replayed as
    recruiter credentials. Legacy recruiter tokens (no typ claim) remain valid.
    """
    try:
        raw, sig = token.split(".", 1)
        if not hmac.compare_digest(
            _sign(raw.encode()), _unb64url(sig)
        ):
            return None
        payload = json.loads(_unb64url(raw).decode())
        if int(payload["exp"]) < int(time.time()):
            return None
        if payload.get("typ") is not None and payload.get("typ") != "recruiter":
            return None
        return payload.get("sub")
    except Exception:
        return None


# --- interview access tokens ---

def create_interview_token(
    candidate_id: str, job_id: str, ttl_seconds: int = 4 * 3600
) -> tuple[str, int]:
    """Signed, short-lived token binding a candidate to one job. Issued only
    after the candidate's invite code validates, so start-session/consent can
    derive identity server-side instead of trusting the client's candidate_id.
    Returns (token, expiry_epoch)."""
    now = int(time.time())
    payload = {
        "typ": "interview",
        "sub": candidate_id,
        "job": job_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    raw = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(_sign(raw.encode()))
    return f"{raw}.{sig}", payload["exp"]


def verify_interview_token(token: str):
    """Return (candidate_id, job_id) for a valid, unexpired interview token;
    else None. The token type is checked so a recruiter auth token cannot be
    replayed as interview access."""
    try:
        raw, sig = token.split(".", 1)
        if not hmac.compare_digest(_sign(raw.encode()), _unb64url(sig)):
            return None
        payload = json.loads(_unb64url(raw).decode())
        if payload.get("typ") != "interview":
            return None
        if int(payload["exp"]) < int(time.time()):
            return None
        candidate_id = payload.get("sub")
        job_id = payload.get("job")
        if not candidate_id or not job_id:
            return None
        return candidate_id, job_id
    except Exception:
        return None


# --- media (signed URL) tokens ---

def create_media_token(path: str, ttl_seconds: int = 3600) -> tuple[str, int]:
    """Sign a media path. Returns (sig, expiry_epoch). The URL consumer
    builds: /media/{path}?sig={sig}&exp={expiry_epoch}."""
    exp = int(time.time()) + ttl_seconds
    payload = {"p": path, "exp": exp}
    raw = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(_sign(raw.encode()))
    return sig, exp


def verify_media_token(path: str, sig: str, exp: str) -> bool:
    """True when the signature matches the path and is not expired."""
    try:
        if not sig or not exp:
            return False
        if int(exp) < int(time.time()):
            return False
        expected = json.dumps({"p": path, "exp": int(exp)}, separators=(",", ":"))
        return hmac.compare_digest(
            _sign(_b64url(expected.encode()).encode()), _unb64url(sig)
        )
    except Exception:
        return False