"""
Question engine API routes (recruiter side).

  POST /api/questions/select  — generate/select + lock a question set for a session.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_recruiter
from api.schemas import SelectQuestionsRequest, SelectQuestionsResponse, QuestionItem
from app.core import db
from app.engine.question_selector import select_questions

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_recruiter_owns_session(username: str, session_id: str) -> dict:
    """Verify the recruiter owns the candidate/job/session. Returns session row."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    job_id = session.get("job_id")
    if job_id:
        job = db.get_job_posting(job_id)
        if not job or job.get("created_by") != username:
            raise HTTPException(
                status_code=403,
                detail="You do not own this session's job.",
            )

    candidates = db.get_all_candidates()
    owner_candidate = None
    for c in candidates:
        if c.get("session_id") == session_id:
            owner_candidate = c
            break

    if owner_candidate:
        job_of_candidate = db.get_job_posting(owner_candidate.get("job_id", ""))
        if job_of_candidate and job_of_candidate.get("created_by") != username:
            raise HTTPException(
                status_code=403,
                detail="You do not own this candidate.",
            )

    return session


@router.post("/select", response_model=SelectQuestionsResponse)
def select_session_questions(
    req: SelectQuestionsRequest,
    username: str = Depends(get_current_recruiter),
):
    """Generate/select questions and lock them to the session.

    Once locked, the question set is immutable — refreshes return the same
    questions.  The recruiter may re-lock BEFORE the interview starts by
    calling this endpoint again (replaces the set).
    """
    _verify_recruiter_owns_session(username, req.session_id)

    session = db.get_session(req.session_id)
    job_id = session.get("job_id") if session else None
    job = db.get_job_posting(job_id) if job_id else None
    job_description = (job or {}).get("description", "")
    required_skills = (job or {}).get("required_skills", [])

    if required_skills and job_description:
        skills_text = "Required skills: " + ", ".join(required_skills) + "\n\n"
        job_description = skills_text + job_description

    questions = select_questions(
        job_description=job_description,
        num_questions=req.num_questions,
        force_generated=req.force_generated,
    )

    session_questions = []
    for i, q in enumerate(questions):
        session_questions.append({
            "question_index": i,
            "question_id": q["question_id"],
            "question_text": q["question_text"],
            "category": q.get("category", ""),
            "competency": q.get("competency", ""),
            "difficulty": q.get("difficulty", "medium"),
            "source": q.get("source", "bank"),
        })

    db.save_session_questions(req.session_id, session_questions)

    logger.info(
        "select_session_questions: session=%s locked %d questions",
        req.session_id, len(session_questions),
    )

    return SelectQuestionsResponse(
        session_id=req.session_id,
        questions=[QuestionItem(**q) for q in session_questions],
        locked=True,
    )
