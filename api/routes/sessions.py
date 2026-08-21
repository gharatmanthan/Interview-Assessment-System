from fastapi import APIRouter
from api.schemas import SessionCreate, SessionResponse
from app.core import db
from app.core.models import InterviewSession

router = APIRouter()


@router.get("", response_model=list[SessionResponse])
def list_sessions():
    return db.get_all_sessions()


@router.post("", response_model=SessionResponse)
def create_session(req: SessionCreate):
    session = InterviewSession(
        session_id=req.session_id,
        candidate_name=req.candidate_name,
        job_title=req.job_title,
        job_id=req.job_id,
    )
    db.save_session(session)
    return SessionResponse(
        session_id=session.session_id,
        candidate_name=session.candidate_name,
        job_title=session.job_title,
        job_id=session.job_id,
        status="in_progress",
    )
