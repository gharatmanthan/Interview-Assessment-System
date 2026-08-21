"""
Candidate entry: invite-code validation followed by a lightweight consent
step. Candidates never see a login form — the invite code is their only
credential. On consent, emits `entry_success` with the full candidate dict.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal

from app.core import db


def evaluate_invite_code(candidate):
    """Pure decision logic for an invite-code lookup result.

    Returns (ok: bool, message: str) — message is empty when ok.
    """
    if not candidate:
        return False, "Invalid invite code"
    status = candidate.get("status")
    if status == "completed":
        return False, "This interview has already been completed."
    if status == "expired":
        return False, "This invite code has expired."
    return True, ""


class CodeEntryPage(QWidget):
    def __init__(self, on_submit):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignHCenter)

        title = QLabel("Candidate Entry")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        prompt = QLabel("Enter your invite code")
        prompt.setObjectName("PageSubtitle")
        prompt.setAlignment(Qt.AlignCenter)
        layout.addWidget(prompt)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. Xk7Bp2")
        self.code_input.setMinimumWidth(280)
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.returnPressed.connect(on_submit)
        input_row = QHBoxLayout()
        input_row.addStretch()
        input_row.addWidget(self.code_input)
        input_row.addStretch()
        layout.addLayout(input_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #DC2626; font-size: 13px;")
        self.error_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.error_label)

        self.submit_btn = QPushButton("Continue")
        self.submit_btn.setObjectName("PrimaryButton")
        self.submit_btn.setCursor(Qt.PointingHandCursor)
        self.submit_btn.clicked.connect(on_submit)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.submit_btn)
        button_row.addStretch()
        layout.addLayout(button_row)


class ConsentPage(QWidget):
    def __init__(self, on_start):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 48, 56, 48)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignHCenter)

        title = QLabel("Before you begin")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        details = QLabel(
            "During your interview:\n"
            "  •  Your camera and microphone will record video and audio.\n"
            "  •  An AI system will score your answers against the job requirements.\n"
            "  •  Basic device-integrity checks will run to keep the process fair."
        )
        details.setWordWrap(True)
        layout.addWidget(details)

        self.consent_checkbox = QCheckBox("I understand and I'm ready to begin")
        self.consent_checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self.consent_checkbox)

        self.start_btn = QPushButton("Start Interview")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(on_start)
        layout.addWidget(self.start_btn, alignment=Qt.AlignCenter)

    def _on_toggled(self, checked):
        self.start_btn.setEnabled(checked)


class CandidateEntryWindow(QWidget):
    entry_success = Signal(dict)
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("InterviewIQ — Candidate Entry")
        self.resize(560, 480)
        self.candidate = None

        self.stack = QStackedWidget()

        code_page = CodeEntryPage(self._validate_code)
        consent_page = ConsentPage(self._start_interview)
        self.stack.addWidget(code_page)
        self.stack.addWidget(consent_page)

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(self.stack)
        outer.addStretch(1)

        self.code_input = code_page.code_input
        self.submit_btn = code_page.submit_btn
        self.error_label = code_page.error_label
        self.consent_checkbox = consent_page.consent_checkbox
        self.start_btn = consent_page.start_btn

    def _validate_code(self):
        code = self.code_input.text().strip()
        candidate = db.get_candidate_by_invite_code(code)
        ok, message = evaluate_invite_code(candidate)
        if not ok:
            self.error_label.setText(message)
            return
        self.error_label.setText("")
        self.candidate = candidate
        self.stack.setCurrentIndex(1)

    def _start_interview(self):
        if self.candidate:
            self.entry_success.emit(self.candidate)

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()
