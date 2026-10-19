"""
Interviewer Interview Monitor — live session view with AI question approval.

The interviewer can:
  - Watch any active candidate's transcript and camera feed in real time
  - See AI-generated next questions that are PENDING their approval
  - Approve the question as-is, edit it before sending, or skip to regenerate
  - Send ad-hoc follow-up questions at any time
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core import db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background worker: regenerate a question when interviewer clicks Skip
# ---------------------------------------------------------------------------

class RegenerateWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, session_id: str, job_title: str, job_description: str,
                 resume_profile: dict, history: list):
        super().__init__()
        self.session_id = session_id
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


# ---------------------------------------------------------------------------
# Pending question approval panel
# ---------------------------------------------------------------------------

class PendingQuestionPanel(QWidget):
    """
    Shown when the AI has generated the next question and is waiting for
    the interviewer to approve / edit / skip.
    """

    approved = Signal(str)    # question text to approve
    skipped = Signal()        # request a new question

    def __init__(self):
        super().__init__()
        self.setObjectName("PendingQuestionPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        badge = QLabel("🤖  AI Suggested Question — Awaiting Your Approval")
        badge.setStyleSheet("font-weight: 700; color: #92400E; font-size: 13px;")
        header_row.addWidget(badge)
        header_row.addStretch()
        layout.addLayout(header_row)

        self.question_edit = QLineEdit()
        self.question_edit.setPlaceholderText("AI question will appear here...")
        self.question_edit.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(self.question_edit)

        hint = QLabel("You can edit the question above before approving.")
        hint.setObjectName("WaitingLabel")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self.approve_btn = QPushButton("✅  Approve & Send to Candidate")
        self.approve_btn.setObjectName("ApproveButton")
        self.approve_btn.clicked.connect(self._on_approve)

        self.skip_btn = QPushButton("⏭  Skip — Generate Another")
        self.skip_btn.setObjectName("SkipButton")
        self.skip_btn.clicked.connect(self.skipped.emit)

        btn_row.addWidget(self.approve_btn)
        btn_row.addWidget(self.skip_btn)
        layout.addLayout(btn_row)

    def set_question(self, text: str):
        self.question_edit.setText(text)

    def _on_approve(self):
        self.approved.emit(self.question_edit.text().strip())


# ---------------------------------------------------------------------------
# Main interviewer interview page
# ---------------------------------------------------------------------------

class InterviewerInterviewPage(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_session_id = None
        self.latest_sessions = []
        self._regen_thread = None
        self._regen_worker = None
        self._frame_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="frame-download"
        )
        self._frame_future = None
        self._frame_session_id = None
        self._session_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="session-refresh"
        )
        self._session_future = None

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        title = QLabel("Live Interview Monitor")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Watch, guide, and approve AI questions for the candidate")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(20)

        # --- Left: active candidate list ---
        sessions_panel = QWidget()
        sessions_panel.setObjectName("Card")
        sessions_layout = QVBoxLayout(sessions_panel)
        sessions_layout.setContentsMargins(16, 16, 16, 16)
        sessions_layout.addWidget(QLabel("Active Candidates"))
        self.sessions_list = QListWidget()
        self.sessions_list.currentRowChanged.connect(self._select_session)
        sessions_layout.addWidget(self.sessions_list)
        body.addWidget(sessions_panel, stretch=1)

        # --- Right: monitor panel ---
        monitor_panel = QWidget()
        monitor_panel.setObjectName("Card")
        monitor_panel.setMinimumWidth(560)
        monitor_layout = QVBoxLayout(monitor_panel)
        monitor_layout.setContentsMargins(20, 20, 20, 20)
        monitor_layout.setSpacing(12)

        self.candidate_label = QLabel("No active candidate selected")
        self.candidate_label.setObjectName("PageSubtitle")

        q_row = QHBoxLayout()
        self.question_label = QLabel("Current question will appear here.")
        self.question_label.setWordWrap(True)
        self.question_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #1B1F2A;")
        self.q_count_lbl = QLabel("")
        self.q_count_lbl.setObjectName("PageSubtitle")
        self.q_count_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        q_row.addWidget(self.question_label, stretch=1)
        q_row.addWidget(self.q_count_lbl)

        monitor_layout.addWidget(self.candidate_label)
        monitor_layout.addLayout(q_row)

        # Camera feed
        self.video_label = QLabel("Candidate camera feed will appear here.")
        self.video_label.setMinimumHeight(200)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(
            "background-color: #111827; color: #9CA3AF; border-radius: 8px;"
        )
        monitor_layout.addWidget(self.video_label)

        integrity_group = QGroupBox("Integrity Flags")
        integrity_layout = QVBoxLayout(integrity_group)
        self.integrity_flags_label = QLabel("No integrity flags recorded.")
        self.integrity_flags_label.setWordWrap(True)
        self.integrity_flags_label.setStyleSheet("color: #0F766E; font-size: 12px;")
        integrity_layout.addWidget(self.integrity_flags_label)
        monitor_layout.addWidget(integrity_group)

        # Live transcript
        transcript_title = QLabel("Live Candidate Transcript")
        transcript_title.setObjectName("PageSubtitle")
        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        self.transcript_box.setPlaceholderText("Transcribed answers appear here in real time.")
        self.transcript_box.setMaximumHeight(140)
        monitor_layout.addWidget(transcript_title)
        monitor_layout.addWidget(self.transcript_box)

        # --- Pending question approval panel ---
        self.pending_panel = PendingQuestionPanel()
        self.pending_panel.setVisible(False)
        self.pending_panel.approved.connect(self._approve_question)
        self.pending_panel.skipped.connect(self._regenerate_question)
        monitor_layout.addWidget(self.pending_panel)

        self.regen_status_lbl = QLabel("")
        self.regen_status_lbl.setObjectName("WaitingLabel")
        self.regen_status_lbl.setVisible(False)
        monitor_layout.addWidget(self.regen_status_lbl)

        # Ad-hoc question input
        adhoc_group = QGroupBox("Send Ad-hoc Follow-up")
        adhoc_layout = QHBoxLayout(adhoc_group)
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Type a follow-up question and press Send...")
        self.question_input.returnPressed.connect(self.send_question)
        adhoc_layout.addWidget(self.question_input, stretch=1)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.clicked.connect(self.send_question)
        adhoc_layout.addWidget(self.send_button)
        monitor_layout.addWidget(adhoc_group)

        self.status_label = QLabel("Waiting for a candidate to start an interview.")
        self.status_label.setObjectName("PageSubtitle")
        monitor_layout.addWidget(self.status_label)

        monitor_scroll = QScrollArea()
        monitor_scroll.setWidgetResizable(True)
        monitor_scroll.setFrameShape(QScrollArea.NoFrame)
        monitor_scroll.setWidget(monitor_panel)
        body.addWidget(monitor_scroll, stretch=3)
        root.addLayout(body, stretch=1)

        # Refresh timer — 1 s
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_sessions)
        self.refresh_timer.start(1500)
        self.refresh_sessions()

    # ------------------------------------------------------------------
    # Session list
    # ------------------------------------------------------------------

    def refresh_sessions(self):
        if self._session_future is None:
            self._session_future = self._session_executor.submit(
                self._load_sessions
            )
            QTimer.singleShot(50, self._apply_session_refresh)
            return
        if not self._session_future.done():
            return
        self._apply_session_refresh()

    @staticmethod
    def _load_sessions():
        live_sessions = db.get_live_interviews()
        live_candidate_ids = {s["candidate_id"] for s in live_sessions}
        sessions = list(live_sessions)
        for candidate in db.get_candidate_accounts():
            if candidate["candidate_id"] not in live_candidate_ids:
                sessions.append({
                    "session_id": None,
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate["full_name"],
                    "question": "Waiting for the candidate to start.",
                    "question_index": 0,
                    "question_count": 0,
                    "transcript": "",
                    "status": "ready",
                    "pending_question": "",
                    "pending_status": "none",
                })
        return sessions

    def _apply_session_refresh(self):
        if self._session_future is None or not self._session_future.done():
            if self._session_future is not None:
                QTimer.singleShot(50, self._apply_session_refresh)
            return
        future = self._session_future
        self._session_future = None
        try:
            sessions = future.result()
        except Exception as exc:
            self.status_label.setText(f"Live monitor unavailable: {exc}")
            return
        selected_id = self.selected_session_id
        self.latest_sessions = sessions
        self.sessions_list.blockSignals(True)
        self.sessions_list.clear()
        selected_row = -1
        for row, session in enumerate(sessions):
            state = "🟢 LIVE" if session["status"] == "live" else "⚪ READY"
            pending = " ⏳" if session.get("pending_status") == "pending" else ""
            self.sessions_list.addItem(
                f"{session['candidate_name']}  {state}{pending}\n"
                f"Q {session['question_index'] + 1}"
            )
            key = session["session_id"] or session["candidate_id"]
            if key == selected_id:
                selected_row = row
        self.sessions_list.blockSignals(False)

        if selected_row >= 0:
            self.sessions_list.setCurrentRow(selected_row)
            self._show_session(sessions[selected_row])
        elif sessions:
            self.sessions_list.setCurrentRow(0)
        else:
            self.selected_session_id = None
            self._clear_monitor()

    def _select_session(self, row: int):
        if row < 0 or row >= len(self.latest_sessions):
            return
        session = self.latest_sessions[row]
        self.selected_session_id = session["session_id"] or session["candidate_id"]
        self._show_session(session)

    def _show_session(self, session: dict):
        self.candidate_label.setText(f"Candidate: {session['candidate_name']}")
        self.question_label.setText(session["question"])
        self.transcript_box.setPlainText(session.get("transcript", ""))
        is_live = session["status"] == "live"
        self.send_button.setEnabled(is_live)

        q_count = session.get("question_count", 0)
        from app.engine.question_generator import MAX_QUESTIONS
        self.q_count_lbl.setText(f"Q {q_count} / {MAX_QUESTIONS}" if is_live else "")

        # Request the frame outside the Qt UI thread.
        frame_path = session.get("session_id") if is_live else None
        self._request_frame(frame_path)

        self._refresh_integrity_flags(session.get("session_id") if is_live else None)

        # Pending question panel
        pending_q = session.get("pending_question", "")
        pending_status = session.get("pending_status", "none")
        if is_live and pending_status == "pending" and pending_q:
            self.pending_panel.set_question(pending_q)
            self.pending_panel.setVisible(True)
        else:
            self.pending_panel.setVisible(False)

        self.status_label.setText(
            "Live session. Use the panel above to approve the AI question."
            if is_live else "Candidate is registered and ready."
        )

    def _request_frame(self, session_id):
        if not session_id:
            self._frame_session_id = None
            self._frame_future = None
            return
        if self._frame_future is not None and not self._frame_future.done():
            return
        self._frame_session_id = session_id
        self._frame_future = self._frame_executor.submit(
            db.download_live_frame, session_id
        )
        QTimer.singleShot(50, self._apply_frame_result)

    def _apply_frame_result(self):
        future = self._frame_future
        if future is None or not future.done():
            if future is not None:
                QTimer.singleShot(50, self._apply_frame_result)
            return
        self._frame_future = None
        try:
            frame_bytes = future.result()
        except Exception as exc:
            self.status_label.setText(f"Camera feed unavailable: {exc}")
            return
        if not frame_bytes or self._frame_session_id != self.selected_session_id:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(frame_bytes, "JPG"):
            self.video_label.setPixmap(
                pixmap.scaled(
                    self.video_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def _clear_monitor(self):
        self.candidate_label.setText("No active candidate selected")
        self.question_label.setText("A candidate's current question will appear here.")
        self.transcript_box.clear()
        self._refresh_integrity_flags(None)
        self.status_label.setText("Waiting for a candidate to start an interview.")
        self.pending_panel.setVisible(False)

    def _refresh_integrity_flags(self, session_id):
        if not session_id:
            self.integrity_flags_label.setText("Select a live candidate to view integrity flags.")
            self.integrity_flags_label.setStyleSheet("color: #6B7280; font-size: 12px;")
            return

        flags = db.get_session_flags(session_id)
        if not flags:
            self.integrity_flags_label.setText("No integrity flags recorded.")
            self.integrity_flags_label.setStyleSheet("color: #0F766E; font-size: 12px;")
            return

        lines = [
            f"[{flag.get('severity', 'medium').upper()}] "
            f"{flag.get('detail', 'Unknown signal')} "
            f"(confidence {float(flag.get('confidence', 0.0)):.0%})"
            for flag in flags
        ]
        self.integrity_flags_label.setText("\n".join(lines))
        self.integrity_flags_label.setStyleSheet("color: #B91C1C; font-size: 12px; font-weight: 600;")

    # ------------------------------------------------------------------
    # Approve / Skip / Regenerate
    # ------------------------------------------------------------------

    def _approve_question(self, question: str):
        if not self.selected_session_id:
            return
        # Find full session to get session_id (not candidate_id used as key)
        session = next(
            (s for s in self.latest_sessions
             if (s["session_id"] or s["candidate_id"]) == self.selected_session_id),
            None,
        )
        if not session or not session.get("session_id"):
            return
        db.approve_pending_question(session["session_id"], question)
        self.pending_panel.setVisible(False)
        self.status_label.setText("✅ Question approved and sent to the candidate.")

    def _regenerate_question(self):
        session = next(
            (s for s in self.latest_sessions
             if (s["session_id"] or s["candidate_id"]) == self.selected_session_id),
            None,
        )
        if not session or not session.get("session_id"):
            return

        self.regen_status_lbl.setText("⏳ Generating a new question...")
        self.regen_status_lbl.setVisible(True)
        self.pending_panel.approve_btn.setEnabled(False)
        self.pending_panel.skip_btn.setEnabled(False)

        # Build history from context stored in DB
        live = db.get_live_interview(session["session_id"])
        history = []
        if live and live.get("interview_context"):
            try:
                history = json.loads(live["interview_context"])
            except (json.JSONDecodeError, TypeError):
                history = []

        # Fetch resume + job for regen
        profile_row = db.get_candidate_profile(session.get("candidate_id", ""))
        resume_profile = profile_row["profile"] if profile_row else {}
        sessions_rows = db.get_all_sessions()
        job_title, job_description = "", ""
        for s in sessions_rows:
            if s["session_id"] == session["session_id"]:
                job_title = s.get("job_title", "")
                break
        jobs = db.get_active_job_postings()
        for j in jobs:
            if j["title"] == job_title:
                job_description = j.get("description", "")
                break

        self._regen_thread = QThread(self)
        self._regen_worker = RegenerateWorker(
            session["session_id"], job_title, job_description, resume_profile, history
        )
        self._regen_worker.moveToThread(self._regen_thread)
        self._regen_thread.started.connect(self._regen_worker.run)
        self._regen_worker.finished.connect(self._on_regen_done)
        self._regen_worker.failed.connect(self._on_regen_failed)
        self._regen_worker.finished.connect(self._cleanup_regen)
        self._regen_worker.failed.connect(self._cleanup_regen)
        self._regen_thread.start()

    def _on_regen_done(self, question: str):
        session = next(
            (s for s in self.latest_sessions
             if (s["session_id"] or s["candidate_id"]) == self.selected_session_id),
            None,
        )
        if session and session.get("session_id"):
            db.save_pending_question(session["session_id"], question)
        self.pending_panel.set_question(question)
        self.pending_panel.approve_btn.setEnabled(True)
        self.pending_panel.skip_btn.setEnabled(True)
        self.regen_status_lbl.setVisible(False)
        self.status_label.setText("New question generated. Review and approve.")

    def _on_regen_failed(self, error: str):
        self.regen_status_lbl.setText(f"Regeneration failed: {error}")
        self.pending_panel.approve_btn.setEnabled(True)
        self.pending_panel.skip_btn.setEnabled(True)

    def _cleanup_regen(self):
        if self._regen_thread:
            self._regen_thread.quit()
            self._regen_thread.wait()
            if self._regen_worker:
                self._regen_worker.deleteLater()
            self._regen_thread.deleteLater()
            self._regen_worker = None
            self._regen_thread = None

    # ------------------------------------------------------------------
    # Ad-hoc follow-up
    # ------------------------------------------------------------------

    def send_question(self):
        question = self.question_input.text().strip()
        session = next(
            (s for s in self.latest_sessions
             if (s["session_id"] or s["candidate_id"]) == self.selected_session_id),
            None,
        )
        if not session or session["status"] != "live" or not question or not session.get("session_id"):
            return
        # Ad-hoc questions bypass the approval flow — sent directly
        db.update_live_interview(session["session_id"], question=question, transcript="")
        self.question_input.clear()
        self.question_label.setText(question)
        self.status_label.setText("Ad-hoc question sent to the candidate.")

    def cleanup(self):
        self.refresh_timer.stop()
        self._frame_executor.shutdown(wait=False, cancel_futures=True)
        self._session_executor.shutdown(wait=False, cancel_futures=True)
        self._cleanup_regen()
