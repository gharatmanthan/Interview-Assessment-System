import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException

from api.rate_limit import rate_limited
from api.schemas import (
    SessionResponse,
    ValidateCodeRequest,
    ConsentRequest,
    StartSessionRequest,
    SubmitAnswerRequest,
    CompleteSessionRequest,
    CandidateQuestionsResponse,
    CandidateProgressResponse,
    QuestionItem,
)
from app.core import db
from app.core.models import InterviewSession
from app.core.tokens import create_interview_token, verify_interview_token

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_question_item(q: dict) -> QuestionItem:
    """Map a session_questions row to the QuestionItem API shape (used by both
    the locked-set listing and the server-authoritative progress endpoint)."""
    return QuestionItem(
        question_index=q["question_index"],
        question_id=q["question_id"],
        question_text=q["question_text"],
        category=q["category"],
        competency=q["competency"],
        difficulty=q["difficulty"],
        source=q["source"],
    )


def _interview_progress(session_id: str) -> dict:
    """Derive the server-authoritative Mode 2 interview progress for a session.

    A question counts as ANSWERED when it has a persisted competency score
    (scoring is the step that advances the interview). The current question is
    the first locked question, in question_index order, without a score. This
    makes the interview state machine refresh-proof and independent of any
    client-held position — and it reuses the existing session_questions +
    competency_scores tables (no new schema).
    """
    questions = db.get_session_questions(session_id)
    answered = {s["question_id"] for s in db.get_session_scores(session_id)}
    total = len(questions)
    answered_count = sum(1 for q in questions if q["question_id"] in answered)

    # Order by question_index (get_session_questions already orders by it).
    current = None
    for q in questions:
        if q["question_id"] not in answered:
            current = q
            break

    completed = total > 0 and answered_count == total

    if answered_count == total and total > 0:
        status = "completed"
    elif answered_count > 0:
        status = "in_progress"
    elif total > 0:
        status = "ready"
    else:
        status = "not_ready"

    return {
        "total_questions": total,
        "answered_questions": answered_count,
        "remaining_questions": total - answered_count,
        "current_question": _to_question_item(current) if current else None,
        "interview_status": status,
        "completed": completed,
    }


def _invite_status(candidate: dict) -> tuple[bool, str]:
    """Cross-check the candidate's interview invites: expired/consumed
    invites invalidate the code even if the candidate row still says 'invited'.
    """
    invites = db.get_interview_invites_for_candidate(candidate["candidate_id"])
    for invite in invites:
        if invite["status"] == "expired":
            return False, "This invite has expired"
        if invite["status"] == "consumed":
            return False, "This invite has already been used"
    return True, ""


def _screening_eligible(candidate: dict) -> bool:
    """Candidates linked to an application may interview only while their
    latest screening decision is 'passed'. Manual candidates (no linked
    application) are always eligible — the recruiter judged them directly."""
    application_id = candidate.get("application_id")
    if not application_id:
        return True
    result = db.get_screening_result(application_id)
    return bool(result and result.get("decision") == "passed")


@router.post("/candidate/validate-code", dependencies=[Depends(rate_limited("invite_code"))])
def validate_invite_code(req: ValidateCodeRequest):
    code = req.invite_code.strip()
    if not code:
        return {"valid": False, "message": "No invite code provided"}

    candidate = db.get_candidate_by_invite_code(code)
    if not candidate:
        return {"valid": False, "message": "Invalid invite code"}

    ok, message = _invite_status(candidate)
    if not ok:
        return {"valid": False, "message": message}

    if candidate.get("status") == "completed":
        return {"valid": False, "message": "This interview has already been completed"}

    if candidate.get("status") == "expired":
        return {"valid": False, "message": "This invite code has expired"}

    # Re-check screening eligibility on every validation instead of trusting a
    # decision taken when the invite was issued.
    if not _screening_eligible(candidate):
        return {"valid": False, "message": "Your application no longer qualifies for this interview"}

    job = db.get_job_posting(candidate["job_id"])
    if not job:
        return {"valid": False, "message": "Invalid invite code"}

    # Bind this validated invite to a short-lived, purpose-scoped token so
    # later steps (consent / start-session) derive identity server-side.
    token, exp = create_interview_token(candidate["candidate_id"], job["job_id"])

    # Do not echo the raw invite code back to the browser; it is bearer.
    safe_candidate = {k: v for k, v in candidate.items() if k != "invite_code"}

    return {
        "valid": True,
        "candidate": safe_candidate,
        "job": job,
        "interview_token": token,
        "expires_at": datetime.fromtimestamp(exp).isoformat(),
    }


