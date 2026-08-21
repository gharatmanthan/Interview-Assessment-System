import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.schemas import IntegrityFlagResponse
from app.core import db
from app.candidate.integrity import run_checks, ExternalDeviceMonitor

router = APIRouter()


@router.get("/integrity/flags", response_model=list[IntegrityFlagResponse])
def list_integrity_flags():
    return db.get_all_integrity_flags()


@router.get("/bias/flags")
def list_bias_flags():
    return db.get_all_fairness_flags()


@router.websocket("/ws/integrity/{session_id}")
async def integrity_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    monitor = ExternalDeviceMonitor(session_id)
    monitor.start()

    try:
        while True:
            flags = run_checks(session_id)
            poll_flags = monitor.poll()
            all_flags = flags + poll_flags

            for flag in all_flags:
                db.save_integrity_flag(flag)

            await websocket.send_json({
                "flags": [
                    {
                        "flag_type": f.flag_type,
                        "detail": f.detail,
                        "severity": f.severity,
                    }
                    for f in all_flags
                ],
                "total_flags": len(all_flags),
            })
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
