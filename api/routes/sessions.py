import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from api.deps import get_current_recruiter, require_interview_session
from api.schemas import SessionCreate, SessionResponse
from app.core import db
from app.core.models import InterviewSession

router = APIRouter()

# Recordings land under data/uploads/<session_id>/ and are served back at
# /media/<session_id>/<file> (see the StaticFiles mount in main.py). Paths
# stored in the sessions table are relative to data/uploads so they stay
# valid both on the local sidecar and on a deployed central server.
UPLOADS_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"

# Live-monitor preview frames: data/live_frames/<session_id>.jpg. Disk-only,
# one file per active session, overwritten in place on every upload — this is
# a low-stakes preview (the permanent recording goes to UPLOADS_DIR), so no
# atomic-replace dance is needed here.
LIVE_FRAMES_DIR = Path(__file__).parent.parent.parent / "data" / "live_frames"

# Upload hardening: recordings (video+audio together) may legitimately be tens
# of megabytes for a long interview; cap each file and the combined total so an
# accidental giant upload can't exhaust disk. Live frames are one small JPEG.
MAX_RECORDING_FILE_BYTES = 256 * 1024 * 1024
MAX_RECORDING_TOTAL_BYTES = 512 * 1024 * 1024
MAX_LIVE_FRAME_BYTES = 2 * 1024 * 1024

SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def _safe_name(filename: str) -> str:
    name = SAFE_FILENAME.sub("_", Path(filename).name or "recording.bin")
    return name


def live_frame_path(session_id: str) -> Path:
    # session_id comes straight off the URL — neutralize traversal before it
    # can escape live_frames/.
    safe = SAFE_FILENAME.sub("_", session_id)
    return LIVE_FRAMES_DIR / f"{safe}.jpg"


def delete_live_frame(session_id: str) -> None:
    """Best-effort cleanup; a racing late upload simply recreates the file."""
    try:
        live_frame_path(session_id).unlink(missing_ok=True)
    except OSError:
        pass


@router.get("", response_model=list[SessionResponse])
def list_sessions(username: str = Depends(get_current_recruiter)):
    """Owned sessions only (derived from the candidate's job ownership)."""
    return db.get_owned_sessions(username)


@router.post("", response_model=SessionResponse)
def create_session(req: SessionCreate, username: str = Depends(get_current_recruiter)):
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


@router.post("/{session_id}/upload")
async def upload_recording(
    session_id: str,
    video: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    x_interview_token: str = Header(default=""),
):
    """Accept a candidate's locally recorded webcam/mic files.

    In remote mode the recording is made on the candidate's machine, so the
    file has to travel to the central server explicitly — there is no shared
    disk for the API to read from. Works identically against the local
    sidecar in local mode.

    Authenticated by the candidate's X-Interview-Token; the session must
    belong to that candidate.
    """
    require_interview_session(session_id, x_interview_token)
    if video is None and audio is None:
        raise HTTPException(status_code=400, detail="No file provided (expected 'video' and/or 'audio')")

    sessions = db.get_all_sessions()
    session = next((s for s in sessions if s["session_id"] == session_id), None)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # The session id comes off the URL — neutralize traversal before it can
    # escape data/uploads/ and keep the stored rel path consistent with the
    # on-disk directory.
    safe_session = SAFE_FILENAME.sub("_", session_id)
    target_dir = UPLOADS_DIR / safe_session
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_fields: dict[str, str] = {}
    total_size = 0

    for field, upload in (("video_path", video), ("audio_path", audio)):
        if upload is None:
            continue
        dest = target_dir / _safe_name(upload.filename or f"{field}.bin")
        size = 0
        with open(dest, "wb") as f:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                total_size += len(chunk)
                if size > MAX_RECORDING_FILE_BYTES or total_size > MAX_RECORDING_TOTAL_BYTES:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail="Recording exceeds the upload size limit.",
                    )
                f.write(chunk)
        if size == 0:
            continue
        rel_path = f"{safe_session}/{dest.name}"
        saved_fields[field] = rel_path

    if not saved_fields:
        raise HTTPException(status_code=400, detail="Uploaded file(s) were empty")

    db.update_session(session_id, **saved_fields)
    return {"success": True, "saved": saved_fields}


@router.post("/{session_id}/live-frame")
async def upload_live_frame(
    session_id: str,
    request: Request,
    x_interview_token: str = Header(default=""),
):
    """Accept one preview frame (raw JPEG body) from the candidate's app.

    Called every ~1.5s while their interview is in progress. Deliberately
    does NOT require the session to exist in the DB and never touches it:
    this is fire-and-forget from the client, and a late frame arriving just
    after completion must be silently tolerated (it merely recreates the
    file, which a later sweep or the recruiter's poll cycle ignores).

    Authenticated by the candidate's X-Interview-Token; the session must
    belong to that candidate.
    """
    require_interview_session(session_id, x_interview_token)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty frame body")
    if len(body) > MAX_LIVE_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="Live frame exceeds size limit")

    dest = live_frame_path(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "wb") as f:
            f.write(body)
    except OSError:
        # Disk hiccup mid-write: skip this frame, the next tick re-sends.
        raise HTTPException(status_code=503, detail="Frame write failed")

    return {"success": True}


@router.get("/{session_id}/live-frame")
def get_live_frame(session_id: str, username: str = Depends(get_current_recruiter)):
    path = live_frame_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No live frame for session")
    return FileResponse(path, media_type="image/jpeg")
