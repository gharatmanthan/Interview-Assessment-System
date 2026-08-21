from app.core import db
from app.core.auth import register_recruiter, verify_recruiter


def test_register_creates_account_with_salted_hash(fresh_db):
    success, message = register_recruiter("alice", "secret123", "Alice")

    assert success is True
    assert message == "Account created."
    stored = db.get_recruiter_user("alice")
    assert stored["full_name"] == "Alice"
    salt, hashed = stored["password_hash"].split("$", 1)
    assert len(salt) == 16
    assert len(hashed) == 64


def test_register_rejects_duplicate_username(fresh_db):
    register_recruiter("alice", "secret123")
    success, message = register_recruiter("alice", "other456")

    assert success is False
    assert message == "That username is already taken."


def test_register_rejects_short_password(fresh_db):
    success, message = register_recruiter("bob", "abc")

    assert success is False
    assert message == "Password must be at least 6 characters."
    assert db.get_recruiter_user("bob") is None


def test_verify_correct_password(fresh_db):
    register_recruiter("alice", "secret123")
    success, message = verify_recruiter("alice", "secret123")

    assert success is True
    assert message == "Login successful."


def test_verify_wrong_password(fresh_db):
    register_recruiter("alice", "secret123")
    success, message = verify_recruiter("alice", "wrongpass")

    assert success is False
    assert message == "Incorrect password."


def test_verify_unknown_username(fresh_db):
    success, message = verify_recruiter("ghost", "whatever")

    assert success is False
    assert message == "No account with that username."


def test_verify_corrupted_hash_record(fresh_db):
    from app.core.models import RecruiterUser

    db.save_recruiter_user(RecruiterUser(username="mallory", password_hash="no-salt-separator"))
    success, message = verify_recruiter("mallory", "anything")

    assert success is False
    assert message == "Corrupted account record."


def test_same_password_produces_different_hashes(fresh_db):
    register_recruiter("alice", "shared-password")
    register_recruiter("bob", "shared-password")

    alice = db.get_recruiter_user("alice")["password_hash"]
    bob = db.get_recruiter_user("bob")["password_hash"]
    assert alice != bob
