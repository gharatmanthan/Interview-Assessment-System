"""
Signed media serving.

Replaces the wide-open StaticFiles /media mount: files are only served when
the URL carries a short-lived HMAC signature issued to an authenticated
recruiter. Guards against path traversal by resolving inside the media
roots (interview recordings under data/uploads, resumes under data/resumes).
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from api.deps import get_current_recruiter
from app.core.paths import get_uploads_dir, get_resumes_dir
from app.core.tokens import create_media_token, verify_media_token

router = APIRouter()

# Module-level variables that can be monkeypatched in tests
MEDIA_DIR = get_uploads_dir()
RESUMES_DIR = get_resumes_dir()


def media_roots():
    return [MEDIA_DIR.resolve(), RESUMES_DIR.resolve()]


def to_relative_media_path(path: str) -> str:
    """Turn an absolute stored file path (e.g. the resume_path persisted from
    disk) into a portable path relative to a signed-media root. Files already
    relative — and anything outside the roots — are returned untouched."""
    try:
        p = Path(path)
        if not p.is_absolute():
            return path
        for root in media_roots():
            try:
                return p.resolve().relative_to(root).as_posix()
            except (ValueError, OSError):
                continue
    except Exception:
        pass
    return path


def _owns_media_path(path: str, username: str) -> bool:
    """A recruiter may sign media only for data belonging to a job they own.

    Recording uploads live at <session_id>/<file>; the session's job gives the
    ownership root. Flat resume files are matched against the applications and
    candidates that reference them (the on-disk name embeds the job id for the
    apply portal). Anything unmatchable is denied.
    """
    from app.core import db

    rel = path.lstrip("/")
    first, sep, _ = rel.partition("/")
    if sep:
        session = db.get_session(first)
        if not session or not session.get("job_id"):
            return False
        return db.job_owned_by(session["job_id"], username)

    candidates = db.get_all_candidates()
    applications = db.get_all_applications()
    for row in [*applications, *candidates]:
        stored = row.get("resume_path") or ""
        if not stored:
            continue
        if to_relative_media_path(stored) == rel and db.job_owned_by(row["job_id"], username):
            return True
    return False


@router.get("/sign")
def sign_media(
    path: str = Query(..., description="Media path relative to a media root, e.g. uploads/<session>/<file>"),
    username: str = Depends(get_current_recruiter),
):
    """Issue a short-lived signed URL for a media path the recruiter owns."""
    if not _owns_media_path(path, username):
        raise HTTPException(status_code=403, detail="You do not have access to that media.")
    sig, exp = create_media_token(path)
    return {"url": f"/media/{path.replace('^/', '')}?sig={sig}&exp={exp}"}


def _resolve_media(path: str) -> Path:
    """Resolve a signed path inside the media roots. Anything that escapes
    every root (traversal) or is missing yields 404 — nothing outside the
    roots is ever served."""
    for root in media_roots():
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            continue
        if candidate.is_file():
            return candidate
    raise HTTPException(status_code=404, detail="Not found.")


def serve_media_file(path: str, sig: str = "", exp: str = ""):
    if not verify_media_token(path, sig, exp):
        raise HTTPException(status_code=403, detail="Invalid or expired media link.")
    target = _resolve_media(path)
    return FileResponse(str(target), media_type="application/octet-stream")