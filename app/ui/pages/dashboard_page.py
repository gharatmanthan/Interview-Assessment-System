from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt


class StatCard(QWidget):
    def __init__(self, title, value, hint, accent="#5B5FEF"):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("PageSubtitle")

        value_lbl = QLabel(value)
        value_lbl.setStyleSheet(f"font-size: 28px; font-weight: 700; color: {accent};")

        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet("font-size: 11px; color: #6B7280;")

        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        layout.addWidget(hint_lbl)


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(20)

        header = QLabel("Dashboard")
        header.setObjectName("PageTitle")
        sub = QLabel("Overview of interviews, bias signals, and integrity flags")
        sub.setObjectName("PageSubtitle")

        layout.addWidget(header)
        layout.addWidget(sub)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.addWidget(StatCard("Interviews Conducted", "0", "This session", "#5B5FEF"), 0, 0)
        grid.addWidget(StatCard("Avg. Explainability Score", "—", "Confidence in scoring", "#14B8A6"), 0, 1)
        grid.addWidget(StatCard("Bias Flags Raised", "0", "Across demographic proxies", "#F59E0B"), 0, 2)
        grid.addWidget(StatCard("Integrity Flags", "0", "Suspected AI-assisted answers", "#EF4444"), 0, 3)
        layout.addLayout(grid)

        placeholder = QLabel(
            "No interviews recorded yet.\n\nStart a new interview from the sidebar to begin "
            "collecting scoring, explainability, and integrity data."
        )
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 60px;")
        placeholder.setObjectName("Card")

        layout.addWidget(placeholder, stretch=1)
