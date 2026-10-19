from pathlib import Path
from uuid import uuid4
from datetime import datetime
import json
import os

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSizePolicy, QSlider
)
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap

import cv2

from app.core.question_bank import DEFAULT_QUESTIONS, questions_for_job
from app.core.models import InterviewSession
from app.core import db
from app.candidate.face_recognition import face_match_confidence
from app.candidate.integrity import FaceIntegrityMonitor, run_checks
from app.engine.explainability import explain_score
from app.engine.rag import retrieve_rubric
from app.engine.scoring import score_answer
from app.engine.stt import transcribe


# --------------------------------------------------------------------------
# Workers
# --------------------------------------------------------------------------

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


class NextQuestionWorker(QObject):
    """Generates the next question dynamically after each answer."""
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, job_title: str, job_description: str,
                 resume_profile: dict, history: list):
        super().__init__()
        self.job_title = job_title
        self.job_description = job_description
        self.resume_profile = resume_profile
        self.history = history

    def run(self):
        try:
            from app.engine.question_generator import generate_next_question
            q = generate_next_question(
                self.job_title, self.job_description, self.resume_profile, self.history
            )
            self.finished.emit(q)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# --------------------------------------------------------------------------
# Interview page
# --------------------------------------------------------------------------

class InterviewPage(QWidget):
    def __init__(self, candidate_id=None):
        super().__init__()
        self.candidate_id = candidate_id
        self.candidate_name = "Candidate"
        self.job_id = None
        self.job_title = ""
        self.job_description = ""
        self.resume_profile = {}
        self.session_started_at = None
        self.session_id = None
        self.live_frame_path = None
        self.capture = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_frame)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._sync_live_state)

        # Dynamic question state
        self.interview_history: list[dict] = []   # [{question, answer, score, category}]
        self.initial_questions: list[str] = []    # pre-generated Q1 (from dashboard)
        self.current_question: str = ""
        self.current_question_number: int = 0
        self.waiting_for_approval: bool = False   # True while next Q is pending

        self.audio_stream = None
        self.audio_chunks = []
        self.transcription_thread = None
        self.transcription_worker = None
        self._nq_thread = None
        self._nq_worker = None
        self.frame_count = 0
        self.active_integrity_flags = set()
        self.face_monitor = FaceIntegrityMonitor()
        self.session_finished = False

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

        q_header_row = QHBoxLayout()
        q_label_title = QLabel("Current Question")
        q_label_title.setObjectName("PageSubtitle")
        self.category_tag = QLabel("")
        self.category_tag.setObjectName("CategoryTag")
        self.category_tag.setVisible(False)
        self.progress_label = QLabel("Question 1 of 8")
        self.progress_label.setObjectName("PageSubtitle")
        self.progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        q_header_row.addWidget(q_label_title)
        q_header_row.addWidget(self.category_tag)
        q_header_row.addStretch()
        q_header_row.addWidget(self.progress_label)

        self.question_text = QLabel("Your question will appear here when the interview starts.")
        self.question_text.setWordWrap(True)
        self.question_text.setStyleSheet("font-size: 15px; font-weight: 600; color: #1B1F2A;")

        self.waiting_lbl = QLabel("⏳  Interviewer is reviewing the next question...")
        self.waiting_lbl.setObjectName("WaitingLabel")
        self.waiting_lbl.setVisible(False)

        qa_layout.addLayout(q_header_row)
        qa_layout.addWidget(self.question_text)
        qa_layout.addWidget(self.waiting_lbl)

        transcript_title = QLabel("Live Transcript")
        transcript_title.setObjectName("PageSubtitle")
        self.transcript_box = QTextEdit()
        self.transcript_box.setPlaceholderText(
            "Your spoken answer will appear here after you stop recording."
        )
        self.transcript_box.setReadOnly(True)

        qa_layout.addWidget(transcript_title)
        qa_layout.addWidget(self.transcript_box, stretch=1)

        self.record_btn = QPushButton("Start answer")
        self.record_btn.setObjectName("PrimaryButton")
        self.record_btn.clicked.connect(self._toggle_recording)
        confidence_row = QHBoxLayout()
        confidence_label = QLabel("How confident are you in this answer?")
        confidence_label.setObjectName("PageSubtitle")
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(1, 5)
        self.confidence_slider.setValue(3)
        self.confidence_slider.setTickPosition(QSlider.TicksBelow)
        self.confidence_slider.setTickInterval(1)
        self.confidence_value = QLabel("3/5")
        self.confidence_slider.valueChanged.connect(
            lambda value: self.confidence_value.setText(f"{value}/5")
        )
        confidence_row.addWidget(confidence_label)
        confidence_row.addWidget(self.confidence_slider, stretch=1)
        confidence_row.addWidget(self.confidence_value)
        self.record_status = QLabel("Microphone is ready.")
        self.record_status.setObjectName("PageSubtitle")
        qa_layout.addWidget(self.record_btn)
        qa_layout.addLayout(confidence_row)
        qa_layout.addWidget(self.record_status)

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
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as stream_err:
                pass
            finally:
                self.audio_stream = None

        self.record_btn.setEnabled(False)
        self.record_btn.setText("Transcribing...")
        self.record_status.setText("Converting your answer to text...")
        self.record_status.setStyleSheet("color: #F59E0B; font-weight: 600;")

        if not self.audio_chunks:
            self._show_transcription_error("No audio was captured.")
            return

        try:
            audio = np.concatenate(self.audio_chunks, axis=0)
            if audio.size == 0:
                self._show_transcription_error("Audio recording was empty.")
                return
            audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)
            audio_path = Path("data") / "recordings" / f"answer-{uuid4().hex}.wav"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            write_wav(str(audio_path), 16000, audio)
        except Exception as prep_err:
            self._show_transcription_error(f"Error saving audio: {prep_err}")
            return

        # Safe non-blocking worker thread pattern
        self.transcription_thread = QThread()
        self.transcription_worker = TranscriptionWorker(str(audio_path))
        self.transcription_worker.moveToThread(self.transcription_thread)

        self.transcription_thread.started.connect(self.transcription_worker.run)
        self.transcription_worker.finished.connect(self._show_transcription)
        self.transcription_worker.failed.connect(self._show_transcription_error)

        # Thread shutdown & cleanup
        self.transcription_worker.finished.connect(self.transcription_thread.quit)
        self.transcription_worker.failed.connect(self.transcription_thread.quit)
        self.transcription_worker.finished.connect(self.transcription_worker.deleteLater)
        self.transcription_worker.failed.connect(self.transcription_worker.deleteLater)
        self.transcription_thread.finished.connect(self.transcription_thread.deleteLater)
        self.transcription_thread.finished.connect(self._on_stt_thread_finished)

        self.transcription_thread.start()

    def _on_stt_thread_finished(self):
        self.transcription_worker = None
        self.transcription_thread = None

    def _show_transcription(self, text):
        try:
            if text and text.strip():
                self.transcript_box.append(text)
                score_value = None
                if self.session_id:
                    transcript = self.transcript_box.toPlainText()
                    try:
                        db.update_live_interview(self.session_id, transcript=transcript)
                    except Exception:
                        pass

                    from app.engine.question_generator import _CATEGORY_SEQUENCE
                    idx = max(0, self.current_question_number - 1)
                    category = _CATEGORY_SEQUENCE[idx] if idx < len(_CATEGORY_SEQUENCE) else "technical"

                    try:
                        rubric = retrieve_rubric(self.job_title or "", category)
                        score = score_answer(
                            self.session_id,
                            f"q-{self.current_question_number}",
                            category,
                            text,
                            rubric,
                            question=self.current_question,
                        )
                        explanation = explain_score(
                            self.session_id, score.question_id, text, score.score,
                        )
                        db.save_competency_score(score)
                        db.save_explanation(explanation)
                        score_value = score.score
                        self.record_status.setText(
                            f"Answer scored: {score.score}/100 (AI certainty: {score.confidence:.0%}; "
                            f"your confidence: {self.confidence_slider.value()}/5). "
                            "Generating next question..."
                        )
                        self.record_status.setStyleSheet("color: #14B8A6; font-weight: 600;")
                    except Exception as eval_err:
                        self.record_status.setText("Answer recorded. Generating next question...")
                        self.record_status.setStyleSheet("color: #14B8A6; font-weight: 600;")

                    # Trigger dynamic next question generation
                    self._trigger_next_question_generation(text, score_value)
                else:
                    self.record_status.setText("Answer added to the transcript.")
                    self.record_status.setStyleSheet("color: #14B8A6; font-weight: 600;")
                    self.record_btn.setEnabled(True)
                    self.record_btn.setText("Start answer")
            else:
                self._show_transcription_error("No speech was detected. Please try answering again.")
        except Exception as exc:
            self._show_transcription_error(f"Processing error: {exc}")

    def _show_transcription_error(self, message):
        self.record_status.setText(f"Transcription status: {message}")
        self.record_status.setStyleSheet("color: #EF4444; font-weight: 600;")
        self.record_btn.setEnabled(True)
        self.record_btn.setText("Start answer")

    # --- Camera / candidate setup ---
    def set_candidate(self, candidate_id, candidate_name="Candidate"):
        self.candidate_id = candidate_id
        self.candidate_name = candidate_name
        saved_profile = db.get_candidate_profile(candidate_id)
        self.resume_profile = saved_profile["profile"] if saved_profile else {}

    def set_job(self, job_id: int, initial_questions: list | None = None):
        """
        Called when the candidate starts an interview.

        Args:
            job_id:            The selected job posting ID.
            initial_questions: Pre-generated Q1 list from CandidateDashboard.
                               If empty/None, falls back to heuristic questions_for_job().
        """
        job = next((j for j in db.get_active_job_postings() if j["id"] == job_id), None)
        if not job or not self.candidate_id:
            return

        self.job_id = job_id
        self.job_title = job["title"]
        self.job_description = job.get("description", "")
        self.interview_history = []
        self.current_question_number = 1
        self.waiting_for_approval = False
        self.session_id = uuid4().hex
        self.session_started_at = datetime.utcnow()
        self.session_finished = False

        # Determine first question
        if initial_questions:
            first_q = initial_questions[0]
        else:
            saved_profile = db.get_candidate_profile(self.candidate_id)
            self.resume_profile = saved_profile["profile"] if saved_profile else {}
            fallback_qs = questions_for_job(self.job_title, self.job_description, self.resume_profile)
            first_q = fallback_qs[0] if fallback_qs else "Tell me about yourself."

        self.current_question = first_q
        self._display_current_question()

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
            first_q,
            0,
        )
        self._record_integrity_flags(run_checks(self.session_id))
        self.live_timer.start(1000)

    def _display_current_question(self):
        from app.engine.question_generator import MAX_QUESTIONS, _CATEGORY_SEQUENCE
        self.question_text.setText(self.current_question)
        self.progress_label.setText(
            f"Question {self.current_question_number} of {MAX_QUESTIONS}"
        )
        # Show category tag
        idx = self.current_question_number - 1
        if 0 <= idx < len(_CATEGORY_SEQUENCE):
            category = _CATEGORY_SEQUENCE[idx].replace("_", " ").title()
            self.category_tag.setText(category)
            self.category_tag.setVisible(True)
        self.waiting_lbl.setVisible(False)
        self.record_btn.setEnabled(True)

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

    # --- Dynamic question generation ---

    def _trigger_next_question_generation(self, answer_text: str, score_value: float | None):
        """After an answer is scored, generate the next question in background and save as pending."""
        from app.engine.question_generator import MAX_QUESTIONS, _CATEGORY_SEQUENCE
        if self.current_question_number >= MAX_QUESTIONS:
            self.question_text.setText(
                "✅ Interview complete! Thank you for your answers. "
                "The interviewer will review your responses shortly."
            )
            self.category_tag.setVisible(False)
            self.record_btn.setEnabled(False)
            self._finalize_session()
            return

        # Record current Q+A in history
        idx = self.current_question_number - 1
        category = _CATEGORY_SEQUENCE[idx] if 0 <= idx < len(_CATEGORY_SEQUENCE) else "general"
        self.interview_history.append({
            "question": self.current_question,
            "answer": answer_text,
            "score": score_value,
            "category": category,
            "candidate_confidence": self.confidence_slider.value(),
        })

        # Persist history to DB for interviewer's regenerate flow
        if self.session_id:
            db.update_live_interview(
                self.session_id,
                interview_context=json.dumps(self.interview_history),
            )

        # Show waiting state
        self.waiting_lbl.setVisible(True)
        self.record_btn.setEnabled(False)
        self.waiting_for_approval = True

        # Spawn background worker
        self._nq_thread = QThread()
        self._nq_worker = NextQuestionWorker(
            self.job_title, self.job_description,
            self.resume_profile, self.interview_history,
        )
        self._nq_worker.moveToThread(self._nq_thread)
        self._nq_thread.started.connect(self._nq_worker.run)
        self._nq_worker.finished.connect(self._on_next_question_generated)
        self._nq_worker.failed.connect(self._on_next_question_failed)
        self._nq_worker.finished.connect(self._nq_thread.quit)
        self._nq_worker.failed.connect(self._nq_thread.quit)
        self._nq_thread.finished.connect(self._nq_worker.deleteLater)
        self._nq_thread.finished.connect(self._nq_thread.deleteLater)
        self._nq_thread.finished.connect(self._on_nq_thread_finished)
        self._nq_thread.start()

    def _on_next_question_generated(self, question: str):
        if self.session_id:
            db.save_pending_question(self.session_id, question)
        self.record_status.setText(
            "✅ Answer recorded. Waiting for interviewer to approve the next question..."
        )
        self.record_status.setStyleSheet("color: #F59E0B; font-weight: 600;")

    def _on_next_question_failed(self, error: str):
        # Even on failure, unblock the candidate with a fallback question
        self.waiting_for_approval = False
        self.waiting_lbl.setVisible(False)
        self.record_btn.setEnabled(True)
        self.record_status.setText(f"Question generation status: {error}. Using fallback.")

    def _on_nq_thread_finished(self):
        self._nq_worker = None
        self._nq_thread = None

    # --- Sync live state (polls DB every 1s) ---
    def _sync_live_state(self):
        if not self.session_id:
            return
        live_session = db.get_live_interview(self.session_id)
        if not live_session:
            return

        # Check if interviewer approved the pending question
        if self.waiting_for_approval and live_session.get("pending_status") == "approved":
            approved_q = live_session.get("question", "")
            if approved_q:
                self.waiting_for_approval = False
                self.current_question_number += 1
                self.current_question = approved_q
                db.update_live_interview(self.session_id, pending_status="none")
                self.transcript_box.clear()
                self._display_current_question()
                self.record_status.setText("New question from interviewer — ready to answer.")
                self.record_status.setStyleSheet("color: #0F766E; font-weight: 600;")
                return

        # Ad-hoc question sent directly by interviewer (bypasses approval flow)
        if (not self.waiting_for_approval
                and live_session.get("question") != self.current_question):
            self.current_question = live_session["question"]
            self.question_text.setText(self.current_question)
            self.transcript_box.clear()
            self.record_status.setText("Interviewer sent a follow-up question.")
            self.record_status.setStyleSheet("color: #5B5FEF; font-weight: 600;")

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
        face_count, face_verified, face_confidence, face_message = face_match_confidence(
            self.candidate_id, frame
        )
        if self.session_id and self.frame_count % 6 == 0:
            self._record_integrity_flags(
                self.face_monitor.observe(self.session_id, self.candidate_id, frame)
            )
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
        if self.session_id and self.frame_count % 30 == 0:
            ok, encoded = cv2.imencode(
                ".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                [int(cv2.IMWRITE_JPEG_QUALITY), 65],
            )
            if ok:
                try:
                    db.upload_live_frame(self.session_id, encoded.tobytes())
                except Exception:
                    pass
        if self.live_frame_path:
            frame_path = self.live_frame_path.with_name(
                f".{self.live_frame_path.stem}-{uuid4().hex}.tmp.jpg"
            )
            try:
                if cv2.imwrite(str(frame_path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)):
                    os.replace(str(frame_path), str(self.live_frame_path))
            except PermissionError:
                # The interviewer may have the previous frame open on Windows.
                pass
            finally:
                try:
                    frame_path.unlink(missing_ok=True)
                except OSError:
                    pass
        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

    def cleanup(self):
        self.live_timer.stop()
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        if getattr(self, "transcription_thread", None) is not None and self.transcription_thread.isRunning():
            self.transcription_thread.quit()
            self.transcription_thread.wait()
        if getattr(self, "_nq_thread", None) is not None and self._nq_thread.isRunning():
            self._nq_thread.quit()
            self._nq_thread.wait()
        if self.timer.isActive():
            self.timer.stop()
        if self.capture:
            try:
                self.capture.release()
            except Exception:
                pass
            self.capture = None
        self._finalize_session()
        if self.live_frame_path and self.live_frame_path.exists():
            try:
                self.live_frame_path.unlink()
            except Exception:
                pass

    def _finalize_session(self):
        if not self.session_id or self.session_finished:
            return
        try:
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
            self.session_finished = True
        except Exception:
            pass
