from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.rate_limit import rate_limited
from api.schemas import (
    SessionResponse,
    ValidateCodeRequest,
    ConsentRequest,
    StartSessionRequest,
    SubmitAnswerRequest,
    CompleteSessionRequest,
)
from app.core import db
from app.core.models import InterviewSession
from app.core.tokens import create_interview_token, verify_interview_token

router = APIRouter()


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
    if not req.session_id:
        return {"success": False, "message": "Missing required fields"}

    candidate_id, job_id = _identity_from_token(req)

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")

    # Bind the session to the candidate now (the device-check and interview
    # pages post integrity flags / answers for this session before any
    # start-session call): the ownership checks across all candidate endpoints
    # rely on candidate.session_id being set from consent onward.
    db.update_candidate_status(candidate_id, "in_progress", session_id=req.session_id)
    return {"success": True}


@router.post("/candidate/start-session", response_model=SessionResponse)
def start_candidate_session(req: StartSessionRequest):
    candidate_id, job_id = _identity_from_token(req)

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        raise HTTPException(status_code=401, detail="Interview access token is invalid.")
    candidate_name = candidate["name"]

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

    session = InterviewSession(
        session_id=req.session_id,
        candidate_name=candidate_name,
        job_title=job_title,
        job_id=job_id,
        started_at=datetime.now().isoformat(),
        status="in_progress",
    )
    db.save_session(session)

    db.update_candidate_status(candidate_id, "in_progress", session_id=req.session_id)

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
        started_at=session.started_at,
        status=session.status,
    )


@router.post("/candidate/submit-answer")
def submit_answer(req: SubmitAnswerRequest):
    from app.engine.scoring import score_answer
    from app.engine.explainability import explain_score
    from app.engine.fairness import audit_bias
    from app.engine.rag import retrieve_rubric

    _require_token_owns_session(req)

    rubric = retrieve_rubric("general", req.category)
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


@router.post("/candidate/complete-session")
def complete_session(req: CompleteSessionRequest):
    session_id = req.session_id
    if not session_id:
        return {"success": False, "message": "Missing session_id"}

    _require_token_owns_session(req)

    session = db.get_session(session_id)
    if session:
        session["status"] = "completed"
        session["completed_at"] = datetime.now().isoformat()
        db.save_session(InterviewSession(**session))

        if session.get("job_id"):
            candidates = db.get_all_candidates()
            candidate = next(
                (c for c in candidates if c.get("session_id") == session_id), None
            )
            if candidate:
                db.update_candidate_status(candidate["candidate_id"], "completed")

    # The real recording is (or will shortly be) in Reports — drop the stale
    # live-preview frame so the monitor shows the feed as ended. A frame
    # upload racing this moment just recreates the file harmlessly.
    from api.routes.sessions import delete_live_frame

    delete_live_frame(session_id)

    return {"success": True}