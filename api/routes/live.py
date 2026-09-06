"""Phase 3A: MODE 1 live interview WebSocket.

One authoritative session per interview. This endpoint wires the recruiter and
the candidate onto the SAME session (derived server-side, never trusted from
the client) and relays:

  recruiter -> ask_question -> candidate
  recruiter -> end_interview -> both
  candidate -> answer_completed -> recruiter (reading question_transcripts)
  connection status to both sides (reconnect/refresh.)

Authentication mirrors the integrity WebSocket: the connecting party passes a
token via ?token=... (browsers cannot set headers on WebSocket upgrades). The
token resolves unambiguously to exactly ONE role:

  * a recruiter Bearer token  -> verify_token()   -> role=recruiter
  * a candidate interview token -> verify_interview_token() -> role=candidate

`verify_token` rejects tokens typed as "interview", and
`verify_interview_token` requires typ == "interview", so a single token can
never be interpreted as both roles.

Every event is validated against the server-side identity — the role and
session are derived, never supplied by the client message.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import db
from app.core.tokens import verify_interview_token, verify_token

logger = logging.getLogger(__name__)

router = APIRouter()

_ROLE_RECRUITER = "recruiter"
_ROLE_CANDIDATE = "candidate"


class LiveManager:
    """Registry of connected sockets per session.

    session_conns[session_id] = {"recruiter": {ws}, "candidate": {ws}}
    """

    def __init__(self) -> None:
        self._session_conns: dict[str, dict[str, set]] = {}

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._session_conns

    def join(self, session_id: str, role: str, ws: WebSocket) -> None:
        bucket = self._session_conns.setdefault(
            session_id, {_ROLE_RECRUITER: set(), _ROLE_CANDIDATE: set()}
        )
        bucket[role].add(ws)

    def leave(self, session_id: str, role: str, ws: WebSocket) -> None:
        bucket = self._session_conns.get(session_id)
        if not bucket:
            return
        bucket[role].discard(ws)
        if not bucket[_ROLE_RECRUITER] and not bucket[_ROLE_CANDIDATE]:
            self._session_conns.pop(session_id, None)

    def counts(self, session_id: str) -> dict:
        bucket = self._session_conns.get(session_id)
        if not bucket:
            return {_ROLE_RECRUITER: 0, _ROLE_CANDIDATE: 0}
        return {
            _ROLE_RECRUITER: len(bucket[_ROLE_RECRUITER]),
            _ROLE_CANDIDATE: len(bucket[_ROLE_CANDIDATE]),
        }

    async def broadcast(self, session_id: str, message: dict, roles=None) -> None:
        bucket = self._session_conns.get(session_id)
        if not bucket:
            return
        if roles is None:
            groups = (bucket[_ROLE_RECRUITER], bucket[_ROLE_CANDIDATE])
        else:
            targets = []
            if _ROLE_RECRUITER in roles:
                targets.append(bucket[_ROLE_RECRUITER])
            if _ROLE_CANDIDATE in roles:
                targets.append(bucket[_ROLE_CANDIDATE])
            groups = tuple(targets)
        payload = json.dumps(message)
        for group in groups:
            for ws in list(group):
                try:
                    # The sending handler awaits the write directly on each
                    # connected socket. All sockets share one event loop, so
                    # this resolves in order without cross-loop scheduling.
                    await ws.send_text(payload)
                except Exception:  # noqa: BLE001 - best effort push
                    logger.exception("live broadcast send failed")


manager = LiveManager()


def _question_payload(q: dict) -> dict:
    return {
        "question_index": q.get("question_index", 0),
        "question_id": q.get("question_id"),
        "question_text": q.get("question_text"),
        "category": q.get("category", ""),
        "competency": q.get("competency", ""),
        "difficulty": q.get("difficulty", "medium"),
        "source": q.get("source", "bank"),
    }


def _resolve_identity(token: str):
    """Return (role, identity) where identity is username (recruiter) or a
    (candidate_id, job_id) tuple (candidate). Returns None if the token is
    invalid for both roles."""
    username = verify_token(token)
    if username:
        return _ROLE_RECRUITER, username
    ident = verify_interview_token(token)
    if ident:
        return _ROLE_CANDIDATE, ident
    return None


def _authorize(session_id: str, role: str, identity):
    """Raise a string reason if the identity may not connect to this session.

    Returns the session dict on success.
    """
    session = db.get_session(session_id)
    if not session:
        return None, "Session not found"

    if role == _ROLE_RECRUITER:
        if not db.get_owned_session(identity, session_id):
            return None, "Not authorized for this session"
        return session, None

    candidate_id, job_id = identity
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate.get("job_id") != job_id:
        return None, "Invalid interview token"
    if candidate.get("session_id") != session_id:
        return None, "Session does not belong to this candidate"
    return session, None


@router.websocket("/ws/interview/{session_id}")
async def interview_ws(websocket: WebSocket, session_id: str):
    token = websocket.query_params.get("token", "")
    resolved = _resolve_identity(token)
    if not resolved:
        await websocket.accept()
        await websocket.close(code=4401, reason="Authentication required")
        return

    role, identity = resolved
    session, err = _authorize(session_id, role, identity)
    if not session:
        await websocket.accept()
        await websocket.close(code=4403, reason=err or "Not authorized")
        return

    await websocket.accept()
    manager.join(session_id, role, websocket)

    try:
        await _send_joined(websocket, session_id, role)

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                await websocket.send_json({"type": "error", "code": "bad_json"})
                continue
            if not isinstance(msg, dict):
                await websocket.send_json({"type": "error", "code": "bad_message"})
                continue

            mtype = msg.get("type")
            if mtype == "ask_question":
                await _on_ask_question(websocket, session_id, role, msg)
            elif mtype == "end_interview":
                await _on_end_interview(websocket, session_id, role)
            elif mtype == "answer_completed":
                await _on_answer_completed(websocket, session_id, role)
            elif mtype in ("join", "answer_started"):
                await _on_ack(websocket, session_id, role, mtype)
            else:
                await websocket.send_json(
                    {"type": "error", "code": "unknown_event", "message": mtype}
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.leave(session_id, role, websocket)
        await _broadcast_connections(session_id)


async def _send_joined(ws: WebSocket, session_id: str, role: str):
    session = db.get_session(session_id)
    status = (session or {}).get("status", "in_progress")
    current = db.get_live_question(session_id)
    has_questions = db.session_questions_exist(session_id)
    counts = manager.counts(session_id)
    await ws.send_json({
        "type": "joined",
        "role": role,
        "session_status": status,
        "current_question": _question_payload(current) if current else None,
        "has_questions": has_questions,
        "connections": counts,
    })


async def _on_ask_question(ws: WebSocket, session_id: str, role: str, msg: dict):
    if role != _ROLE_RECRUITER:
        await ws.send_json({"type": "error", "code": "forbidden", "message": "Recruiter only"})
        return
    question_id = msg.get("question_id", "")
    question = db.get_session_question_by_id(session_id, question_id)
    if not question:
        await ws.send_json({"type": "error", "code": "unknown_question"})
        return

    db.set_live_question(session_id, question_id)
    db.mark_question_asked(session_id, question_id)
    payload = _question_payload(question)
    # Broadcast reaches both the candidate AND the recruiter who asked, so the
    # recruiter's UI updates immediately too.
    await manager.broadcast(session_id, {"type": "question_asked", "question": payload})


async def _on_end_interview(ws: WebSocket, session_id: str, role: str):
    if role != _ROLE_RECRUITER:
        await ws.send_json({"type": "error", "code": "forbidden", "message": "Recruiter only"})
        return
    db.update_session(session_id, status="completed")
    db.set_live_question(session_id, "")
    await manager.broadcast(session_id, {"type": "interview_ended", "status": "completed"})


async def _on_answer_completed(ws: WebSocket, session_id: str, role: str):
    if role != _ROLE_CANDIDATE:
        await ws.send_json({"type": "error", "code": "forbidden", "message": "Candidate only"})
        return
    current = db.get_live_question(session_id)
    if not current:
        await ws.send_json({"type": "error", "code": "no_active_question"})
        return
    transcript_rec = db.get_question_transcript(session_id, current["question_id"])
    transcript = (transcript_rec or {}).get("transcript", "")
    await manager.broadcast(
        session_id,
        {
            "type": "transcript_ready",
            "question_id": current["question_id"],
            "transcript": transcript,
        },
        roles=[_ROLE_RECRUITER],
    )
    await ws.send_json({"type": "answer_completed_ack"})


async def _on_ack(ws: WebSocket, session_id: str, role: str, mtype: str):
    counts = manager.counts(session_id)
    if role == _ROLE_CANDIDATE and mtype == "answer_started":
        await manager.broadcast(
            session_id,
            {"type": "answer_started"},
            roles=[_ROLE_RECRUITER],
        )
    else:
        await _broadcast_connections(session_id)
    await ws.send_json({"type": "ack", "event": mtype, "connections": counts})


async def _broadcast_connections(session_id: str):
    counts = manager.counts(session_id)
    await manager.broadcast(session_id, {
        "type": "connection_status",
        "recruiter": counts[_ROLE_RECRUITER],
        "candidate": counts[_ROLE_CANDIDATE],
    })
