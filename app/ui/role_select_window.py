"""
First screen shown at app launch: explicit choice between the recruiter
product (login -> dashboard) and the candidate product (invite code ->
interview). Both are equally weighted — they are two separate user groups
sharing one codebase.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, Signal

CARD_STYLE = """
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    padding: 28px;
    font-size: 17px;
    font-weight: 700;
    color: #1B1F2A;
}
QPushButton:hover {
    border: 2px solid #4F46E5;
}
"""


class RoleSelectWindow(QWidget):
    recruiter_selected = Signal()
    candidate_selected = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("InterviewIQ")
        self.resize(760, 480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 56, 48, 48)
        outer.setSpacing(24)

        title = QLabel("InterviewIQ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 30px; font-weight: 800;")
        outer.addWidget(title)

        subtitle = QLabel("Who is using this device?")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        outer.addWidget(subtitle)

        outer.addStretch(1)

        cards = QHBoxLayout()
        cards.setSpacing(24)

        self.recruiter_btn = self._make_card(
            "I'm a Recruiter",
            "Create job postings, invite candidates,\nand review reports.",
        )
        self.recruiter_btn.clicked.connect(self.recruiter_selected.emit)
        cards.addWidget(self.recruiter_btn)

        self.candidate_btn = self._make_card(
            "I'm a Candidate",
            "Enter your invite code\nto start your interview.",
        )
        self.candidate_btn.clicked.connect(self.candidate_selected.emit)
        cards.addWidget(self.candidate_btn)

        outer.addLayout(cards, stretch=1)
        outer.addStretch(1)

    def _make_card(self, heading, subtitle_text):
        btn = QPushButton(f"{heading}\n\n{subtitle_text}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumSize(280, 210)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setStyleSheet(CARD_STYLE)
        return btn
