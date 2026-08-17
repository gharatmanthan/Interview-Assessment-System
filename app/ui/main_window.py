from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget

from app.ui.sidebar import Sidebar
from app.ui.pages.candidate_dashboard import CandidateDashboard
from app.ui.pages.interviewer_dashboard import InterviewerDashboard
from app.ui.pages.interview_page import InterviewPage
from app.ui.pages.placeholder_page import PlaceholderPage


class MainWindow(QMainWindow):
    # Added user_role parameter to determine which dashboard to load
    def __init__(self, user_role="candidate"):
        super().__init__()
        self.user_role = user_role
        self.setWindowTitle("InterviewIQ — AI Interview Assessment System")
        self.resize(1280, 800)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self._navigate)

        self.stack = QStackedWidget()

        # Conditionally load the appropriate dashboard widget
        if self.user_role == "interviewer":
            dashboard_page = InterviewerDashboard()
        else:
            dashboard_page = CandidateDashboard()
            dashboard_page.start_interview_requested.connect(lambda: self._navigate("interview"))

        self.pages = {
            "dashboard": dashboard_page,
            "interview": InterviewPage(),
            "reports": PlaceholderPage(
                "Candidate Reports",
                "Score breakdowns with explainability overlays",
                "This section will list completed interviews with:\n\n"
                "  • Overall score and sub-scores (content, delivery, confidence)\n"
                "  • SHAP/LIME-based explanation of what drove each score\n"
                "  • Per-question transcript and timing breakdown\n\n"
                "Not yet implemented — will be built once the scoring pipeline is in place.",
            ),
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

        self.setCentralWidget(central)

    def _navigate(self, key):
        page = self.pages.get(key)
        if page:
            self.stack.setCurrentWidget(page)

    def closeEvent(self, event):
        interview_page = self.pages.get("interview")
        if hasattr(interview_page, "cleanup"):
            interview_page.cleanup()
        event.accept()