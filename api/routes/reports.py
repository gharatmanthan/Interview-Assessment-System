import csv
import io
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, FileResponse
from api.schemas import DashboardStats, CandidateReport, ComparisonRow
from app.reports.analytics import (
    get_dashboard_stats,
    get_candidate_report,
    get_candidate_comparison,
    export_candidates_csv,
)
from app.reports.pdf_export import export_report
from pathlib import Path
import tempfile

router = APIRouter()


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats():
    return get_dashboard_stats()


@router.get("/candidate/{session_id}", response_model=CandidateReport)
def candidate_report(session_id: str):
    return get_candidate_report(session_id)


@router.get("/compare", response_model=list[ComparisonRow])
def compare_candidates(job_id: str = None):
    return get_candidate_comparison(job_id)


@router.get("/export/csv")
def export_csv(job_id: str = None):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="", encoding="utf-8")
    tmp.close()
    export_candidates_csv(tmp.name, job_id)

    def iter_file():
        with open(tmp.name, "r", encoding="utf-8") as f:
            yield from f
        Path(tmp.name).unlink(missing_ok=True)

    return StreamingResponse(
        iter_file(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidates.csv"},
    )


@router.get("/export/pdf/{session_id}")
def export_pdf(session_id: str):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    export_report(session_id, tmp.name)
    return FileResponse(
        tmp.name,
        media_type="application/pdf",
        filename=f"report_{session_id}.pdf",
        background=None,
    )
