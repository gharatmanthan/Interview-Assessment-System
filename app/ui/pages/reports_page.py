from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.core import db
from app.reports.pdf_export import export_report


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.sessions = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(14)

        title = QLabel("Candidate Reports")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Review scored answers, explanations, and integrity signals")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(16)

        sessions_panel = QWidget()
        sessions_panel.setObjectName("Card")
        sessions_layout = QVBoxLayout(sessions_panel)
        sessions_layout.setContentsMargins(16, 16, 16, 16)
        sessions_heading = QLabel("Interview sessions")
        sessions_heading.setStyleSheet("font-size: 14px; font-weight: 700; color: #344054;")
        sessions_layout.addWidget(sessions_heading)

        self.sessions_list = QListWidget()
        self.sessions_list.currentRowChanged.connect(self._show_selected)
        self.sessions_list.setMinimumWidth(300)
        sessions_layout.addWidget(self.sessions_list)
        body.addWidget(sessions_panel, stretch=2)

        report_panel = QWidget()
        report_panel.setObjectName("Card")
        report_layout = QVBoxLayout(report_panel)
        report_layout.setContentsMargins(16, 16, 16, 16)
        report_heading = QLabel("Assessment summary")
        report_heading.setStyleSheet("font-size: 14px; font-weight: 700; color: #344054;")
        report_layout.addWidget(report_heading)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        report_layout.addWidget(self.report_text, stretch=1)

        export_button = QPushButton("Export selected PDF")
        export_button.setObjectName("PrimaryButton")
        export_button.clicked.connect(self._export_selected)
        report_layout.addWidget(export_button)
        body.addWidget(report_panel, stretch=3)

        layout.addLayout(body, stretch=1)

    def start_refreshing(self):
        """Load report data after the user has authenticated."""
        self.refresh()

    def refresh(self):
        self.sessions = db.get_all_sessions()
        self.sessions_list.clear()
        for session in self.sessions:
            self.sessions_list.addItem(
                f"{session['candidate_name']} | {session['job_title']} | {session['status']}"
            )
        if self.sessions:
            self.sessions_list.setCurrentRow(0)
        else:
            self.report_text.setPlainText("No completed interview sessions yet.")

    def _show_selected(self, row):
        if row < 0 or row >= len(self.sessions):
            return
        session = self.sessions[row]
        scores = db.get_session_scores(session["session_id"])
        explanations = db.get_session_explanations(session["session_id"])
        flags = db.get_session_flags(session["session_id"])
        lines = [
            f"Candidate: {session['candidate_name']}",
            f"Role: {session['job_title']}",
            f"Status: {session['status']}",
            "",
            "Scores:",
        ]
        lines.extend(
            f"- {score['question_id']}: {score['score']}/100 "
            f"({score['confidence']:.0%} confidence; {score.get('evaluation_source', 'heuristic')})"
            for score in scores
        )
        lines.append("\nExplanations:")
        lines.extend(
            f"- {item['question_id']} ({item.get('evaluation_source', 'heuristic')}): "
            f"{item['summary']}"
            for item in explanations
        )
        lines.append("\nIntegrity flags:")
        lines.extend(f"- {flag['severity'].upper()}: {flag['detail']}" for flag in flags)
        if not flags:
            lines.append("- None recorded")
        self.report_text.setPlainText("\n".join(lines))

    def _export_selected(self):
        row = self.sessions_list.currentRow()
        if row < 0 or row >= len(self.sessions):
            return
        session_id = self.sessions[row]["session_id"]
        path = Path("data") / "reports" / f"{session_id}.pdf"
        try:
            export_report(session_id, str(path))
            QMessageBox.information(self, "Report exported", f"PDF saved to {path}")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Export failed", str(error))
