from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget

from app.ui.sidebar import Sidebar
from app.ui.pages.candidate_dashboard import CandidateDashboard
from app.ui.pages.interviewer_dashboard import InterviewerDashboard
from app.ui.pages.job_posting_page import JobPostingPage
from app.ui.pages.interview_page import InterviewPage
from app.ui.pages.interviewer_interview_page import InterviewerInterviewPage
from app.ui.pages.login_page import CandidateLoginPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.ui.pages.reports_page import ReportsPage


class MainWindow(QMainWindow):
    # Added user_role parameter to determine which dashboard to load
    def __init__(self, user_role="candidate"):
        super().__init__()
        self.user_role = user_role
        from app.core import db
        db.init_db()
        self.setWindowTitle("InterviewIQ — AI Interview Assessment System")
        self.resize(1360, 860)
        self.setMinimumSize(1040, 680)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(user_role=self.user_role)
        self.sidebar.navigate.connect(self._navigate)

        self.stack = QStackedWidget()

        # Conditionally load the appropriate dashboard widget
        if self.user_role == "interviewer":
            dashboard_page = InterviewerDashboard()
        else:
            dashboard_page = CandidateDashboard()
            dashboard_page.start_interview_requested.connect(self._start_candidate_interview)

        self.pages = {
            "dashboard": dashboard_page,
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
            "settings": PlaceholderPage(
                "Settings",
                "Application configuration",
                "Camera/mic device selection, scoring model configuration, "
                "and export settings will live here.",
            ),
        }

        for page in self.pages.values():
            self.stack.addWidget(page)

        self.stack.setCurrentWidget(self.pages["dashboard"])

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)

        if self.user_role == "candidate":
            self.login_page = CandidateLoginPage()
            self.login_page.authenticated.connect(self._show_candidate_app)
            layout.insertWidget(0, self.login_page, stretch=1)
            self.sidebar.hide()
            self.stack.hide()

        self.setCentralWidget(central)

    def _show_candidate_app(self, account):
        self.pages["dashboard"].set_candidate(account["candidate_id"])
        self.pages["interview"].set_candidate(account["candidate_id"], account["full_name"])
        self.sidebar.show()
        self.stack.show()
        self.login_page.hide()
        self.setWindowTitle(f"InterviewIQ — {account['full_name']}")

    def _start_candidate_interview(self, job_id):
        self.pages["interview"].set_job(job_id)
        self._navigate("interview")

    def _navigate(self, key):
        page = self.pages.get(key)
        if page:
            self.stack.setCurrentWidget(page)

    def closeEvent(self, event):
        interview_page = self.pages.get("interview")
        if hasattr(interview_page, "cleanup"):
            interview_page.cleanup()
        dashboard_page = self.pages.get("dashboard")
        if hasattr(dashboard_page, "cleanup"):
            dashboard_page.cleanup()
        event.accept()