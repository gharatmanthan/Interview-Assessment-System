from app.ui.candidate_entry_window import evaluate_invite_code


def make_candidate(status="invited"):
    return {
        "candidate_id": "cand-1",
        "job_id": "job-1",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "invite_code": "CODE123",
        "status": status,
        "session_id": None,
    }


def test_none_candidate_is_invalid():
    ok, message = evaluate_invite_code(None)
    assert ok is False
    assert message == "Invalid invite code"


def test_completed_candidate_rejected_with_exact_message():
    ok, message = evaluate_invite_code(make_candidate(status="completed"))
    assert ok is False
    assert message == "This interview has already been completed."


def test_expired_candidate_rejected():
    ok, message = evaluate_invite_code(make_candidate(status="expired"))
    assert ok is False
    assert message == "This invite code has expired."


def test_invited_candidate_is_valid():
    ok, message = evaluate_invite_code(make_candidate(status="invited"))
    assert ok is True
    assert message == ""


def test_in_progress_candidate_is_valid():
    ok, message = evaluate_invite_code(make_candidate(status="in_progress"))
    assert ok is True
