from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PySide6.QtCore import Signal, Qt


NAV_ITEMS = [
    ("dashboard", "🏠  Dashboard"),
    ("job_posting", "📝  Create Job Posting"),
    ("interview", "🎙  New Interview"),
    ("reports", "📊  Candidate Reports"),
    ("bias_audit", "⚖️  Bias Audit"),
    ("integrity", "🛡  Integrity Log"),
    ("settings", "⚙️  Settings"),
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
        layout.addSpacing(28)

        visible_items = NAV_ITEMS if user_role == "interviewer" else [
            item for item in NAV_ITEMS if item[0] in {"dashboard", "interview", "settings"}
        ]
        for key, label in visible_items:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._on_click(k))
            layout.addWidget(btn)
            self.buttons[key] = btn

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

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
