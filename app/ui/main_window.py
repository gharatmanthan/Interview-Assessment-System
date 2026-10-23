from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget

from app.ui.sidebar import Sidebar
from app.ui.pages.candidate_dashboard import CandidateDashboard
from app.ui.pages.candidates_page import CandidatesPage
from app.ui.pages.interviewer_dashboard import InterviewerDashboard
from app.ui.pages.job_posting_page import JobPostingPage
from app.ui.pages.interview_page import InterviewPage
from app.ui.pages.interviewer_interview_page import InterviewerInterviewPage
from app.ui.pages.login_page import RoleLoginPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, user_role="candidate"):
        super().__init__()
        self.user_role = user_role
        from app.core import db
        db.init_db()
        self.setWindowTitle("InterviewIQ - AI Interview Assessment System")
        self.resize(1360, 860)
        self.setMinimumSize(1040, 680)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(user_role=self.user_role)
        self.sidebar.navigate.connect(self._navigate)

        self.stack = QStackedWidget()

        if self.user_role == "interviewer":
            dashboard_page = InterviewerDashboard()
        else:
            dashboard_page = CandidateDashboard()
            dashboard_page.interview_ready.connect(self._start_candidate_interview)

        self.pages = {
            "dashboard": dashboard_page,
            "candidates": CandidatesPage() if self.user_role == "interviewer" else PlaceholderPage(
                "Candidates", "Candidate accounts", "Candidate accounts are managed by interviewers."
            ),
            "job_posting": JobPostingPage() if self.user_role == "interviewer" else PlaceholderPage(
                "Job Postings", "Available interview opportunities", "Job postings are managed by interviewers."
            ),
            "interview": InterviewerInterviewPage() if self.user_role == "interviewer" else InterviewPage(),
            "reports": ReportsPage(),
            "bias_audit": PlaceholderPage(
                "Bias Audit",
                "Fairness metrics across candidate groups",
                "This section will surface:\n\n"
                "  • Score distributions across demographic proxies\n"
                "  • Statistical parity / disparate impact indicators\n"
                "  • Flags when scoring patterns diverge significantly across groups\n\n"
                "Not yet implemented — depends on collected interview data.",
            ),
            "integrity": PlaceholderPage(
                "Integrity Log",
                "Suspected AI-assisted answers during live interviews",
                "This section will log:\n\n"
                "  • Gaze-tracking anomalies (reading off-screen)\n"
                "  • Response latency anomalies\n"
                "  • Linguistic markers consistent with AI-generated answers\n\n"
                "Not yet implemented — this is the core novel research contribution.",
            ),
            "settings": SettingsPage(),
        }

        for page in self.pages.values():
            self.stack.addWidget(page)

        self.stack.setCurrentWidget(self.pages["dashboard"])

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)

        self.login_page = RoleLoginPage(self.user_role)
        self.login_page.authenticated.connect(self._show_authenticated_app)
        layout.insertWidget(0, self.login_page, stretch=1)
        self.sidebar.hide()
        self.stack.hide()

        self.setCentralWidget(central)

    def _show_candidate_app(self, account):
        name = account.get("full_name", "Candidate")
        self.pages["dashboard"].set_candidate(account["candidate_id"], name)
        self.pages["interview"].set_candidate(account["candidate_id"], name)
        self.sidebar.set_user(name)
        self.sidebar.show()
        self.stack.show()
        self.login_page.hide()
        self.setWindowTitle(f"InterviewIQ - {name}")

    def _show_authenticated_app(self, account):
        if self.user_role == "candidate":
            self._show_candidate_app(account)
            return
        self.sidebar.set_user(account.get("full_name", "Interviewer"))
        self.sidebar.show()
        self.stack.show()
        self.login_page.hide()
        self.pages["dashboard"].set_navigate_callback(self._navigate)
        self.setWindowTitle("InterviewIQ - Interviewer workspace")
        self.pages["dashboard"].start_refreshing()
        self.pages["interview"].start_refreshing()
        self.pages["reports"].start_refreshing()

    def _start_candidate_interview(self, job_id: int, questions: list):
        if hasattr(self.pages["dashboard"], "cleanup"):
            self.pages["dashboard"].cleanup()
        started = self.pages["interview"].set_job(
            job_id, questions if questions else None
        )
        if started:
            self._navigate("interview")

    def _navigate(self, key):
        page = self.pages.get(key)
        if page:
            if self.user_role == "candidate" and key != "interview":
                interview_page = self.pages.get("interview")
                if (
                    interview_page is not None
                    and getattr(interview_page, "session_id", None)
                ):
                    interview_page.record_application_switch(
                        "Candidate navigated away from the active interview page."
                    )
            if key == "reports" and hasattr(page, "refresh"):
                page.refresh()
            self.stack.setCurrentWidget(page)

    def closeEvent(self, event):
        interview_page = self.pages.get("interview")
        if hasattr(interview_page, "cleanup"):
            interview_page.cleanup()
        dashboard_page = self.pages.get("dashboard")
        if hasattr(dashboard_page, "cleanup"):
            dashboard_page.cleanup()
        event.accept()
