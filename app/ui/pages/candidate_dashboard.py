"""
Enhanced Candidate Dashboard.

Shows:
  - Personalised welcome header with candidate name
  - 3-step progress stepper: Resume → Face Check → Interview
  - Status cards for resume, camera, and environment
  - Job selection with description preview
  - Large Start Interview CTA (enabled only when all checks pass)
  - Launches AI question generation in background before transitioning
"""
import cv2
from PySide6.QtCore import Qt, QTimer, QThread, QObject, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.candidate.face_recognition import enroll_face, has_enrolled_face, verify_single_face
from app.candidate.resume import extract_resume, match_resume_to_job, profile_json
from app.core import db
from app.utils.port_scanner import get_unauthorized_devices


# ---------------------------------------------------------------------------
# Background worker: AI question generation
# ---------------------------------------------------------------------------

class QuestionGeneratorWorker(QObject):
    """Generates 8 AI questions in a background thread."""

    finished = Signal(list)   # list[str]
    failed = Signal(str)

    def __init__(self, job_title: str, job_description: str, resume_profile: dict):
        super().__init__()
        self.job_title = job_title
        self.job_description = job_description
        self.resume_profile = resume_profile

    def run(self):
        try:
            from app.engine.question_generator import generate_next_question, MAX_QUESTIONS
            questions = []
            history = []
            # Generate all 8 initial questions upfront (first one shown immediately;
            # subsequent ones are generated dynamically after each answer in interview_page.py,
            # but we pre-generate Q1 here so there is no delay at session start).
            q1 = generate_next_question(
                self.job_title, self.job_description, self.resume_profile, history
            )
            questions.append(q1)
            self.finished.emit(questions)
        except Exception as exc:  # noqa: BLE001
            # Fallback: use heuristic questions
            try:
                from app.core.question_bank import questions_for_job
                qs = questions_for_job(self.job_title, self.job_description, self.resume_profile)
                self.finished.emit(qs[:8])
            except Exception as inner:  # noqa: BLE001
                self.failed.emit(str(inner))


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

