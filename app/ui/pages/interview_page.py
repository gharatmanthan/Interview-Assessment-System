from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap

import cv2
from uuid import uuid4

from app.core.question_bank import DEFAULT_QUESTIONS
from app.core.db import save_integrity_flag, save_session
from app.core.models import InterviewSession
from app.candidate.integrity import ExternalDeviceMonitor


class InterviewPage(QWidget):
    def __init__(self):
        super().__init__()
        self.capture = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_frame)
        self.integrity_timer = QTimer()
        self.integrity_timer.timeout.connect(self._poll_integrity)

        self.questions = DEFAULT_QUESTIONS
        self.current_index = 0
        self.is_recording = False
        self.session_id = f"session-{uuid4().hex[:8]}"
        self.session_saved = False
        self.integrity_flag_count = 0
        self.device_monitor = ExternalDeviceMonitor(self.session_id)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        header = QLabel("New Interview")
        header.setObjectName("PageTitle")
        sub = QLabel("Live session — question flow, transcription, and integrity monitoring")
        sub.setObjectName("PageSubtitle")
        root.addWidget(header)
        root.addWidget(sub)

        body = QHBoxLayout()
        body.setSpacing(20)

        # --- Left: Camera feed ---
        cam_card = QWidget()
        cam_card.setObjectName("Card")
        cam_layout = QVBoxLayout(cam_card)
        cam_layout.setContentsMargins(16, 16, 16, 16)

        self.video_label = QLabel("Camera preview will appear here.\nClick 'Start Camera' to begin.")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(480, 360)
        self.video_label.setStyleSheet(
            "background-color: #111827; color: #9CA3AF; border-radius: 8px; font-size: 12px;"
        )
        cam_layout.addWidget(self.video_label)

        cam_btn_row = QHBoxLayout()
        self.start_cam_btn = QPushButton("Start Camera")
        self.start_cam_btn.setObjectName("PrimaryButton")
        self.start_cam_btn.clicked.connect(self._toggle_camera)

        self.integrity_badge = QLabel("Integrity: Not Monitoring")
        self.integrity_badge.setObjectName("Badge-clear")

        cam_btn_row.addWidget(self.start_cam_btn)
        cam_btn_row.addStretch()
        cam_btn_row.addWidget(self.integrity_badge)
        cam_layout.addLayout(cam_btn_row)

        self.integrity_log = QTextEdit()
        self.integrity_log.setReadOnly(True)
        self.integrity_log.setMaximumHeight(96)
        self.integrity_log.setPlaceholderText("External device alerts will appear here during the interview.")
        cam_layout.addWidget(self.integrity_log)

        body.addWidget(cam_card, stretch=3)

        # --- Right: Question + transcript panel ---
        qa_card = QWidget()
        qa_card.setObjectName("Card")
        qa_layout = QVBoxLayout(qa_card)
        qa_layout.setContentsMargins(20, 20, 20, 20)
        qa_layout.setSpacing(12)

        q_label_title = QLabel("Current Question")
        q_label_title.setObjectName("PageSubtitle")
        self.question_text = QLabel(self.questions[0])
        self.question_text.setWordWrap(True)
        self.question_text.setStyleSheet("font-size: 15px; font-weight: 600; color: #1B1F2A;")

        qa_layout.addWidget(q_label_title)
        qa_layout.addWidget(self.question_text)

        transcript_title = QLabel("Live Transcript (placeholder)")
        transcript_title.setObjectName("PageSubtitle")
        self.transcript_box = QTextEdit()
        self.transcript_box.setPlaceholderText(
            "Transcription will appear here once speech-to-text is wired in (Whisper)."
        )
        self.transcript_box.setReadOnly(False)

        qa_layout.addWidget(transcript_title)
        qa_layout.addWidget(self.transcript_box, stretch=1)

        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setObjectName("SecondaryButton")
        self.prev_btn.clicked.connect(self._prev_question)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("PrimaryButton")
        self.next_btn.clicked.connect(self._next_question)

        self.progress_label = QLabel(f"Question 1 of {len(self.questions)}")
        self.progress_label.setObjectName("PageSubtitle")

        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.progress_label)
        nav_row.addStretch()
        nav_row.addWidget(self.next_btn)

        qa_layout.addLayout(nav_row)

        body.addWidget(qa_card, stretch=2)
        root.addLayout(body, stretch=1)

    # --- Camera handling ---
    def _toggle_camera(self):
        if self.timer.isActive():
            self.timer.stop()
            if self.capture:
                self.capture.release()
                self.capture = None
            self.video_label.setText("Camera preview will appear here.\nClick 'Start Camera' to begin.")
            self.start_cam_btn.setText("Start Camera")
            self.integrity_badge.setText("Integrity: Not Monitoring")
            self.integrity_badge.setObjectName("Badge-clear")
            self._stop_integrity_monitoring()
        else:
            self.capture = cv2.VideoCapture(0)
            if not self.capture.isOpened():
                self.video_label.setText("Could not access webcam.\nCheck camera permissions.")
                return
            self.timer.start(30)
            self.start_cam_btn.setText("Stop Camera")
            self._start_integrity_monitoring()
            self.integrity_badge.setText("Integrity: Monitoring")
            self.integrity_badge.setObjectName("Badge-flagged")

    def _update_frame(self):
        if not self.capture:
            return
        ret, frame = self.capture.read()
        if not ret:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

    # --- Question navigation ---
    def _next_question(self):
        if self.current_index < len(self.questions) - 1:
            self.current_index += 1
            self._refresh_question()

    def _prev_question(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._refresh_question()

    def _refresh_question(self):
        self.question_text.setText(self.questions[self.current_index])
        self.progress_label.setText(f"Question {self.current_index + 1} of {len(self.questions)}")

    def _start_integrity_monitoring(self):
        if not self.session_saved:
            save_session(
                InterviewSession(
                    session_id=self.session_id,
                    candidate_name="Local Candidate",
                    job_title="Interview Session",
                )
            )
            self.session_saved = True

        self.device_monitor.start()
        self.integrity_timer.start(5000)
        if self.device_monitor.is_supported:
            self._append_integrity_log("Device monitor started. Current devices captured as baseline.")
        else:
            self._append_integrity_log("Device monitor is only available on Windows in this build.")

    def _stop_integrity_monitoring(self):
        if self.integrity_timer.isActive():
            self.integrity_timer.stop()

    def _poll_integrity(self):
        for flag in self.device_monitor.poll():
            save_integrity_flag(flag)
            self.integrity_flag_count += 1
            self.integrity_badge.setText(f"Integrity: {self.integrity_flag_count} Flag(s)")
            self._append_integrity_log(flag.detail)

    def _append_integrity_log(self, message):
        self.integrity_log.append(message)

    def cleanup(self):
        if self.timer.isActive():
            self.timer.stop()
        self._stop_integrity_monitoring()
        if self.capture:
            self.capture.release()
