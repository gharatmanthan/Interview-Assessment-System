"""
Recruiter auth — PBKDF2-SHA256 (120k iterations) password hashing, stored as
a self-describing string:

    pbkdf2_sha256$<iterations>$<salt>$<hex>

Legacy salted-SHA-256 hashes ("<salt>$<hex>") from earlier versions are still
accepted so existing demo accounts keep working; a successful legacy login is
transparently re-hashed to the PBKDF2 format. Failed logins always report the
same message so username enumeration via /api/auth/login is not possible.
"""
import hashlib
import hmac
import secrets

from app.core import db

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 120_000

WRONG_CREDENTIALS = "Invalid username or password."


def _hash_sha256(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _hash_pbkdf2(password: str, salt: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()


def _encode_password_hash(salt: str, hashed: str) -> str:
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${salt}${hashed}"


def _decode_password_hash(stored: str):
    """Return (scheme, salt, hashed, iterations); scheme is 'pbkdf2',
    'legacy_sha256', or None when the record is unparseable."""
    if stored.startswith(_PBKDF2_ALGO + "$"):
        try:
            _, iterations, salt, hashed = stored.split("$", 3)
            return "pbkdf2", salt, hashed, int(iterations)
        except ValueError:
            return None, None, None, None
    if stored.count("$") == 1:
        salt, hashed = stored.split("$", 1)
        return "legacy_sha256", salt, hashed, None
    return None, None, None, None


def _upgrade_to_pbkdf2(username: str, password: str):
    """Re-hash a legacy account to PBKDF2 after a successful login."""
    from app.core.models import RecruiterUser

    user = db.get_recruiter_user(username)
    if not user:
        return
    salt = secrets.token_hex(16)
    db.save_recruiter_user(RecruiterUser(
        username=username,
        password_hash=_encode_password_hash(salt, _hash_pbkdf2(password, salt)),
        full_name=user.get("full_name", ""),
    ))


def register_recruiter(username: str, password: str, full_name: str = "") -> tuple:
    """Returns (success: bool, message: str)."""
    from app.core.models import RecruiterUser

    if db.get_recruiter_user(username):
        return False, "That username is already taken."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    salt = secrets.token_hex(16)
    stored_hash = _encode_password_hash(salt, _hash_pbkdf2(password, salt))

    db.save_recruiter_user(RecruiterUser(
        username=username, password_hash=stored_hash, full_name=full_name
    ))
    return True, "Account created."


def verify_recruiter(username: str, password: str) -> tuple:
    """Returns (success: bool, message: str)."""
    user = db.get_recruiter_user(username)
    if not user:
        return False, WRONG_CREDENTIALS

    scheme, salt, hashed, iterations = _decode_password_hash(user["password_hash"])
    if scheme is None:
        return False, "Corrupted account record."

    if scheme == "pbkdf2":
        ok = hmac.compare_digest(_hash_pbkdf2(password, salt, iterations), hashed)
        if ok:
            return True, "Login successful."
        return False, WRONG_CREDENTIALS

    # Legacy salted-SHA-256 record — verify, then upgrade transparently.
    ok = hmac.compare_digest(_hash_sha256(password, salt), hashed)
    if ok:
        _upgrade_to_pbkdf2(username, password)
        return True, "Login successful."
    return False, WRONG_CREDENTIALS