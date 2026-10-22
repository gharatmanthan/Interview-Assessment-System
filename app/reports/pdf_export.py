"""Generate a concise interviewer-facing PDF report."""
from pathlib import Path
import textwrap

from fpdf import FPDF

from app.core import db


def _pdf_text(value: object, width: int = 95) -> str:
    text = " ".join(str(value or "").split())
    return "\n".join(
        textwrap.wrap(
            text,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
        )
    ) or "-"


def _write_paragraph(pdf: FPDF, text: object) -> None:
    pdf.multi_cell(
        pdf.epw,
        6,
        _pdf_text(text),
        new_x="LMARGIN",
        new_y="NEXT",
    )


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
    pdf.cell(pdf.epw, 10, "Interview Assessment Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(
        pdf.epw, 8, _pdf_text(f"Candidate: {session['candidate_name']}"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.cell(
        pdf.epw, 8, _pdf_text(f"Role: {session['job_title']}"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.cell(
        pdf.epw, 8, _pdf_text(f"Status: {session['status']}"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "Answer Scores", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for score in scores:
        _write_paragraph(
            pdf,
            f"{score['question_id']} | {score['category']}: {score['score']}/100 "
            f"(confidence {score['confidence']:.0%})",
        )
    if not scores:
        pdf.cell(pdf.epw, 6, "No scored answers available.", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "Explainability", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for explanation in explanations:
        _write_paragraph(
            pdf, f"{explanation['question_id']}: {explanation['summary']}"
        )
    if not explanations:
        pdf.cell(pdf.epw, 6, "No explanations available.", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(pdf.epw, 8, "Integrity Flags", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for flag in flags:
        _write_paragraph(
            pdf, f"{flag['severity'].upper()} | {flag['flag_type']}: {flag['detail']}"
        )
    if not flags:
        pdf.cell(pdf.epw, 6, "No integrity flags recorded.", new_x="LMARGIN", new_y="NEXT")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(destination))
    return str(destination)
