from pathlib import Path
from uuid import uuid4
from datetime import datetime

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSizePolicy
)
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap

import cv2

from app.core.question_bank import DEFAULT_QUESTIONS, questions_for_job
from app.core.models import InterviewSession
from app.core import db
from app.candidate.face_recognition import verify_enrolled_face
from app.candidate.integrity import frame_checks, run_checks
from app.engine.explainability import explain_score
from app.engine.rag import retrieve_rubric
from app.engine.scoring import score_answer
from app.engine.stt import transcribe


class TranscriptionWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, audio_path):
        super().__init__()
        self.audio_path = audio_path

    def run(self):
        try:
            self.finished.emit(transcribe(self.audio_path))
        except Exception as error:
            self.failed.emit(str(error))


class InterviewPage(QWidget):
    def __init__(self, candidate_id=None):
        super().__init__()
        self.candidate_id = candidate_id
        self.candidate_name = "Candidate"
        self.job_id = None
        self.job_title = ""
        self.session_started_at = None
        self.session_id = None
        self.live_frame_path = None
        self.capture = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_frame)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._sync_live_state)

        self.questions = DEFAULT_QUESTIONS
        self.current_index = 0
        self.audio_stream = None
        self.audio_chunks = []
        self.transcription_thread = None
        self.transcription_worker = None
        self.frame_count = 0
        self.active_integrity_flags = set()

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

        transcript_title = QLabel("Live Transcript")
        transcript_title.setObjectName("PageSubtitle")
        self.transcript_box = QTextEdit()
        self.transcript_box.setPlaceholderText(
            "Your spoken answer will appear here after you stop recording."
        )
        self.transcript_box.setReadOnly(True)

        qa_layout.addWidget(transcript_title)
        qa_layout.addWidget(self.transcript_box, stretch=1)

        self.record_btn = QPushButton("Start Answer")
        self.record_btn.setObjectName("PrimaryButton")
        self.record_btn.clicked.connect(self._toggle_recording)
        self.record_status = QLabel("Microphone is ready.")
        self.record_status.setObjectName("PageSubtitle")
        qa_layout.addWidget(self.record_btn)
        qa_layout.addWidget(self.record_status)

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

    # --- Speech-to-text handling ---
    def _audio_callback(self, audio_data, frames, time_info, status):
        self.audio_chunks.append(audio_data.copy())

    def _toggle_recording(self):
        if self.audio_stream is not None:
            self._stop_recording()
            return
        try:
            self.audio_chunks = []
            self.audio_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32", callback=self._audio_callback
            )
            self.audio_stream.start()
        except Exception as error:
            self.audio_stream = None
            self.record_status.setText(f"Microphone could not be opened: {error}")
            self.record_status.setStyleSheet("color: #EF4444; font-weight: 600;")
            return
        self.record_btn.setText("Stop Answer")
        self.record_status.setText("Listening...")
        self.record_status.setStyleSheet("color: #EF4444; font-weight: 600;")

    def _stop_recording(self):
        self.audio_stream.stop()
        self.audio_stream.close()
        self.audio_stream = None
        self.record_btn.setEnabled(False)
        self.record_btn.setText("Transcribing...")
        self.record_status.setText("Converting your answer to text...")
        self.record_status.setStyleSheet("color: #F59E0B; font-weight: 600;")
        if not self.audio_chunks:
            self._show_transcription_error("No audio was captured.")
            return

        audio = np.concatenate(self.audio_chunks, axis=0)
        audio_path = Path("data") / "recordings" / f"answer-{uuid4().hex}.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        write_wav(str(audio_path), 16000, audio)
        self.transcription_thread = QThread(self)
        self.transcription_worker = TranscriptionWorker(str(audio_path))
        self.transcription_worker.moveToThread(self.transcription_thread)
        self.transcription_thread.started.connect(self.transcription_worker.run)
        self.transcription_worker.finished.connect(self._show_transcription)
        self.transcription_worker.failed.connect(self._show_transcription_error)
        self.transcription_worker.finished.connect(self._finish_transcription)
        self.transcription_worker.failed.connect(self._finish_transcription)
        self.transcription_thread.start()

    def _show_transcription(self, text):
        if text:
            self.transcript_box.append(text)
            if self.session_id:
                transcript = self.transcript_box.toPlainText()
                db.update_live_interview(
                    self.session_id,
                    transcript=transcript,
                )
                rubric = retrieve_rubric(self.job_title, "technical")
                score = score_answer(
                    self.session_id,
                    f"q-{self.current_index + 1}",
                    "technical",
                    text,
                    rubric,
                )
                explanation = explain_score(
                    self.session_id,
                    score.question_id,
                    text,
                    score.score,
                )
                db.save_competency_score(score)
                db.save_explanation(explanation)
                self.record_status.setText(
                    f"Answer added. Preliminary score: {score.score}/100 "
                    f"({score.confidence:.0%} confidence)."
                )
            else:
                self.record_status.setText("Answer added to the transcript.")
            self.record_status.setStyleSheet("color: #14B8A6; font-weight: 600;")
        else:
            self._show_transcription_error("No speech was detected.")

    def _show_transcription_error(self, message):
        self.record_status.setText(f"Transcription failed: {message}")
        self.record_status.setStyleSheet("color: #EF4444; font-weight: 600;")
        self.record_btn.setEnabled(True)
        self.record_btn.setText("Start Answer")

    def _finish_transcription(self):
        self.transcription_thread.quit()
        self.transcription_thread.wait()
        self.transcription_worker.deleteLater()
        self.transcription_thread.deleteLater()
        self.transcription_worker = None
        self.transcription_thread = None
        self.record_btn.setEnabled(True)
        self.record_btn.setText("Start Answer")

    # --- Camera handling ---
    def set_candidate(self, candidate_id, candidate_name="Candidate"):
        self.candidate_id = candidate_id
        self.candidate_name = candidate_name

    def set_job(self, job_id):
        job = next((item for item in db.get_active_job_postings() if item["id"] == job_id), None)
        if not job or not self.candidate_id:
            return
        self.job_id = job_id
        self.job_title = job["title"]
        self.session_id = uuid4().hex
        self.session_started_at = datetime.utcnow()
        saved_profile = db.get_candidate_profile(self.candidate_id)
        profile = saved_profile["profile"] if saved_profile else {}
        self.questions = questions_for_job(job["title"], job["description"], profile)
        self.current_index = 0
        self.question_text.setText(self.questions[0])
        self.progress_label.setText(f"Question 1 of {len(self.questions)}")
        self.live_frame_path = Path("data") / "live_frames" / f"{self.session_id}.jpg"
        self.live_frame_path.parent.mkdir(parents=True, exist_ok=True)
        db.save_session(InterviewSession(
            session_id=self.session_id,
            candidate_name=self.candidate_name,
            job_title=self.job_title,
            started_at=self.session_started_at,
            status="in_progress",
        ))
        db.start_live_interview(
            self.session_id,
            self.candidate_id,
            self.candidate_name,
            self.questions[self.current_index],
            self.current_index,
        )
        self._record_integrity_flags(run_checks(self.session_id))
        self.live_timer.start(1000)

    def _record_integrity_flags(self, flags):
        for flag in flags:
            key = (flag.flag_type, flag.detail)
            if key not in self.active_integrity_flags:
                db.save_integrity_flag(flag)
                self.active_integrity_flags.add(key)
        if self.active_integrity_flags:
            self.integrity_badge.setText(
                f"Integrity: {len(self.active_integrity_flags)} signal(s) for review"
            )
            self.integrity_badge.setStyleSheet("color: #EF4444; font-weight: 600;")

    def _sync_live_state(self):
        if not self.session_id:
            return
        live_session = db.get_live_interview(self.session_id)
        if not live_session:
            return
        if live_session["question"] != self.question_text.text():
            self.question_text.setText(live_session["question"])
            self.transcript_box.clear()
            self.record_status.setText("Interviewer asked a follow-up question.")

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
            self.integrity_badge.setStyleSheet("color: #14B8A6; font-weight: 600;")
        else:
            self.capture = cv2.VideoCapture(0)
            if not self.capture.isOpened():
                self.video_label.setText("Could not access webcam.\nCheck camera permissions.")
                return
            self.timer.start(30)
            self.start_cam_btn.setText("Stop Camera")
            self.integrity_badge.setText("Face check: Checking...")
            self.integrity_badge.setObjectName("Badge-clear")

    def _update_frame(self):
        if not self.capture:
            return
        ret, frame = self.capture.read()
        if not ret:
            return
        self.frame_count += 1
        if self.session_id and self.frame_count % 30 == 0:
            self._record_integrity_flags(frame_checks(self.session_id, frame))
        face_verified, face_message = verify_enrolled_face(self.candidate_id, frame)
        self.integrity_badge.setText(f"Face check: {face_message}")
        if face_verified:
            self.integrity_badge.setObjectName("Badge-clear")
            self.integrity_badge.setStyleSheet("color: #14B8A6; font-weight: 600;")
        else:
            self.integrity_badge.setObjectName("Badge-flagged")
            self.integrity_badge.setStyleSheet("color: #EF4444; font-weight: 600;")
        if self.active_integrity_flags:
            self.integrity_badge.setText(
                f"Integrity: {len(self.active_integrity_flags)} signal(s) for review"
            )
            self.integrity_badge.setStyleSheet("color: #EF4444; font-weight: 600;")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if self.live_frame_path:
            frame_path = self.live_frame_path.with_suffix(".tmp.jpg")
            cv2.imwrite(str(frame_path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            frame_path.replace(self.live_frame_path)
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
        if self.session_id:
            db.update_live_interview(
                self.session_id,
                question=self.questions[self.current_index],
                question_index=self.current_index,
                transcript="",
            )

    def cleanup(self):
        self.live_timer.stop()
        if self.audio_stream is not None:
            self._stop_recording()
        if self.transcription_thread is not None and self.transcription_thread.isRunning():
            self.transcription_thread.quit()
            self.transcription_thread.wait()
        if self.timer.isActive():
            self.timer.stop()
        if self.capture:
            self.capture.release()
        if self.session_id:
            db.update_live_interview(self.session_id, status="completed")
            db.save_session(InterviewSession(
                session_id=self.session_id,
                candidate_name=self.candidate_name,
                job_title=self.job_title,
                transcript=self.transcript_box.toPlainText(),
                started_at=self.session_started_at or datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="complete",
            ))
        if self.live_frame_path and self.live_frame_path.exists():
            self.live_frame_path.unlink()
