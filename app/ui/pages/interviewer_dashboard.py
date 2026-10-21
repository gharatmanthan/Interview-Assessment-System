"""
Interviewer Dashboard — rich recruiter home page.

Shows:
  - Stat cards: sessions today, active jobs, avg score, integrity flags
  - Recent sessions table with status badges
  - Quick action buttons (navigate to other pages)
  - Live integrity alerts panel
"""
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core import db
from app.reports.analytics import get_dashboard_stats


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------

class StatCard(QWidget):
    """A single KPI card with a big coloured number."""

    def __init__(self, title: str, value: str, hint: str, accent: str = "#5B5FEF"):
        super().__init__()
        self.setObjectName("StatCard")
        self.setMinimumHeight(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("PageSubtitle")

        value_lbl = QLabel(value)
        value_lbl.setObjectName("StatValue")
        value_lbl.setStyleSheet(f"font-size: 30px; font-weight: 700; color: {accent};")

        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet("font-size: 11px; color: #6B7280;")

        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        layout.addWidget(hint_lbl)
        layout.addStretch()


class SessionRow(QWidget):
    """One row in the recent-sessions mini-table."""

    STATUS_COLORS = {
        "complete": ("#D1FAE5", "#065F46"),
        "in_progress": ("#FEF3C7", "#92400E"),
        "live": ("#DBEAFE", "#1E40AF"),
    }

    def __init__(self, session: dict):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        name_lbl = QLabel(session.get("candidate_name", "—"))
        name_lbl.setMinimumWidth(140)
        name_lbl.setStyleSheet("font-weight: 600; color: #1B1F2A;")

        job_lbl = QLabel(session.get("job_title", "—"))
        job_lbl.setMinimumWidth(160)
        job_lbl.setStyleSheet("color: #6B7280;")

        # Score
        session_id = session.get("session_id")
        scores = db.get_session_scores(session_id) if session_id else []
        avg_score = (
            round(sum(s["score"] for s in scores) / len(scores), 1) if scores else None
        )
        score_lbl = QLabel(f"{avg_score}/100" if avg_score is not None else "—")
        score_lbl.setMinimumWidth(80)
        score_lbl.setAlignment(Qt.AlignCenter)
        score_lbl.setStyleSheet("font-weight: 600; color: #1B1F2A;")

        # Status badge
        status = session.get("status", "")
        bg, fg = self.STATUS_COLORS.get(status, ("#F3F4F6", "#6B7280"))
        status_lbl = QLabel(status.replace("_", " ").title())
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.setFixedWidth(90)
        status_lbl.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 6px;"
            f" padding: 3px 8px; font-size: 11px; font-weight: 600;"
        )

        layout.addWidget(name_lbl)
        layout.addWidget(job_lbl, stretch=1)
        layout.addWidget(score_lbl)
        layout.addWidget(status_lbl)

        # Alternate row background
        self.setAutoFillBackground(True)

    def enterEvent(self, _event):
        self.setStyleSheet("background-color: #F0FDF4; border-radius: 6px;")

    def leaveEvent(self, _event):
        self.setStyleSheet("")


class IntegrityAlertRow(QWidget):
    """One integrity flag row in the alerts panel."""

    SEVERITY_COLORS = {
        "high": ("#FEE2E2", "#991B1B"),
        "medium": ("#FEF3C7", "#92400E"),
        "low": ("#F0FDF4", "#065F46"),
    }

    def __init__(self, flag: dict):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        severity = flag.get("severity", "low")
        bg, fg = self.SEVERITY_COLORS.get(severity, ("#F9FAFB", "#6B7280"))
        sev_lbl = QLabel(severity.upper())
        sev_lbl.setFixedWidth(60)
        sev_lbl.setAlignment(Qt.AlignCenter)
        sev_lbl.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 5px;"
            f" padding: 2px 6px; font-size: 11px; font-weight: 700;"
        )

        detail_lbl = QLabel(flag.get("detail", "—"))
        detail_lbl.setWordWrap(True)
        detail_lbl.setStyleSheet("color: #374151; font-size: 12px;")

        layout.addWidget(sev_lbl)
        layout.addWidget(detail_lbl, stretch=1)


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

