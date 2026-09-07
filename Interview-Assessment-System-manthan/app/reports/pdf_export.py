"""Generate a concise interviewer-facing PDF report."""
from pathlib import Path

from fpdf import FPDF

from app.core import db


def export_report(session_id: str, output_path: str) -> str:
    sessions = [item for item in db.get_all_sessions() if item["session_id"] == session_id]
    if not sessions:
        raise ValueError("Interview session was not found.")
    session = sessions[0]
    scores = db.get_session_scores(session_id)
    explanations = db.get_session_explanations(session_id)
    flags = db.get_session_flags(session_id)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Interview Assessment Report", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, f"Candidate: {session['candidate_name']}", ln=True)
    pdf.cell(0, 8, f"Role: {session['job_title']}", ln=True)
    pdf.cell(0, 8, f"Status: {session['status']}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Answer Scores", ln=True)
    pdf.set_font("Helvetica", size=10)
    for score in scores:
        pdf.multi_cell(0, 6, f"{score['question_id']} | {score['category']}: {score['score']}/100 "
                             f"(confidence {score['confidence']:.0%})")
    if not scores:
        pdf.cell(0, 6, "No scored answers available.", ln=True)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Explainability", ln=True)
    pdf.set_font("Helvetica", size=10)
    for explanation in explanations:
        pdf.multi_cell(0, 6, f"{explanation['question_id']}: {explanation['summary']}")
    if not explanations:
        pdf.cell(0, 6, "No explanations available.", ln=True)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Integrity Flags", ln=True)
    pdf.set_font("Helvetica", size=10)
    for flag in flags:
        pdf.multi_cell(0, 6, f"{flag['severity'].upper()} | {flag['flag_type']}: {flag['detail']}")
    if not flags:
        pdf.cell(0, 6, "No integrity flags recorded.", ln=True)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(destination))
    return str(destination)
