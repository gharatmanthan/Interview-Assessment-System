"""
Single source of truth for the Google OAuth client used by both Gmail
(email intake) and Google Calendar (auto-scheduling).

The application loads client_id / client_secret from data/client_secret.json
at use-time and never mirrors those values into data/settings.json. Runtime
state stored in settings is limited to the refresh token per service.

No secrets are logged by this module.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CLIENT_SECRET_PATH = Path(__file__).parent.parent.parent / "data" / "client_secret.json"

TOKEN_URI = "https://oauth2.googleapis.com/token"


def load_oauth_client(path=None) -> dict:
    """Load client credentials from a Google client_secret.json.

    Returns {'client_id', 'client_secret', 'token_uri'}. Values are empty
    strings when the file is unparseable or lacks an 'installed'/'web'
    section. Raises FileNotFoundError only when the file is absent.
    """
    if path is None:
        path = CLIENT_SECRET_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"OAuth client_secret.json not found at {path}. "
            "Download it from Google Cloud Console and place it in data/."
        )
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read OAuth client_secret.json: %s", exc)
        return {"client_id": "", "client_secret": "", "token_uri": TOKEN_URI}
    section = data.get("installed") or data.get("web") or {}
    return {
        "client_id": section.get("client_id", ""),
        "client_secret": section.get("client_secret", ""),
        "token_uri": TOKEN_URI,
    }


def load_oauth_credentials(refresh_token: str, path=None):
    """Build google.oauth2.credentials.Credentials from client_secret.json
    plus the stored refresh token so offline token refresh keeps working.

    Returns None (treated as "not connected") when the refresh token is
    absent or the OAuth client config cannot be loaded. Never raises.
    """
    from google.oauth2.credentials import Credentials

    if not refresh_token:
        return None
    try:
        client = load_oauth_client(path)
    except FileNotFoundError as exc:
        logger.warning("Cannot refresh token — %s", exc)
        return None
    if not client["client_id"] or not client["client_secret"]:
        logger.warning("OAuth client_id/secret missing from client_secret.json — blocking token refresh")
        return None
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=client["token_uri"],
        client_id=client["client_id"],
        client_secret=client["client_secret"],
    )