class InterviewerDashboard(QWidget):
    """Full recruiter home dashboard with live stats, sessions, and alerts."""

    navigate = None  # Will be connected by MainWindow

    def __init__(self):
        super().__init__()
        self._navigate_callback = None

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(20)

        # --- Header ---
        header_row = QHBoxLayout()
        title = QLabel("Interviewer Dashboard")
        title.setObjectName("PageTitle")
        today = datetime.now().strftime("%A, %d %B %Y")
        date_lbl = QLabel(today)
        date_lbl.setObjectName("PageSubtitle")
        date_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(date_lbl)
        root.addLayout(header_row)

        # --- Stat cards ---
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(14)
        self._stat_cards: list[StatCard] = []
        root.addLayout(self.stats_grid)

        # --- Body: sessions + quick-actions + alerts ---
        body = QHBoxLayout()
        body.setSpacing(16)

        # Left column: recent sessions
        sessions_group = QGroupBox("Recent Interview Sessions")
        sessions_layout = QVBoxLayout(sessions_group)
        sessions_layout.setSpacing(0)

        # Table header
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #F3F7F5;")
        hdr_layout = QHBoxLayout(header_widget)
        hdr_layout.setContentsMargins(12, 6, 12, 6)
        for text, width in [("Candidate", 140), ("Job Title", 0), ("Avg Score", 80), ("Status", 90)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: 700; font-size: 11px; color: #6B7280; text-transform: uppercase;")
            if width:
                lbl.setMinimumWidth(width)
            else:
                lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            hdr_layout.addWidget(lbl)
        sessions_layout.addWidget(header_widget)

        self.sessions_scroll = QScrollArea()
        self.sessions_scroll.setWidgetResizable(True)
        self.sessions_scroll.setMinimumHeight(200)
        self.sessions_container = QWidget()
        self.sessions_vbox = QVBoxLayout(self.sessions_container)
        self.sessions_vbox.setContentsMargins(0, 0, 0, 0)
        self.sessions_vbox.setSpacing(0)
        self.sessions_vbox.addStretch()
        self.sessions_scroll.setWidget(self.sessions_container)
        sessions_layout.addWidget(self.sessions_scroll)

        self.no_sessions_lbl = QLabel("No sessions yet. Start an interview to begin.")
        self.no_sessions_lbl.setAlignment(Qt.AlignCenter)
        self.no_sessions_lbl.setStyleSheet("color: #9CA3AF; padding: 30px;")
        sessions_layout.addWidget(self.no_sessions_lbl)

        body.addWidget(sessions_group, stretch=3)

        # Right column: quick actions + integrity alerts
        right_col = QVBoxLayout()
        right_col.setSpacing(14)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setSpacing(10)

        self.btn_new_job = QPushButton("Create job posting")
        self.btn_new_job.setObjectName("PrimaryButton")
        self.btn_interview = QPushButton("Open live monitor")
        self.btn_interview.setObjectName("SecondaryButton")
        self.btn_reports = QPushButton("View reports")
        self.btn_reports.setObjectName("SecondaryButton")

        for btn in (self.btn_new_job, self.btn_interview, self.btn_reports):
            btn.setMinimumHeight(40)
            actions_layout.addWidget(btn)

        right_col.addWidget(actions_group)

        # Integrity alerts
        alerts_group = QGroupBox("Integrity alerts")
        alerts_layout = QVBoxLayout(alerts_group)
        alerts_layout.setSpacing(0)

        self.alerts_scroll = QScrollArea()
        self.alerts_scroll.setWidgetResizable(True)
        self.alerts_scroll.setMaximumHeight(200)
        self.alerts_container = QWidget()
        self.alerts_vbox = QVBoxLayout(self.alerts_container)
        self.alerts_vbox.setContentsMargins(0, 0, 0, 0)
        self.alerts_vbox.setSpacing(2)
        self.alerts_vbox.addStretch()
        self.alerts_scroll.setWidget(self.alerts_container)
        alerts_layout.addWidget(self.alerts_scroll)

        self.no_alerts_lbl = QLabel("No integrity flags raised yet.")
        self.no_alerts_lbl.setAlignment(Qt.AlignCenter)
        self.no_alerts_lbl.setStyleSheet("color: #059669; padding: 16px; font-weight: 600;")
        alerts_layout.addWidget(self.no_alerts_lbl)

        right_col.addWidget(alerts_group)
        right_col.addStretch()
        body.addLayout(right_col, stretch=2)

        root.addLayout(body, stretch=1)

        # Auto-refresh every 5 s
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------------

    def set_navigate_callback(self, callback):
        """Connect quick-action buttons to the main window navigate function."""
        self._navigate_callback = callback
        self.btn_new_job.clicked.connect(lambda: callback("job_posting"))
        self.btn_interview.clicked.connect(lambda: callback("interview"))
        self.btn_reports.clicked.connect(lambda: callback("reports"))

    def refresh(self):
        """Reload all data from DB and repaint."""
        self._refresh_stats()
        self._refresh_sessions()
        self._refresh_alerts()

    def start_refreshing(self):
        """Begin loading remote dashboard data after authentication."""
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(5000)
        self.refresh()

    def _refresh_stats(self):
        # Clear old cards
        while self.stats_grid.count():
            item = self.stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            stats = get_dashboard_stats()
        except Exception:  # noqa: BLE001
            stats = {
                "interviews_conducted": 0,
                "avg_explainability_score": 0.0,
                "bias_flags_raised": 0,
                "integrity_flags": 0,
            }

        all_sessions = db.get_all_sessions()
        today_str = datetime.now().strftime("%Y-%m-%d")
        sessions_today = sum(
            1 for s in all_sessions
            if s.get("started_at", "").startswith(today_str)
        )
        active_jobs = len(db.get_active_job_postings())

        cards_data = [
            ("Sessions Today",  str(sessions_today),                           "Interviews conducted",       "#5B5FEF"),
            ("Active Jobs",     str(active_jobs),                               "Open job postings",          "#0F766E"),
            ("Avg Score",       f"{stats['avg_explainability_score']:.1f}",    "Across all scored answers",  "#14B8A6"),
            ("Integrity Flags", str(stats["integrity_flags"]),                  "Signals for review",         "#EF4444"),
        ]
        for col, (title, value, hint, accent) in enumerate(cards_data):
            card = StatCard(title, value, hint, accent)
            self.stats_grid.addWidget(card, 0, col)

    def _refresh_sessions(self):
        # Clear session rows (keep the stretch at end)
        while self.sessions_vbox.count() > 1:
            item = self.sessions_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sessions = db.get_all_sessions()[:15]  # latest 15
        self.no_sessions_lbl.setVisible(not sessions)
        self.sessions_scroll.setVisible(bool(sessions))

        for session in sessions:
            row = SessionRow(session)
            self.sessions_vbox.insertWidget(self.sessions_vbox.count() - 1, row)

    def _refresh_alerts(self):
        while self.alerts_vbox.count() > 1:
            item = self.alerts_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        flags = db.get_all_integrity_flags()[:10]
        self.no_alerts_lbl.setVisible(not flags)
        self.alerts_scroll.setVisible(bool(flags))

        for flag in flags:
            row = IntegrityAlertRow(flag)
            self.alerts_vbox.insertWidget(self.alerts_vbox.count() - 1, row)

    def cleanup(self):
        self.refresh_timer.stop()
