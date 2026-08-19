"""
Owner: Member C
Touches: this file only (registered into main_window.py)

Two-panel page: list of completed interview sessions on the left,
selected candidate's full score breakdown + explainability on the right.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    QFrame, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt

from app.core import db, settings_store
from app.reports.analytics import get_candidate_report
from app.reports.pdf_export import export_report


class SessionListItem(QWidget):
    def __init__(self, session, on_click):
        super().__init__()
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        name = QLabel(session.get("candidate_name") or "Unnamed candidate")
        name.setStyleSheet("font-size: 13px; font-weight: 700;")
        job = QLabel(session.get("job_title") or "—")
        job.setStyleSheet("font-size: 11px; color: #6B7280;")
        status = QLabel(f"Status: {session.get('status', 'unknown')}")
        status.setStyleSheet("font-size: 10px; color: #9CA3AF;")

        layout.addWidget(name)
        layout.addWidget(job)
        layout.addWidget(status)

        self.session_id = session["session_id"]
        self.on_click = on_click

    def mousePressEvent(self, event):
        self.on_click(self.session_id)


class ScoreRow(QWidget):
    def __init__(self, category, score, confidence):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)

        cat_lbl = QLabel(category)
        cat_lbl.setFixedWidth(160)
        cat_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")

        bar_bg = QFrame()
        bar_bg.setFixedHeight(10)
        bar_bg.setStyleSheet("background-color: #E5E7EB; border-radius: 5px;")
        bar_layout = QHBoxLayout(bar_bg)
        bar_layout.setContentsMargins(0, 0, 0, 0)

        color = "#10B981" if score >= 70 else ("#F59E0B" if score >= 40 else "#EF4444")
        fill = QFrame()
        fill.setFixedHeight(10)
        fill.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        fill.setFixedWidth(max(4, int(score * 2)))
        bar_layout.addWidget(fill)
        bar_layout.addStretch()

        score_lbl = QLabel(f"{score:.0f}")
        score_lbl.setFixedWidth(36)
        score_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")

        layout.addWidget(cat_lbl)
        layout.addWidget(bar_bg, stretch=1)
        layout.addWidget(score_lbl)


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        header = QLabel("Candidate Reports")
        header.setObjectName("PageTitle")
        sub = QLabel("Score breakdowns with explainability overlays")
        sub.setObjectName("PageSubtitle")
        root.addWidget(header)
        root.addWidget(sub)

        body = QHBoxLayout()
        body.setSpacing(20)

        # left: session list
        left = QVBoxLayout()
        left_label = QLabel("Completed Interviews")
        left_label.setStyleSheet("font-size: 13px; font-weight: 700;")
        left.addWidget(left_label)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QScrollArea.NoFrame)
        self.list_scroll.setFixedWidth(280)
        left.addWidget(self.list_scroll)
        body.addLayout(left)

        # right: detail panel
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QScrollArea.NoFrame)
        self.detail_container = QWidget()
        self.detail_scroll.setWidget(self.detail_container)
        body.addWidget(self.detail_scroll, stretch=1)

        root.addLayout(body, stretch=1)

        self._show_empty_detail("Select a candidate on the left to view their report.")
        self.refresh()

    def refresh(self):
        sessions = db.get_all_sessions()
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setSpacing(8)

        if sessions:
            for s in sessions:
                item = SessionListItem(s, self._show_detail)
                list_layout.addWidget(item)
        else:
            empty = QLabel("No completed interviews yet.")
            empty.setStyleSheet("color: #9CA3AF; font-size: 12px; padding: 20px;")
            empty.setWordWrap(True)
            list_layout.addWidget(empty)
        list_layout.addStretch()
        self.list_scroll.setWidget(list_widget)

    def _show_empty_detail(self, message):
        container = QWidget()
        layout = QVBoxLayout(container)
        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 60px;")
        lbl.setObjectName("Card")
        layout.addWidget(lbl)
        self.detail_scroll.setWidget(container)

    def _show_detail(self, session_id):
        report = get_candidate_report(session_id)
        session = report["session"]
        scores = report["scores"]
        explanations = {e["question_id"]: e for e in report["explanations"]}

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        name_lbl = QLabel(session.get("candidate_name", "Unknown"))
        name_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        job_lbl = QLabel(f"Applied for: {session.get('job_title', '—')}")
        job_lbl.setObjectName("PageSubtitle")

        top_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.addWidget(name_lbl)
        title_col.addWidget(job_lbl)
        top_row.addLayout(title_col)
        top_row.addStretch()

        download_btn = QPushButton("Download PDF")
        download_btn.setObjectName("PrimaryButton")
        download_btn.setCursor(Qt.PointingHandCursor)
        download_btn.clicked.connect(lambda: self._download_pdf(session_id, session.get("candidate_name", "candidate")))
        top_row.addWidget(download_btn)
        layout.addLayout(top_row)

        overall_card = QWidget()
        overall_card.setObjectName("Card")
        overall_layout = QVBoxLayout(overall_card)
        overall_title = QLabel("Overall Score")
        overall_title.setObjectName("PageSubtitle")
        overall_val = QLabel(f"{report['overall_score']:.0f} / 100")
        overall_val.setStyleSheet("font-size: 26px; font-weight: 700; color: #5B5FEF;")
        overall_layout.addWidget(overall_title)
        overall_layout.addWidget(overall_val)
        layout.addWidget(overall_card)

        if scores:
            breakdown_card = QWidget()
            breakdown_card.setObjectName("Card")
            breakdown_layout = QVBoxLayout(breakdown_card)
            breakdown_title = QLabel("Competency Breakdown")
            breakdown_title.setStyleSheet("font-size: 13px; font-weight: 700; margin-bottom: 6px;")
            breakdown_layout.addWidget(breakdown_title)
            for sc in scores:
                breakdown_layout.addWidget(ScoreRow(sc["category"], sc["score"], sc["confidence"]))

                exp = explanations.get(sc["question_id"])
                if exp:
                    exp_lbl = QLabel(f"↳ {exp['summary']}")
                    exp_lbl.setWordWrap(True)
                    exp_lbl.setStyleSheet("font-size: 11px; color: #6B7280; padding-left: 8px; padding-bottom: 4px;")
                    breakdown_layout.addWidget(exp_lbl)
            layout.addWidget(breakdown_card)
        else:
            no_scores = QLabel(
                "No scores recorded yet for this session — scoring pipeline "
                "(app/engine/scoring.py) hasn't run for it."
            )
            no_scores.setObjectName("Card")
            no_scores.setWordWrap(True)
            no_scores.setStyleSheet("padding: 20px; color: #6B7280; font-size: 12px;")
            layout.addWidget(no_scores)

        layout.addStretch()
        self.detail_scroll.setWidget(container)

    def _download_pdf(self, session_id, candidate_name):
        default_dir = settings_store.load_settings()["export_dir"]
        safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in candidate_name).strip() or "candidate"
        default_path = str(Path(default_dir) / f"{safe_name}_report.pdf")

        path, _ = QFileDialog.getSaveFileName(self, "Save report as", default_path, "PDF files (*.pdf)")
        if not path:
            return
        try:
            export_report(session_id, path)
            QMessageBox.information(self, "Report saved", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Could not generate PDF:\n{e}")
