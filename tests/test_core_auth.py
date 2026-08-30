from app.core import db
from app.core.auth import register_recruiter, verify_recruiter, WRONG_CREDENTIALS


def test_register_creates_account_with_pbkdf2_hash(fresh_db):
    success, message = register_recruiter("alice", "secret123", "Alice")

    assert success is True
    assert message == "Account created."
    stored = db.get_recruiter_user("alice")
    assert stored["full_name"] == "Alice"
    algo, iterations, salt, hashed = stored["password_hash"].split("$")
    assert algo == "pbkdf2_sha256"
    assert int(iterations) >= 120_000
    assert len(salt) == 32
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
    assert message == WRONG_CREDENTIALS


def test_verify_unknown_username_uses_generic_message(fresh_db):
    success, message = verify_recruiter("ghost", "whatever")

    assert success is False
    assert message == WRONG_CREDENTIALS


def test_verify_corrupted_hash_record(fresh_db):
    from app.core.models import RecruiterUser

    db.save_recruiter_user(RecruiterUser(username="mallory", password_hash="no-salt-separator"))
    success, message = verify_recruiter("mallory", "anything")

    assert success is False
    assert message == "Corrupted account record."


def test_legacy_sha256_hash_still_verifies_and_upgrades(fresh_db):
    import hashlib
    import secrets

    from app.core.models import RecruiterUser

    salt = secrets.token_hex(8)
    stored = f"{salt}${hashlib.sha256((salt + 'secret123').encode()).hexdigest()}"
    db.save_recruiter_user(RecruiterUser(username="veteran", password_hash=stored))

    success, message = verify_recruiter("veteran", "secret123")
    assert success is True

    upgraded = db.get_recruiter_user("veteran")
    assert upgraded["password_hash"].startswith("pbkdf2_sha256$")
    assert verify_recruiter("veteran", "secret123")[0] is True


def test_legacy_sha256_hash_rejects_wrong_password(fresh_db):
    import hashlib
    import secrets

    from app.core.models import RecruiterUser

    salt = secrets.token_hex(8)
    stored = f"{salt}${hashlib.sha256((salt + 'secret123').encode()).hexdigest()}"
    db.save_recruiter_user(RecruiterUser(username="veteran", password_hash=stored))

    success, message = verify_recruiter("veteran", "wrongpass")
    assert success is False
    assert message == WRONG_CREDENTIALS


def test_same_password_produces_different_hashes(fresh_db):
    register_recruiter("alice", "shared-password")
    register_recruiter("bob", "shared-password")

    alice = db.get_recruiter_user("alice")["password_hash"]
    bob = db.get_recruiter_user("bob")["password_hash"]
    assert alice != bob
