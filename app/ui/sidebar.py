from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PySide6.QtCore import Signal, Qt


INTERVIEWER_NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("candidates", "Candidates"),
    ("job_posting", "Job postings"),
    ("interview", "Live monitor"),
    ("reports", "Candidate reports"),
    ("bias_audit", "Bias audit"),
    ("integrity", "Integrity log"),
    ("settings", "Settings"),
]

CANDIDATE_NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("interview", "My interview"),
    ("settings", "Settings"),
]


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, logged_in_as: str = None, user_role: str = "candidate"):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(230)

        self.buttons = {}
        self.active_key = "dashboard"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 28, 18, 24)
        layout.setSpacing(7)

        title = QLabel("InterviewIQ")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("AI Interview Assessment")
        subtitle.setObjectName("BrandSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Role / User indicator
        role_title = "Interviewer workspace" if user_role == "interviewer" else "Candidate workspace"
        self.user_badge = QLabel(logged_in_as or role_title)
        self.user_badge.setObjectName("RoleBadge")
        layout.addWidget(self.user_badge)
        layout.addSpacing(20)

        visible_items = INTERVIEWER_NAV_ITEMS if user_role == "interviewer" else CANDIDATE_NAV_ITEMS
        for key, label in visible_items:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._on_click(k))
            layout.addWidget(btn)
            self.buttons[key] = btn

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        footer = QLabel("Interview assessment platform")
        footer.setObjectName("BrandSubtitle")
        layout.addWidget(footer)

        self._set_active("dashboard")

    def set_user(self, name: str):
        self.user_badge.setText(name)

    def _on_click(self, key):
        self._set_active(key)
        self.navigate.emit(key)

    def _set_active(self, key):
        self.active_key = key
        for k, btn in self.buttons.items():
            btn.setObjectName("NavButtonActive" if k == key else "NavButton")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
