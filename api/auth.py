"""Password hashing and signed API session tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 300_000)
    return f"pbkdf2_sha256$300000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def _secret() -> bytes:
    secret = os.getenv("AUTH_SECRET", "").strip()
    if not secret:
        raise RuntimeError("AUTH_SECRET is required for authenticated API access.")
    return secret.encode()


def create_token(user_id: str, role: str, expires_in: int = 8 * 60 * 60) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + expires_in,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = hmac.new(_secret(), encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def decode_token(token: str) -> dict:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_secret(), encoded.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("Invalid token signature.")
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("Token has expired.")
        if not payload.get("sub") or not payload.get("role"):
            raise ValueError("Token payload is incomplete.")
        return payload
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid access token.") from exc


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