class CandidateDashboard(QWidget):
    """Guided pre-interview dashboard for the candidate."""

    # Emitted when questions are ready and user can proceed to interview
    interview_ready = Signal(int, list)  # (job_id, questions)

    def __init__(self, candidate_id=None):
        super().__init__()
        self.candidate_id = candidate_id
        self.candidate_name = "Candidate"
        self.capture = None
        self.latest_frame = None
        self.environment_clear = False
        self.face_clear = False
        self.face_enrolled = False
        self.selected_job_id = None
        self.selected_job = None
        self.resume_profile = None

        self._gen_thread = None
        self._gen_worker = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_camera)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(18)

        # --- Welcome header ---
        self.welcome_lbl = QLabel("Welcome")
        self.welcome_lbl.setObjectName("PageTitle")
        self.role_lbl = QLabel("Complete the checks below, then start your interview.")
        self.role_lbl.setObjectName("PageSubtitle")
        root.addWidget(self.welcome_lbl)
        root.addWidget(self.role_lbl)

        # --- Progress stepper ---
        stepper_row = QHBoxLayout()
        stepper_row.setSpacing(8)
        self.step1_lbl = QLabel("1  Resume")
        self.step2_lbl = QLabel("2  Identity check")
        self.step3_lbl = QLabel("3  Begin interview")

        arrow1 = QLabel("──")
        arrow1.setStyleSheet("color: #D1D5DB;")
        arrow2 = QLabel("──")
        arrow2.setStyleSheet("color: #D1D5DB;")

        stepper_row.addStretch()
        stepper_row.addWidget(self.step1_lbl)
        stepper_row.addWidget(arrow1)
        stepper_row.addWidget(self.step2_lbl)
        stepper_row.addWidget(arrow2)
        stepper_row.addWidget(self.step3_lbl)
        stepper_row.addStretch()
        root.addLayout(stepper_row)
        self._update_stepper()

        # --- Middle body ---
        body = QHBoxLayout()
        body.setSpacing(16)

        # Left: resume + job selection
        left_col = QVBoxLayout()
        left_col.setSpacing(14)

        # Resume card
        resume_group = QGroupBox("Resume")
        resume_layout = QVBoxLayout(resume_group)
        resume_layout.setSpacing(10)

        self.resume_status_lbl = QLabel("No resume uploaded yet.")
        self.resume_status_lbl.setObjectName("StatusPending")
        self.resume_status_lbl.setWordWrap(True)
        resume_layout.addWidget(self.resume_status_lbl)

        self.skills_lbl = QLabel("")
        self.skills_lbl.setWordWrap(True)
        self.skills_lbl.setStyleSheet("color: #374151; font-size: 12px;")
        resume_layout.addWidget(self.skills_lbl)

        self.match_lbl = QLabel("")
        self.match_lbl.setStyleSheet("color: #0F766E; font-weight: 600; font-size: 12px;")
        resume_layout.addWidget(self.match_lbl)

        upload_btn = QPushButton("Upload Resume")
        upload_btn.setObjectName("SecondaryButton")
        upload_btn.clicked.connect(self.upload_resume)
        resume_layout.addWidget(upload_btn)

        left_col.addWidget(resume_group)

        # Job selection card
        jobs_group = QGroupBox("Choose an interview")
        jobs_layout = QVBoxLayout(jobs_group)
        jobs_layout.setSpacing(8)

        self.jobs_list = QListWidget()
        self.jobs_list.setMinimumHeight(120)
        self.jobs_list.itemSelectionChanged.connect(self._on_job_selected)
        jobs_layout.addWidget(self.jobs_list)

        self.job_desc_lbl = QLabel("")
        self.job_desc_lbl.setWordWrap(True)
        self.job_desc_lbl.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.job_desc_lbl.setMaximumHeight(60)
        jobs_layout.addWidget(self.job_desc_lbl)

        refresh_btn = QPushButton("Refresh jobs")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.clicked.connect(self.load_jobs)
        jobs_layout.addWidget(refresh_btn)

        left_col.addWidget(jobs_group)
        left_col.addStretch()
        body.addLayout(left_col, stretch=1)

        # Right: camera + environment
        cam_group = QGroupBox("Camera and environment check")
        cam_layout = QVBoxLayout(cam_group)
        cam_layout.setSpacing(10)

        self.camera_preview = QLabel("Click 'Start Camera' to verify your face")
        self.camera_preview.setAlignment(Qt.AlignCenter)
        self.camera_preview.setMinimumSize(380, 220)
        self.camera_preview.setStyleSheet(
            "background-color: #111827; color: #9CA3AF; border-radius: 8px; font-size: 12px;"
        )
        cam_layout.addWidget(self.camera_preview)

        # Status badges row
        badges_row = QHBoxLayout()
        self.env_badge = QLabel("Environment: Checking...")
        self.env_badge.setObjectName("StatusPending")
        self.face_badge = QLabel("Identity: Not checked")
        self.face_badge.setObjectName("StatusPending")
        badges_row.addWidget(self.env_badge)
        badges_row.addStretch()
        badges_row.addWidget(self.face_badge)
        cam_layout.addLayout(badges_row)

        cam_btn_row = QHBoxLayout()
        self.camera_button = QPushButton("Start Camera")
        self.camera_button.setObjectName("SecondaryButton")
        self.camera_button.clicked.connect(self._toggle_camera)

        self.env_button = QPushButton("Re-scan Environment")
        self.env_button.setObjectName("SecondaryButton")
        self.env_button.clicked.connect(self.check_environment)

        cam_btn_row.addWidget(self.camera_button)
        cam_btn_row.addWidget(self.env_button)
        cam_layout.addLayout(cam_btn_row)

        body.addWidget(cam_group, stretch=1)
        root.addLayout(body, stretch=1)

        # --- Start Interview button ---
        start_row = QHBoxLayout()
        self.start_button = QPushButton("Start interview")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setMinimumHeight(48)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._launch_interview)

        self.start_status_lbl = QLabel("")
        self.start_status_lbl.setObjectName("PageSubtitle")

        start_row.addStretch()
        start_row.addWidget(self.start_status_lbl)
        start_row.addWidget(self.start_button)
        root.addLayout(start_row)

        # Initial checks
        self.check_environment()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_candidate(self, candidate_id: str, candidate_name: str = "Candidate"):
        self.candidate_id = candidate_id
        self.candidate_name = candidate_name
        self.welcome_lbl.setText(f"Welcome back, {candidate_name}")
        self.load_jobs()
        self.face_enrolled = has_enrolled_face(candidate_id)
        saved_profile = db.get_candidate_profile(candidate_id)
        if saved_profile:
            self.resume_profile = saved_profile["profile"]
            self._show_resume_loaded(saved_profile["resume_path"])
        self._update_start_state()

    # ------------------------------------------------------------------
    # Resume
    # ------------------------------------------------------------------

    def upload_resume(self):
        if not self.candidate_id:
            QMessageBox.warning(self, "Not logged in", "Please log in before uploading your resume.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Resume", "", "Resume files (*.pdf *.docx *.txt)"
        )
        if not path:
            return
        try:
            profile = extract_resume(path)
            db.save_candidate_profile(self.candidate_id, path, profile_json(profile))
            self.resume_profile = profile
            self._show_resume_loaded(path)
            self._update_match_status()
            self._update_start_state()
        except (OSError, ValueError, ImportError) as error:
            QMessageBox.warning(self, "Resume could not be read", str(error))

    def _show_resume_loaded(self, path: str):
        fname = path.split("/")[-1].split("\\")[-1]
        self.resume_status_lbl.setText(f"Resume uploaded: {fname}")
        self.resume_status_lbl.setObjectName("StatusPass")
        self.resume_status_lbl.style().unpolish(self.resume_status_lbl)
        self.resume_status_lbl.style().polish(self.resume_status_lbl)
        skills = self.resume_profile.get("skills", []) if self.resume_profile else []
        self.skills_lbl.setText(f"Skills: {', '.join(skills[:6]) or 'None detected'}")
        self._update_stepper()

    def _update_match_status(self):
        if not self.resume_profile or not self.selected_job:
            self.match_lbl.setText("")
            return
        try:
            match = match_resume_to_job(
                self.resume_profile,
                self.selected_job["title"],
                self.selected_job["description"],
            )
            self.match_lbl.setText(
                f"Role match: {match['score']}%  |  "
                f"Missing: {', '.join(match['missing_skills'][:3]) or 'None'}"
            )
        except Exception:  # noqa: BLE001
            self.match_lbl.setText("")

    # ------------------------------------------------------------------
    # Job selection
    # ------------------------------------------------------------------

    def load_jobs(self):
        self.jobs_list.clear()
        jobs = db.get_active_job_postings()
        for job in jobs:
            self.jobs_list.addItem(f"{job['title']}")
            self.jobs_list.item(self.jobs_list.count() - 1).setData(Qt.UserRole, job)
        if not jobs:
            self.jobs_list.addItem("No active job postings available yet.")
            self.jobs_list.item(0).setFlags(Qt.NoItemFlags)
        self._update_start_state()

    def _on_job_selected(self):
        item = self.jobs_list.currentItem()
        self.selected_job = item.data(Qt.UserRole) if item else None
        self.selected_job_id = self.selected_job["id"] if self.selected_job else None
        if self.selected_job:
            desc = self.selected_job.get("description", "")
            self.job_desc_lbl.setText(desc[:160] + "..." if len(desc) > 160 else desc)
            self.role_lbl.setText(f"Interviewing for: {self.selected_job['title']}")
        else:
            self.job_desc_lbl.setText("")
        self._update_match_status()
        self._update_start_state()

    # ------------------------------------------------------------------
    # Environment & Camera
    # ------------------------------------------------------------------

    def check_environment(self):
        self.env_badge.setText("Environment: Checking...")
        self.env_badge.setObjectName("StatusPending")
        self.env_badge.style().unpolish(self.env_badge)
        self.env_badge.style().polish(self.env_badge)
        QApplication.processEvents()
        devices = get_unauthorized_devices()
        self.environment_clear = not devices
        if devices:
            self.env_badge.setText("Environment: Devices detected")
            self.env_badge.setObjectName("StatusFail")
        else:
            self.env_badge.setText("Environment: Clear")
            self.env_badge.setObjectName("StatusPass")
        self.env_badge.style().unpolish(self.env_badge)
        self.env_badge.style().polish(self.env_badge)
        self._update_start_state()

    def _toggle_camera(self):
        if self.capture is not None:
            self._stop_camera()
            return
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            self.face_badge.setText("Identity: Camera unavailable")
            self.face_badge.setObjectName("StatusFail")
            self.face_badge.style().unpolish(self.face_badge)
            self.face_badge.style().polish(self.face_badge)
            return
        self.camera_button.setText("Stop Camera")
        self.timer.start(33)

    def _stop_camera(self):
        self.timer.stop()
        self.capture.release()
        self.capture = None
        self.latest_frame = None
        self.face_clear = False
        self.camera_button.setText("Start Camera")
        self.face_badge.setText("Identity: Camera stopped")
        self.face_badge.setObjectName("StatusPending")
        self.face_badge.style().unpolish(self.face_badge)
        self.face_badge.style().polish(self.face_badge)
        self.camera_preview.setText("Click 'Start Camera' to verify your face")
        self._update_start_state()

    def _update_camera(self):
        ok, frame = self.capture.read()
        if not ok:
            return
        self.latest_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.camera_preview.setPixmap(
            QPixmap.fromImage(img).scaled(
                self.camera_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        self._update_face_state()

    def _update_face_state(self):
        if self.latest_frame is None:
            return
        verified, message = verify_single_face(self.latest_frame)
        if verified:
            was_enrolled = self.face_enrolled
            if not was_enrolled:
                if enroll_face(self.candidate_id, self.latest_frame):
                    self.face_enrolled = True
                else:
                    self.face_clear = False
                    return
            self.face_clear = True
            label = "Identity enrolled and verified" if not was_enrolled else "Identity: Verified"
            self.face_badge.setText(label if was_enrolled else "Identity: Enrolled")
            self.face_badge.setObjectName("StatusPass")
        else:
            self.face_clear = False
            self.face_badge.setText(f"Identity: {message}")
            self.face_badge.setObjectName("StatusPending")
        self.face_badge.style().unpolish(self.face_badge)
        self.face_badge.style().polish(self.face_badge)
        self._update_stepper()
        self._update_start_state()

    # ------------------------------------------------------------------
    # Stepper
    # ------------------------------------------------------------------

    def _update_stepper(self):
        resume_done = self.resume_profile is not None
        face_done = self.face_clear

        def _style(lbl: QLabel, name: str):
            lbl.setObjectName(name)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

        if resume_done:
            _style(self.step1_lbl, "StepperDone")
        elif not resume_done and not face_done:
            _style(self.step1_lbl, "StepperActive")
        else:
            _style(self.step1_lbl, "StepperDone")

        if face_done:
            _style(self.step2_lbl, "StepperDone")
        elif resume_done:
            _style(self.step2_lbl, "StepperActive")
        else:
            _style(self.step2_lbl, "StepperPending")

        if resume_done and face_done and self.selected_job_id:
            _style(self.step3_lbl, "StepperActive")
        else:
            _style(self.step3_lbl, "StepperPending")

    # ------------------------------------------------------------------
    # Start interview
    # ------------------------------------------------------------------

    def _update_start_state(self):
        ready = (
            self.environment_clear
            and self.face_clear
            and self.selected_job_id is not None
            and self.resume_profile is not None
        )
        self.start_button.setEnabled(ready)
        if not ready:
            missing = []
            if not self.resume_profile:
                missing.append("upload resume")
            if not self.face_clear:
                missing.append("verify face")
            if not self.environment_clear:
                missing.append("clear environment")
            if not self.selected_job_id:
                missing.append("select a job")
            self.start_status_lbl.setText(f"Still needed: {', '.join(missing)}")
        else:
            self.start_status_lbl.setText("All checks passed. You are ready to begin.")

    def _launch_interview(self):
        """Generate first question in background, then emit interview_ready."""
        if not self.selected_job or not self.resume_profile:
            return

        # Release webcam before switching to interview
        if self.capture is not None:
            self._stop_camera()

        self.start_button.setEnabled(False)
        self.start_button.setText("Preparing questions...")
        self.start_status_lbl.setText("AI is preparing your personalised questions...")

        self._gen_thread = QThread()
        self._gen_worker = QuestionGeneratorWorker(
            self.selected_job["title"],
            self.selected_job["description"],
            self.resume_profile,
        )
        self._gen_worker.moveToThread(self._gen_thread)
        self._gen_thread.started.connect(self._gen_worker.run)
        self._gen_worker.finished.connect(self._on_questions_ready)
        self._gen_worker.failed.connect(self._on_questions_failed)
        self._gen_worker.finished.connect(self._gen_thread.quit)
        self._gen_worker.failed.connect(self._gen_thread.quit)
        self._gen_thread.finished.connect(self._gen_worker.deleteLater)
        self._gen_thread.finished.connect(self._gen_thread.deleteLater)
        self._gen_thread.finished.connect(self._on_gen_thread_finished)
        self._gen_thread.start()

    def _on_questions_ready(self, questions: list):
        self.start_button.setText("Start interview")
        self.start_status_lbl.setText("")
        self.interview_ready.emit(self.selected_job_id, questions)

    def _on_questions_failed(self, error: str):
        self.start_button.setEnabled(True)
        self.start_button.setText("Start interview")
        self.start_status_lbl.setText(f"Question generation failed: {error}. Using defaults.")
        # Emit with empty list — interview_page will use fallback
        self.interview_ready.emit(self.selected_job_id, [])

    def _on_gen_thread_finished(self):
        self._gen_worker = None
        self._gen_thread = None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        if self.capture is not None:
            self._stop_camera()
        if getattr(self, "_gen_thread", None) and self._gen_thread.isRunning():
            self._gen_thread.quit()
            self._gen_thread.wait(500)
