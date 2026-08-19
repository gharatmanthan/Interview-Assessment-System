from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from PySide6.QtCore import Signal

from app.ui.sidebar import Sidebar
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.interview_page import InterviewPage
from app.ui.pages.job_posting_page import JobPostingPage
from app.ui.pages.candidates_page import CandidatesPage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.bias_audit_page import BiasAuditPage
from app.ui.pages.integrity_log_page import IntegrityLogPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.core import db


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, logged_in_as: str = None):
        super().__init__()
        self.logged_in_as = logged_in_as
        title = "InterviewIQ — AI Interview Assessment System"
        if logged_in_as:
            title += f"  ({logged_in_as})"
        self.setWindowTitle(title)
        self.resize(1280, 800)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(logged_in_as=logged_in_as)
        self.sidebar.navigate.connect(self._navigate)
        self.sidebar.logout.connect(self.logout_requested.emit)

        self.stack = QStackedWidget()

        self.pages = {
            "dashboard": DashboardPage(),
            "job_posting": JobPostingPage(),
            "candidates": CandidatesPage(),
            "interview": InterviewPage(),
            "reports": ReportsPage(),
            "bias_audit": BiasAuditPage(),
            "integrity": IntegrityLogPage(),
            "settings": SettingsPage(),
        }

        for page in self.pages.values():
            self.stack.addWidget(page)

        self.stack.setCurrentWidget(self.pages["dashboard"])

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central)

    def _navigate(self, key):
        page = self.pages.get(key)
        if page:
            if hasattr(page, "refresh"):
                page.refresh()
            self.stack.setCurrentWidget(page)

    def closeEvent(self, event):
        interview_page = self.pages.get("interview")
        if hasattr(interview_page, "cleanup"):
            interview_page.cleanup()
        event.accept()
