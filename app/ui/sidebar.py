import os

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PySide6.QtCore import Signal, Qt


NAV_ITEMS = [
    ("dashboard", "🏠  Dashboard"),
    ("job_posting", "📝  Create Job Posting"),
    ("candidates", "👥  Candidates"),
    ("interview", "🎙  New Interview"),
    ("live_monitor", "📡  Live Monitor"),
    ("reports", "📊  Candidate Reports"),
    ("bias_audit", "⚖️  Bias Audit"),
    ("integrity", "🛡  Integrity Log"),
    ("settings", "⚙️  Settings"),
]


def visible_nav_items():
    """Candidates take interviews through their own window — recruiters
    should never see the interview tab unless DEV_MODE=1 (Member A's
    direct-UI testing shortcut)."""
    dev_mode = os.environ.get("DEV_MODE") == "1"
    return [
        (key, label) for key, label in NAV_ITEMS
        if key != "interview" or dev_mode
    ]


class Sidebar(QWidget):
    navigate = Signal(str)
    logout = Signal()

    def __init__(self, logged_in_as: str = None):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(230)

        self.buttons = {}
        self.active_key = "dashboard"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(6)

        title = QLabel("InterviewIQ")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("AI Interview Assessment")
        subtitle.setObjectName("BrandSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        for key, label in visible_nav_items():
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._on_click(k))
            layout.addWidget(btn)
            self.buttons[key] = btn

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        if logged_in_as:
            user_lbl = QLabel(f"Logged in as {logged_in_as}")
            user_lbl.setObjectName("BrandSubtitle")
            user_lbl.setWordWrap(True)
            layout.addWidget(user_lbl)

        logout_btn = QPushButton("🚪  Log Out")
        logout_btn.setObjectName("NavButton")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.clicked.connect(self.logout.emit)
        layout.addWidget(logout_btn)

        footer = QLabel("Group Project · v0.1")
        footer.setObjectName("BrandSubtitle")
        layout.addWidget(footer)

        self._set_active("dashboard")

    def _on_click(self, key):
        self._set_active(key)
        self.navigate.emit(key)

    def _set_active(self, key):
        self.active_key = key
        for k, btn in self.buttons.items():
            btn.setObjectName("NavButtonActive" if k == key else "NavButton")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
