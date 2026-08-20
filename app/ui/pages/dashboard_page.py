from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QScrollArea
)
from PySide6.QtCore import Qt

from app.reports.analytics import get_dashboard_stats
from app.core import db


class StatCard(QWidget):
    def __init__(self, title, value, hint, accent="#5B5FEF"):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("PageSubtitle")

        value_lbl = QLabel(str(value))
        value_lbl.setStyleSheet(f"font-size: 28px; font-weight: 700; color: {accent};")

        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet("font-size: 11px; color: #6B7280;")

        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        layout.addWidget(hint_lbl)


class JobPostingRow(QWidget):
    def __init__(self, job):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        top = QHBoxLayout()
        title = QLabel(job["title"])
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        level = QLabel(job["experience_level"])
        level.setObjectName("Badge-clear")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(level)
        layout.addLayout(top)

        skills = ", ".join(job["required_skills"]) if job["required_skills"] else "—"
        meta = QLabel(f"{job['department']} · {job['num_rounds']} round(s) · Skills: {skills}")
        meta.setStyleSheet("font-size: 12px; color: #6B7280;")
        meta.setWordWrap(True)
        layout.addWidget(meta)


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(36, 30, 36, 30)
        self.layout_root.setSpacing(20)

        header = QLabel("Dashboard")
        header.setObjectName("PageTitle")
        sub = QLabel("Overview of interviews, bias signals, and integrity flags")
        sub.setObjectName("PageSubtitle")
        self.layout_root.addWidget(header)
        self.layout_root.addWidget(sub)

        self.grid_container = QWidget()
        self.layout_root.addWidget(self.grid_container)

        jobs_header = QLabel("Job Postings")
        jobs_header.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 8px;")
        self.layout_root.addWidget(jobs_header)

        self.jobs_scroll = QScrollArea()
        self.jobs_scroll.setWidgetResizable(True)
        self.jobs_scroll.setFrameShape(QScrollArea.NoFrame)
        self.layout_root.addWidget(self.jobs_scroll, stretch=1)

        self.refresh()

    def refresh(self):
        """Call this whenever the dashboard becomes visible, so newly
        created job postings / sessions show up without restarting the app.
        """
        # rebuild stat cards
        old_grid = self.grid_container.layout()
        if old_grid:
            while old_grid.count():
                item = old_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        else:
            old_grid = QGridLayout(self.grid_container)
            old_grid.setSpacing(16)

        stats = get_dashboard_stats()
        old_grid.addWidget(StatCard("Interviews Conducted", stats["interviews_conducted"],
                                     "All time", "#5B5FEF"), 0, 0)
        avg_score = stats["avg_explainability_score"]
        old_grid.addWidget(StatCard("Avg. Explainability Score",
                                     f"{avg_score:.0f}" if avg_score else "—",
                                     "Confidence in scoring", "#14B8A6"), 0, 1)
        old_grid.addWidget(StatCard("Bias Flags Raised", stats["bias_flags_raised"],
                                     "Across demographic proxies", "#F59E0B"), 0, 2)
        old_grid.addWidget(StatCard("Integrity Flags", stats["integrity_flags"],
                                     "Suspected AI-assisted answers", "#EF4444"), 0, 3)

        # rebuild candidate status summary
        status_labels = {
            "invited": ("Invited", "#4338CA"),
            "in_progress": ("In Progress", "#92400E"),
            "completed": ("Completed", "#065F46"),
        }
        by_status = stats.get("candidates_by_status", {})
        col = 0
        for key, (label, color) in status_labels.items():
            count = by_status.get(key, 0)
            old_grid.addWidget(
                StatCard(label, count, "Candidates", color), 1, col
            )
            col += 1

        # rebuild job postings list
        jobs = db.get_all_job_postings()
        jobs_widget = QWidget()
        jobs_layout = QVBoxLayout(jobs_widget)
        jobs_layout.setSpacing(10)
        if jobs:
            for job in jobs:
                jobs_layout.addWidget(JobPostingRow(job))
        else:
            empty = QLabel(
                "No job postings yet.\n\nGo to 'Create Job Posting' in the sidebar to define "
                "a role — this is what grounds question generation and scoring."
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 40px;")
            empty.setObjectName("Card")
            jobs_layout.addWidget(empty)
        jobs_layout.addStretch()
        self.jobs_scroll.setWidget(jobs_widget)
