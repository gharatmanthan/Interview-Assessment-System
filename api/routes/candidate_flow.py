import secrets
from fastapi import APIRouter
from api.schemas import SessionResponse
from app.core import db
from app.core.models import Candidate, InterviewSession
from datetime import datetime

router = APIRouter()


@router.post("/candidate/validate-code")
def validate_invite_code(body: dict):
    code = body.get("invite_code", "").strip()
    if not code:
        return {"valid": False, "message": "No invite code provided"}

    candidates = db.get_all_candidates()
    candidate = next((c for c in candidates if c["invite_code"] == code), None)

    if not candidate:
        return {"valid": False, "message": "Invalid invite code"}

    if candidate.get("status") == "completed":
        return {"valid": False, "message": "This interview has already been completed"}

    if candidate.get("status") == "expired":
        return {"valid": False, "message": "This invite code has expired"}

    jobs = db.get_all_job_postings()
    job = next((j for j in jobs if j["job_id"] == candidate["job_id"]), None)

    return {
        "valid": True,
        "candidate": candidate,
        "job": job,
    }


@router.post("/candidate/consent")
def record_consent(body: dict):
    session_id = body.get("session_id")
    candidate_id = body.get("candidate_id")
    if not session_id or not candidate_id:
        return {"success": False, "message": "Missing required fields"}

    db.update_candidate_status(candidate_id, "in_progress")
    return {"success": True}


@router.post("/candidate/start-session", response_model=SessionResponse)
def start_candidate_session(body: dict):
    session_id = body.get("session_id")
    candidate_id = body.get("candidate_id")
    job_id = body.get("job_id")

    candidates = db.get_all_candidates()
    candidate = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
    candidate_name = candidate["name"] if candidate else "Unknown"

    jobs = db.get_all_job_postings()
    job = next((j for j in jobs if j["job_id"] == job_id), None)
    job_title = job["title"] if job else "Unknown"

    session = InterviewSession(
        session_id=session_id,
        candidate_name=candidate_name,
        job_title=job_title,
        job_id=job_id,
        started_at=datetime.now().isoformat(),
        status="in_progress",
    )
    db.save_session(session)

    db.update_candidate_status(candidate_id, "in_progress", session_id=session_id)

    return SessionResponse(
        session_id=session.session_id,
        candidate_name=session.candidate_name,
        job_title=session.job_title,
        job_id=session.job_id,
        started_at=session.started_at,
        status=session.status,
    )


@router.post("/candidate/submit-answer")
def submit_answer(body: dict):
    from app.engine.scoring import score_answer
    from app.engine.explainability import explain_score
    from app.engine.fairness import audit_bias
    from app.engine.rag import retrieve_rubric

    session_id = body.get("session_id")
    question_id = body.get("question_id")
    category = body.get("category")
    transcript = body.get("transcript")

    rubric = retrieve_rubric("general", category)
    score_result = score_answer(session_id, question_id, category, transcript, rubric)
    explanation = explain_score(session_id, question_id, transcript, score_result.score)
    fairness = audit_bias(session_id, question_id, transcript, score_result.score)

    from app.core.models import CompetencyScore, ExplanationItem, FairnessFlag

    db.save_competency_score(score_result)
    db.save_explanation(explanation)

    if fairness:
        db.save_fairness_flag(fairness)

    return {
        "score": {
            "session_id": session_id,
            "question_id": question_id,
            "category": category,
            "score": score_result.score,
            "confidence": score_result.confidence,
        },
        "explanation": {
            "session_id": session_id,
            "question_id": question_id,
            "summary": explanation.summary,
            "supporting_phrases": explanation.supporting_phrases,
        },
        "fairness": {
            "session_id": session_id,
            "question_id": question_id,
            "score_delta": fairness.score_delta if fairness else 0,
            "note": fairness.note if fairness else "",
        } if fairness else None,
    }


@router.post("/candidate/complete-session")
def complete_session(body: dict):
    session_id = body.get("session_id")
    if not session_id:
        return {"success": False, "message": "Missing session_id"}

    sessions = db.get_all_sessions()
    session = next((s for s in sessions if s["session_id"] == session_id), None)
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