def _identity_from_token(req) -> tuple[str, str]:
    """Derive (candidate_id, job_id) from the signed interview token. The
    client-supplied candidate_id/job_id are ignored for security purposes so a
    peeked/edited request cannot impersonate another candidate."""
    if not req.interview_token:
        raise HTTPException(
            status_code=401,
            detail="Interview access token is required. Please re-enter your invite code.",
        )
    identity = verify_interview_token(req.interview_token)
    if not identity:
        raise HTTPException(
            status_code=401,
            detail="Interview access token is missing, invalid, or expired. Please re-enter your invite code.",
        )
    return identity


def _require_token_owns_session(req) -> tuple[str, str]:
    """Require the interview token to be valid AND bound to the session in the
    request. Guards candidate-scoring endpoints (submit-answer, complete-session)
    against cross-candidate/arbitrary-session writes."""
    candidate_id, job_id = _identity_from_token(req)
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")
    if candidate.get("session_id") != req.session_id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to this candidate.",
        )
    return candidate_id, job_id


@router.post("/candidate/consent")
def record_consent(req: ConsentRequest):
    candidate_id, job_id = _identity_from_token(req)

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")

    job = db.get_job_posting(job_id)
    job_title = job["title"] if job else ""

    # The session id is resolved server-side and is authoritative; the client
    # must never dictate it. The device-check and interview pages then use the
    # returned session_id, and the ownership checks across all candidate
    # endpoints rely on candidate.session_id being set to this same value.
    try:
        session_id = db.resolve_or_create_session(
            candidate_id, job_id, candidate["name"], job_title
        )
    except db.SessionResolutionError:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")

    db.update_candidate_status(candidate_id, "in_progress", session_id=session_id)
    return {"success": True, "session_id": session_id}


@router.post("/candidate/start-session", response_model=SessionResponse)
def start_candidate_session(req: StartSessionRequest):
    candidate_id, job_id = _identity_from_token(req)

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")
    candidate_name = candidate["name"]

    # F-01: an already-completed interview must never be reopened. Manually
    # created candidates do not necessarily have an interview_invites row, so
    # _invite_status() below is NOT a sufficient guard for them. Check the
    # server-authoritative states directly (candidate.status and the candidate's
    # authoritative session.status) and reject BEFORE touching any state — no
    # new session, no status flip, no completed_at clearing.
    authoritative_session = db.get_session_for_candidate(candidate_id)
    if candidate.get("status") == "completed" or (
        authoritative_session and authoritative_session.get("status") == "completed"
    ):
        raise HTTPException(
            status_code=409,
            detail="This interview has already been completed and cannot be reopened.",
        )

    job = db.get_job_posting(job_id)
    if not job:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")
    job_title = job["title"]

    # Preserve one-time-use semantics: an already used/expired invite cannot
    # start a second session even with a still-valid token.
    ok, message = _invite_status(candidate)
    if not ok:
        raise HTTPException(status_code=409, detail=message)

    # Screening eligibility can change after the token was issued (re-screen).
    if not _screening_eligible(candidate):
        raise HTTPException(
            status_code=409,
            detail="Your application no longer qualifies for this interview",
        )

    # Resolve (or create) the single authoritative session for this candidate.
    # The user-supplied req.session_id is ignored for authority: if the
    # candidate already has a session (e.g. the recruiter started first, or a
    # previous start attempt), the existing session_id is returned unchanged so
    # recruiter and candidate always share the same InterviewSession.
    try:
        session_id = db.resolve_or_create_session(
            candidate_id, job_id, candidate_name, job_title
        )
    except db.SessionResolutionError:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")

    session_row = db.get_session(session_id)
    if session_row is None:
        # Defensive: the resolver always materializes a row, but if a race
        # leaves us pointing at a missing one, treat it as an auth failure
        # rather than crashing on an unhashable/None payload.
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")
    session = InterviewSession(**session_row)
    session.status = "in_progress"
    db.save_session(session)

    db.update_candidate_status(candidate_id, "in_progress", session_id=session_id)

    # Consume the interview invite: a session start is one-time use.
    for invite in db.get_interview_invites_for_candidate(candidate_id):
        if invite["status"] == "active":
            db.consume_interview_invite(invite["id"])
            break

    return SessionResponse(
        session_id=session.session_id,
        candidate_name=session.candidate_name,
        job_title=session.job_title,
        job_id=session.job_id,
        started_at=str(session.started_at),
        status=session.status,
    )


