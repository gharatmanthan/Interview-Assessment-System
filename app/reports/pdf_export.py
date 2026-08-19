"""
Owner: Member C
Touches: this file only

Generates a downloadable PDF candidate report: overall score, competency
breakdown, explanations, and integrity flags.
"""
from pathlib import Path
from fpdf import FPDF

from app.core import db
from app.reports.analytics import get_candidate_report


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(91, 95, 239)  # brand indigo
        self.cell(0, 12, "Interview Assessment Report", ln=True)
        self.set_draw_color(230, 230, 230)
        self.line(10, 22, 200, 22)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def export_report(session_id: str, output_path: str) -> str:
    """Builds a PDF report for one candidate session and writes it to
    output_path. Returns output_path once written.
    """
    report = get_candidate_report(session_id)
    session = report["session"]
    scores = report["scores"]
    explanations = {e["question_id"]: e for e in report["explanations"]}
    flags = db.get_session_flags(session_id)

    pdf = ReportPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 8, session.get("candidate_name", "Unknown candidate"), ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, f"Applied for: {session.get('job_title', '-')}", ln=True)
    pdf.cell(0, 7, f"Status: {session.get('status', '-')}", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(91, 95, 239)
    pdf.cell(0, 8, f"Overall Score: {report['overall_score']:.0f} / 100", ln=True)
    pdf.ln(4)

    if scores:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 8, "Competency Breakdown", ln=True)
        pdf.ln(2)

        for sc in scores:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(60, 7, sc["category"], border=0)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 7, f"{sc['score']:.0f} / 100  (confidence {sc['confidence']:.0%})", ln=True)

            exp = explanations.get(sc["question_id"])
            if exp:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(110, 110, 110)
                pdf.multi_cell(0, 6, f"   {exp['summary']}")
            pdf.ln(2)
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, "No competency scores recorded for this session.", ln=True)

    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 8, "Integrity Flags", ln=True)
    pdf.ln(2)

    if flags:
        for f in flags:
            pdf.set_font("Helvetica", "B", 9)
            sev = f.get("severity", "low").upper()
            if sev == "HIGH":
                pdf.set_text_color(200, 60, 60)
            else:
                pdf.set_text_color(150, 120, 30)
            pdf.cell(20, 6, sev)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(0, 6, f"{f['flag_type']}: {f['detail']}", ln=True)
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, "No integrity flags raised.", ln=True)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(output_path)
    return output_path
