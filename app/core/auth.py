"""
Owner: Member C
Touches: this file, app/ui/login_window.py

Simple recruiter auth — salted SHA-256 hashing (fine for a final-year
project; not claiming production-grade security here, and that's worth
saying plainly in your report rather than overclaiming).
"""
import hashlib
import secrets

from app.core import db


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def register_recruiter(username: str, password: str, full_name: str = "") -> tuple:
    """Returns (success: bool, message: str)."""
    from app.core.models import RecruiterUser

    if db.get_recruiter_user(username):
        return False, "That username is already taken."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    salt = secrets.token_hex(8)
    stored_hash = f"{salt}${_hash_password(password, salt)}"

    db.save_recruiter_user(RecruiterUser(
        username=username, password_hash=stored_hash, full_name=full_name
    ))
    return True, "Account created."


def verify_recruiter(username: str, password: str) -> tuple:
    """Returns (success: bool, message: str)."""
    user = db.get_recruiter_user(username)
    if not user:
        return False, "No account with that username."

    try:
        salt, hashed = user["password_hash"].split("$", 1)
    except ValueError:
        return False, "Corrupted account record."

    if _hash_password(password, salt) != hashed:
        return False, "Incorrect password."

    return True, "Login successful."
