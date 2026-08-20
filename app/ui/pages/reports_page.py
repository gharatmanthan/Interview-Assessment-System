"""
Owner: Member C
Touches: this file only (registered into main_window.py)

Two-panel page: list of completed interview sessions on the left,
selected candidate's full score breakdown + explainability on the right.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    QFrame, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox
)
from PySide6.QtCore import Qt

from app.core import db, settings_store
from app.reports.analytics import get_candidate_report, get_candidate_comparison, export_candidates_csv
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

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        compare_btn = QPushButton("Compare Candidates")
        compare_btn.setCursor(Qt.PointingHandCursor)
        compare_btn.clicked.connect(self._show_comparison)
        toolbar.addWidget(compare_btn)

        export_btn = QPushButton("Export All (CSV)")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_all_csv)
        toolbar.addWidget(export_btn)
        root.addLayout(toolbar)

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

    def _export_all_csv(self):
        default_dir = settings_store.load_settings()["export_dir"]
        default_path = str(Path(default_dir) / "candidate_rankings.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export all candidates as CSV", default_path, "CSV files (*.csv)")
        if not path:
            return
        try:
            export_candidates_csv(path)
            QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Could not export CSV:\n{e}")

    def _show_comparison(self):
        jobs = db.get_all_job_postings()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        title = QLabel("Candidate Comparison — Ranked by Overall Score")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        filter_row = QHBoxLayout()
        filter_lbl = QLabel("Filter by job:")
        filter_lbl.setStyleSheet("font-size: 12px; color: #6B7280;")
        job_filter = QComboBox()
        job_filter.addItem("All jobs", None)
        for job in jobs:
            job_filter.addItem(job["title"], job["job_id"])
        filter_row.addWidget(filter_lbl)
        filter_row.addWidget(job_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Rank", "Candidate", "Job", "Overall Score"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.cellDoubleClicked.connect(
            lambda row, col: self._show_detail(table.item(row, 0).data(Qt.UserRole))
        )
        layout.addWidget(table, stretch=1)

        hint = QLabel("Double-click a row to view that candidate's full report.")
        hint.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        layout.addWidget(hint)

        def populate(job_id):
            rows = get_candidate_comparison(job_id)
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                rank_item = QTableWidgetItem(str(i + 1))
                rank_item.setData(Qt.UserRole, row["session_id"])
                table.setItem(i, 0, rank_item)
                table.setItem(i, 1, QTableWidgetItem(row["candidate_name"]))
                table.setItem(i, 2, QTableWidgetItem(row["job_title"]))
                score_item = QTableWidgetItem(f"{row['overall_score']:.1f}")
                table.setItem(i, 3, score_item)
            if not rows:
                table.setRowCount(1)
                table.setItem(0, 0, QTableWidgetItem(""))
                table.setItem(0, 1, QTableWidgetItem("No scored candidates yet"))
                table.setItem(0, 2, QTableWidgetItem(""))
                table.setItem(0, 3, QTableWidgetItem(""))

        job_filter.currentIndexChanged.connect(lambda: populate(job_filter.currentData()))
        populate(None)

        layout.addStretch()
        self.detail_scroll.setWidget(container)
