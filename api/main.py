"""
FastAPI application entry point.
Spawns as a child process from Electron, serves on a random port.
"""
import sys
import os
import argparse
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core import db
from api.routes import auth, jobs, candidates, sessions, scoring, reports, integrity, settings, devices, candidate_flow


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="InterviewIQ API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(scoring.router, prefix="/api/scoring", tags=["scoring"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(integrity.router, prefix="/api", tags=["integrity"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(candidate_flow.router, prefix="/api", tags=["candidate-flow"])


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
