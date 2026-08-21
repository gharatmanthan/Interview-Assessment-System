"""
Interview-only window for candidates: hosts the existing InterviewPage with
no sidebar or recruiter navigation. Marks the candidate in_progress on open
and completed when the interview finishes, then shows a dead-end thank-you
screen so the same device can be handed to the next candidate.
"""
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QStackedWidget
from PySide6.QtCore import Qt, Signal

from app.core import db
from app.ui.pages.interview_page import InterviewPage
from app.ui.pages.preflight_check_page import PreflightCheckPage


class DoneScreen(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Interview complete")
        title.setStyleSheet("font-size: 26px; font-weight: 800;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        message = QLabel(
            "Thank you for your time — your responses have been submitted for review."
        )
        message.setObjectName("PageSubtitle")
        message.setAlignment(Qt.AlignCenter)
        layout.addWidget(message)


class CandidateSessionWindow(QMainWindow):
    closed = Signal()

    def __init__(self, candidate):
        super().__init__()
        self.candidate = candidate
        self.setWindowTitle("InterviewIQ — Interview")
        self.resize(1280, 800)

        self.interview_page = InterviewPage(
            candidate_id=candidate.get("candidate_id"),
            job_id=candidate.get("job_id"),
            candidate_name=candidate.get("name"),
            job_title=self._lookup_job_title(candidate.get("job_id")),
        )

        self.done_screen = DoneScreen()
        self.reset_btn = QPushButton("Finish — Hand Device to the Next Candidate")
        self.reset_btn.setObjectName("PrimaryButton")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self.close)
        self.done_screen.layout().addWidget(self.reset_btn, alignment=Qt.AlignCenter)

        self.preflight_page = PreflightCheckPage(
            candidate_id=candidate.get("candidate_id"),
            job_title=self._lookup_job_title(candidate.get("job_id")),
        )
        self.preflight_page.start_requested.connect(self._on_preflight_passed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.preflight_page)
        self.stack.addWidget(self.interview_page)
        self.stack.addWidget(self.done_screen)
        self.setCentralWidget(self.stack)

        db.update_candidate_status(
            candidate["candidate_id"], "in_progress",
            session_id=self.interview_page.session_id,
        )
        self.interview_page.interview_finished.connect(self._on_finished)

    def _on_preflight_passed(self):
        self.stack.setCurrentWidget(self.interview_page)

    def _lookup_job_title(self, job_id):
        if not job_id:
            return None
        for job in db.get_all_job_postings():
            if job["job_id"] == job_id:
                return job["title"]
        return None

    def _on_finished(self):
        db.update_candidate_status(self.candidate["candidate_id"], "completed")
        self.stack.setCurrentWidget(self.done_screen)

    def closeEvent(self, event):
        self.preflight_page.cleanup()
        self.interview_page.cleanup()
        self.closed.emit()
        event.accept()