@router.post("/candidate/submit-answer")
def submit_answer(req: SubmitAnswerRequest):
    from app.engine.scoring import score_answer
    from app.engine.explainability import explain_score
    from app.engine.fairness import audit_bias
    from app.engine.rag import retrieve_rubric

    _require_token_owns_session(req)

    # The submitted question_id MUST belong to this session's locked question
    # set — a candidate can never score a question from another candidate's
    # session or a fabricated id. This applies whenever a Mode 2 locked set
    # exists (which is always the case for a real interview); a session with no
    # locked set at all is a degenerate legacy case that retains prior behavior.
    if db.session_questions_exist(req.session_id):
        question = db.get_session_question_by_id(req.session_id, req.question_id)
        if not question:
            raise HTTPException(
                status_code=403,
                detail="Question does not belong to this interview.",
            )

    # Persist the transcript so it is never lost and so a typed-answer fallback
    # lands in question_transcripts too. Idempotent upsert on (session_id,
    # question_id) — a retry after a scoring failure cannot duplicate it.
    db.save_question_transcript(req.session_id, req.question_id, req.transcript)

    # Ground rubric retrieval in the ACTUAL job description for this session so
    # RAG/LLM scoring receives the real JD context + competency rubric, matching
    # the recruiter-side scoring path (not a generic fallback).
    job_title, jd_text = _job_context(req.session_id)
    rubric = retrieve_rubric(job_title or req.category, req.category, jd_text)

    score_result = score_answer(req.session_id, req.question_id, req.category, req.transcript, rubric)
    explanation = explain_score(req.session_id, req.question_id, req.transcript, score_result.score)
    fairness = audit_bias(req.session_id, req.question_id, req.transcript, score_result.score)

    db.save_competency_score(score_result)
    db.save_explanation(explanation)

    if fairness:
        db.save_fairness_flag(fairness)

    return {
        "score": {
            "session_id": req.session_id,
            "question_id": req.question_id,
            "category": req.category,
            "score": score_result.score,
            "confidence": score_result.confidence,
        },
        "explanation": {
            "session_id": req.session_id,
            "question_id": req.question_id,
            "summary": explanation.summary,
            "supporting_phrases": explanation.supporting_phrases,
        },
        "fairness": {
            "session_id": req.session_id,
            "question_id": req.question_id,
            "score_delta": fairness.score_delta if fairness else 0,
            "note": fairness.note if fairness else "",
        } if fairness else None,
    }


def _job_context(session_id: str) -> tuple[str, str]:
    """Best-effort lookup of (job_title, job_description) for RAG retrieval —
    mirrors the recruiter-side scoring path (api/routes/scoring.py)."""
    session = db.get_session(session_id)
    if not session:
        return "", ""
    job = db.get_job_posting(session.get("job_id")) if session.get("job_id") else None
    if not job:
        return session.get("job_title") or "", ""
    description = job.get("description", "")
    required_skills = job.get("required_skills", [])
    if required_skills and description:
        description = "Required skills: " + ", ".join(required_skills) + "\n\n" + description
    return job.get("title") or "", description


