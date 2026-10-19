"""Live interview synchronization endpoints."""

from fastapi import APIRouter, HTTPException, status
from fastapi import Request
from fastapi.responses import Response

from app.core import db
from api.schemas import (
    ApproveQuestionRequest,
    InterviewUpdateRequest,
    StartInterviewRequest,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])
_frames: dict[str, bytes] = {}


def _get_or_404(session_id: str) -> dict:
    interview = db.get_live_interview(session_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    return interview


@router.get("")
def list_live_interviews() -> list[dict]:
    return db.get_live_interviews()


@router.post("", status_code=status.HTTP_201_CREATED)
def start_interview(payload: StartInterviewRequest) -> dict:
    if db.get_live_interview(payload.session_id) is not None:
        raise HTTPException(status_code=409, detail="Session already exists.")
    db.start_live_interview(
        payload.session_id,
        payload.candidate_id,
        payload.candidate_name,
        payload.question,
        payload.question_index,
    )
    return _get_or_404(payload.session_id)


@router.get("/{session_id}")
def get_interview(session_id: str) -> dict:
    return _get_or_404(session_id)


@router.put("/{session_id}/frame", status_code=status.HTTP_204_NO_CONTENT)
async def upload_frame(session_id: str, request: Request) -> None:
    _get_or_404(session_id)
    frame = await request.body()
    if not frame or len(frame) > 400_000:
        raise HTTPException(status_code=400, detail="Invalid or oversized frame.")
    _frames[session_id] = frame


@router.get("/{session_id}/frame")
def download_frame(session_id: str) -> Response:
    _get_or_404(session_id)
    frame = _frames.get(session_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="No camera frame available.")
    return Response(content=frame, media_type="image/jpeg")


@router.patch("/{session_id}")
def update_interview(session_id: str, payload: InterviewUpdateRequest) -> dict:
    _get_or_404(session_id)
    fields = payload.database_fields()
    if not fields:
        raise HTTPException(status_code=400, detail="At least one update is required.")
    db.update_live_interview(session_id, **fields)
    return _get_or_404(session_id)


@router.post("/{session_id}/approve-question")
def approve_question(
    session_id: str, payload: ApproveQuestionRequest | None = None
) -> dict:
    interview = _get_or_404(session_id)
    if interview.get("pending_status") != "pending":
        raise HTTPException(status_code=409, detail="No pending question to approve.")
    db.approve_pending_question(
        session_id, payload.question if payload is not None else None
    )
    return _get_or_404(session_id)
