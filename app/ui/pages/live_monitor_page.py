"""
Recruiter-facing live monitor (integrated from the teammate's interviewer
interview page): watches active candidate sessions via the live_interviews
table, shows the candidate's camera feed + transcript, and can push a
follow-up question straight onto the candidate's screen.
"""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core import db


class LiveMonitorPage(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_session_id = None
        self.latest_sessions = []

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        title = QLabel("Live Monitor")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Watch active interviews, read live transcripts, and ask follow-up questions")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(20)

        sessions_panel = QWidget()
        sessions_panel.setObjectName("Card")
        sessions_layout = QVBoxLayout(sessions_panel)
        sessions_layout.setContentsMargins(16, 16, 16, 16)
        sessions_layout.addWidget(QLabel("Active Candidates"))
        self.sessions_list = QListWidget()
        self.sessions_list.currentRowChanged.connect(self._select_session)
        sessions_layout.addWidget(self.sessions_list)
        body.addWidget(sessions_panel, stretch=1)

        monitor_panel = QWidget()
        monitor_panel.setObjectName("Card")
        monitor_layout = QVBoxLayout(monitor_panel)
        monitor_layout.setContentsMargins(20, 20, 20, 20)
        self.candidate_label = QLabel("No active candidate selected")
        self.candidate_label.setObjectName("PageSubtitle")
        self.question_label = QLabel("A candidate's current question will appear here.")
        self.question_label.setWordWrap(True)
        self.question_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #1B1F2A;")
        monitor_layout.addWidget(self.candidate_label)
        monitor_layout.addWidget(self.question_label)

        self.video_label = QLabel("Candidate camera feed will appear here when the camera starts.")
        self.video_label.setMinimumHeight(220)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(
            "background-color: #111827; color: #9CA3AF; border-radius: 8px;"
        )
        monitor_layout.addWidget(self.video_label)

        transcript_title = QLabel("Live Candidate Transcript")
        transcript_title.setObjectName("PageSubtitle")
        monitor_layout.addWidget(transcript_title)
        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        self.transcript_box.setPlaceholderText("The candidate's transcribed answers will appear here.")
        monitor_layout.addWidget(self.transcript_box, stretch=1)

        ask_row = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Ask a follow-up question...")
        self.question_input.returnPressed.connect(self.send_question)
        ask_row.addWidget(self.question_input, stretch=1)
        self.send_button = QPushButton("Send Question")
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.clicked.connect(self.send_question)
        ask_row.addWidget(self.send_button)
        monitor_layout.addLayout(ask_row)
        self.status_label = QLabel("Waiting for a candidate to start an interview.")
        self.status_label.setObjectName("PageSubtitle")
        monitor_layout.addWidget(self.status_label)
        body.addWidget(monitor_panel, stretch=3)
        root.addLayout(body, stretch=1)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_sessions)
        self.refresh_timer.start(1000)
        self.refresh_sessions()

    def refresh(self):
        """Called by MainWindow when navigating to this page."""
        self.refresh_sessions()

    def refresh_sessions(self):
        sessions = db.get_live_interviews()
        selected_id = self.selected_session_id
        self.latest_sessions = sessions
        self.sessions_list.blockSignals(True)
        self.sessions_list.clear()
        selected_row = -1
        for row, session in enumerate(sessions):
            self.sessions_list.addItem(
                f"{session['candidate_name']}\nQuestion {session['question_index'] + 1}"
            )
            if session["session_id"] == selected_id:
                selected_row = row
        self.sessions_list.blockSignals(False)

        if selected_row >= 0:
            self.sessions_list.setCurrentRow(selected_row)
            self._show_session(sessions[selected_row])
        elif sessions:
            self.sessions_list.setCurrentRow(0)
        else:
            self.selected_session_id = None
            self.candidate_label.setText("No active candidate selected")
            self.question_label.setText("A candidate's current question will appear here.")
            self.transcript_box.clear()
            self.status_label.setText("Waiting for a candidate to start an interview.")

    def _select_session(self, row):
        if row < 0 or row >= len(self.latest_sessions):
            return
        self.selected_session_id = self.latest_sessions[row]["session_id"]
        self._show_session(self.latest_sessions[row])

    def _show_session(self, session):
        self.candidate_label.setText(f"Candidate: {session['candidate_name']}")
        self.question_label.setText(session["question"])
        self.transcript_box.setPlainText(session["transcript"])
        # Read the bytes and close the handle immediately: constructing
        # QPixmap from a path can hold the file open on Windows while decoding,
        # which blocks the candidate side's atomic replace() onto this same
        # file (WinError 5) and freezes the live feed.
        pixmap = QPixmap()
        try:
            frame_bytes = (
                db.DB_PATH.parent / "live_frames" / f"{session['session_id']}.jpg"
            ).read_bytes()
            if not pixmap.loadFromData(frame_bytes):
                pixmap = QPixmap()
        except OSError:
            pixmap = QPixmap()  # frame not written yet this tick
        if not pixmap.isNull():
            self.video_label.setPixmap(
                pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        self.status_label.setText("Live session connected. Your next question will appear on the candidate's screen.")

    def send_question(self):
        question = self.question_input.text().strip()
        if not self.selected_session_id or not question:
            return
        db.update_live_interview(self.selected_session_id, question=question, transcript="")
        self.question_input.clear()
        self.question_label.setText(question)
        self.status_label.setText("Question sent to the candidate.")

    def cleanup(self):
        self.refresh_timer.stop()