@router.post("/candidate/complete-session")
def complete_session(req: CompleteSessionRequest):
    session_id = req.session_id
    if not session_id:
        return {"success": False, "message": "Missing session_id"}

    _require_token_owns_session(req)

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Server-authoritative completion: the candidate cannot mark the interview
    # completed unless EVERY locked question has been scored. This prevents a
    # forged completion (e.g. skipping questions) by a partially-finished
    # candidate, and doubles as the "final question submitted -> COMPLETED"
    # transition once the last answer lands.
    progress = _interview_progress(session_id)
    if progress["total_questions"] > 0 and not progress["completed"]:
        raise HTTPException(
            status_code=409,
            detail="Interview cannot be completed until every question has been answered.",
        )

    session["status"] = "completed"
    session["completed_at"] = datetime.now().isoformat()
    db.save_session(InterviewSession(**session))

    candidates = db.get_all_candidates()
    candidate = next(
        (c for c in candidates if c.get("session_id") == session_id), None
    )
    if candidate:
        db.update_candidate_status(candidate["candidate_id"], "completed")

    # Interview-mode routing: a Mode 2 candidate's completion may close the
    # job's Mode 2 cohort. When every Mode 2 candidate has finished, the cohort
    # is ranked and the top LIVE_INTERVIEW_CAPACITY are promoted to Mode 1
    # (notifications cached on outbox, never sent inline here). Atomic/safe:
    # ranking is idempotent and a failure must never break session completion.
    if candidate and candidate.get("interview_mode") == "MODE_2":
        try:
            from app.screening.routing import on_mode2_candidate_completed

            on_mode2_candidate_completed(
                candidate["job_id"], candidate["candidate_id"]
            )
        except Exception as exc:  # pragma: no cover - defensive only
            logger.error(
                "mode 2 cohort ranking failed for candidate %s: %s",
                candidate["candidate_id"],
                exc,
            )

    # The real recording is (or will shortly be) in Reports — drop the stale
    # live-preview frame so the monitor shows the feed as ended. A frame
    # upload racing this moment just recreates the file harmlessly.
    from api.routes.sessions import delete_live_frame

    delete_live_frame(session_id)

    return {"success": True}


@router.get("/candidate/questions", response_model=CandidateQuestionsResponse)
def get_candidate_questions(
    x_interview_token: str = Header(default=""),
):
    """Retrieve the locked question set for the candidate's session.

    Auth: X-Interview-Token — derives candidate_id/job_id from the token,
    resolves the authoritative session, and returns only that session's
    questions.
    """
    identity = verify_interview_token(x_interview_token)
    if not identity:
        raise HTTPException(status_code=401, detail="Invalid interview token.")
    candidate_id, job_id = identity

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Invalid interview token.")

    session_id = candidate.get("session_id")
    if not session_id:
        raise HTTPException(status_code=404, detail="No active session found.")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    questions = db.get_session_questions(session_id)
    if not questions:
        raise HTTPException(
            status_code=404,
            detail="No questions have been prepared for this interview yet. "
                   "Please wait for the recruiter.",
        )

    return CandidateQuestionsResponse(
        session_id=session_id,
        questions=[_to_question_item(q) for q in questions],
    )


@router.get("/candidate/progress", response_model=CandidateProgressResponse)
def get_candidate_interview_progress(
    x_interview_token: str = Header(default=""),
):
    """Server-authoritative Mode 2 interview progress for the authenticated
    candidate. Powers refresh/reconnect recovery: the candidate restores their
    current question from here, never from browser sessionStorage. A refresh
    immediately after the interview loads / after each submit returns the true
    server position.

    Auth: X-Interview-Token — derives candidate_id/job_id and resolves the
    candidate's authoritative session.
    """
    identity = verify_interview_token(x_interview_token)
    if not identity:
        raise HTTPException(status_code=401, detail="Invalid interview token.")
    candidate_id, job_id = identity

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Invalid interview token.")

    session_id = candidate.get("session_id")
    if not session_id:
        raise HTTPException(status_code=404, detail="No active session found.")

    # An already-completed interview stays completed — the candidate cannot
    # restart or re-enter a finished interview through progress.
    session = db.get_session(session_id)
    if session and session.get("status") == "completed":
        return CandidateProgressResponse(
            session_id=session_id,
            interview_status="completed",
            total_questions=len(db.get_session_questions(session_id)),
            answered_questions=len(db.get_session_questions(session_id)),
            remaining_questions=0,
            current_question=None,
            completed=True,
        )

    p = _interview_progress(session_id)
    return CandidateProgressResponse(
        session_id=session_id,
        interview_status=p["interview_status"],
        total_questions=p["total_questions"],
        answered_questions=p["answered_questions"],
        remaining_questions=p["remaining_questions"],
        current_question=p["current_question"],
        completed=p["completed"],
    )