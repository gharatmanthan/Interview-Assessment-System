import cv2
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.candidate.face_recognition import enroll_face, has_enrolled_face, verify_single_face
from app.candidate.resume import extract_resume, match_resume_to_job, profile_json
from app.core import db
from app.utils.port_scanner import get_unauthorized_devices


class CandidateDashboard(QWidget):
    start_interview_requested = Signal(int)

    def __init__(self, candidate_id=None):
        super().__init__()
        self.candidate_id = candidate_id
        self.capture = None
        self.latest_frame = None
        self.environment_clear = False
        self.face_clear = False
        self.face_enrolled = False
        self.selected_job_id = None
        self.resume_profile = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_camera)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(18)

        title = QLabel("Candidate Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Complete the environment and camera checks before your interview")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        workspace = QHBoxLayout()
        workspace.setSpacing(18)

        jobs_group = QGroupBox("Choose an interview")
        jobs_layout = QVBoxLayout(jobs_group)
        jobs_layout.setSpacing(10)
        self.jobs_list = QListWidget()
        self.jobs_list.setMinimumHeight(150)
        self.jobs_list.itemSelectionChanged.connect(self._update_start_state)
        jobs_layout.addWidget(self.jobs_list)
        refresh_jobs_button = QPushButton("Refresh Jobs")
        refresh_jobs_button.setObjectName("SecondaryButton")
        refresh_jobs_button.clicked.connect(self.load_jobs)
        jobs_layout.addWidget(refresh_jobs_button)
        workspace.addWidget(jobs_group, stretch=1)

        resume_group = QGroupBox("Resume and role match")
        resume_layout = QVBoxLayout(resume_group)
        resume_layout.setSpacing(10)
        self.resume_status = QLabel("Upload your resume before starting the interview.")
        self.resume_status.setWordWrap(True)
        resume_layout.addWidget(self.resume_status)
        upload_resume_button = QPushButton("Upload Resume")
        upload_resume_button.setObjectName("SecondaryButton")
        upload_resume_button.clicked.connect(self.upload_resume)
        resume_layout.addWidget(upload_resume_button)
        resume_layout.addStretch()
        workspace.addWidget(resume_group, stretch=1)
        layout.addLayout(workspace)

        checks_group = QGroupBox("Readiness checks")
        checks_layout = QVBoxLayout(checks_group)
        checks_layout.setSpacing(10)
        self.camera_preview = QLabel("Camera preview\nClick 'Start Camera' to verify your face")
        self.camera_preview.setAlignment(Qt.AlignCenter)
        self.camera_preview.setMinimumSize(420, 230)
        self.camera_preview.setStyleSheet("background-color: #102A43; color: #9FB3C8; border-radius: 7px;")
        checks_layout.addWidget(self.camera_preview)

        self.status = QLabel("System check has not run.")
        self.status.setWordWrap(True)
        checks_layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.environment_button = QPushButton("Re-scan Environment")
        self.environment_button.setObjectName("SecondaryButton")
        self.environment_button.clicked.connect(self.check_environment)
        actions.addWidget(self.environment_button)

        self.camera_button = QPushButton("Start Camera")
        self.camera_button.setObjectName("SecondaryButton")
        self.camera_button.clicked.connect(self._toggle_camera)
        actions.addWidget(self.camera_button)
        checks_layout.addLayout(actions)

        self.start_button = QPushButton("Start Interview")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_selected_interview)
        checks_layout.addWidget(self.start_button)
        layout.addWidget(checks_group, stretch=1)

        self.check_environment()
        self.load_jobs()

    def load_jobs(self):
        self.jobs_list.clear()
        jobs = db.get_active_job_postings()
        for job in jobs:
            item = self.jobs_list.addItem(f"{job['title']} - {job['description']}")
            self.jobs_list.item(self.jobs_list.count() - 1).setData(Qt.UserRole, job["id"])
        if not jobs:
            self.jobs_list.addItem("No active job postings are available yet.")
            self.jobs_list.item(0).setFlags(Qt.NoItemFlags)
        self._update_start_state()

    def upload_resume(self):
        if not self.candidate_id:
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
            self.resume_status.setText(
                f"Resume loaded: {profile['file_name']}\n"
                f"Detected skills: {', '.join(profile['skills']) or 'None'}"
            )
            self.resume_status.setStyleSheet("color: #14B8A6; font-weight: 600;")
            self._update_match_status()
            self._update_start_state()
        except (OSError, ValueError, ImportError) as error:
            QMessageBox.warning(self, "Resume could not be read", str(error))

    def _update_match_status(self):
        selected = self.jobs_list.currentItem()
        if not self.resume_profile or not selected or selected.data(Qt.UserRole) is None:
            return
        job = next(
            (item for item in db.get_active_job_postings() if item["id"] == selected.data(Qt.UserRole)),
            None,
        )
        if not job:
            return
        match = match_resume_to_job(self.resume_profile, job["title"], job["description"])
        missing = ", ".join(match["missing_skills"]) or "None"
        self.resume_status.setText(
            f"Resume: {self.resume_profile['file_name']} | Role match: {match['score']}%\n"
            f"Matched: {', '.join(match['matched_skills']) or 'None'} | Missing: {missing}"
        )

    def check_environment(self):
        self.status.setText("Checking connected USB and serial devices...")
        QApplication.processEvents()
        devices = get_unauthorized_devices()
        self.environment_clear = not devices
        if devices:
            self.status.setText("Environment check failed:\n" + "\n".join(f"- {device}" for device in devices))
            self.status.setStyleSheet("color: #EF4444; font-weight: 600;")
        else:
            self.status.setText("Environment check passed. Start the camera for the face check.")
            self.status.setStyleSheet("color: #14B8A6; font-weight: 600;")
        self._update_start_state()

    def _toggle_camera(self):
        if self.capture is not None:
            self._stop_camera()
            return
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            self.status.setText("Camera could not be opened. Check camera permissions and try again.")
            self.status.setStyleSheet("color: #EF4444; font-weight: 600;")
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
        self._update_start_state()

    def _update_camera(self):
        ok, frame = self.capture.read()
        if not ok:
            return
        self.latest_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888)
        self.camera_preview.setPixmap(QPixmap.fromImage(image).scaled(
            self.camera_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        self._update_face_state()

    def set_candidate(self, candidate_id):
        self.candidate_id = candidate_id
        self.face_enrolled = has_enrolled_face(candidate_id)
        saved_profile = db.get_candidate_profile(candidate_id)
        if saved_profile:
            self.resume_profile = saved_profile["profile"]
            self.resume_status.setText(
                f"Resume loaded: {self.resume_profile.get('file_name', 'Saved resume')}\n"
                f"Detected skills: {', '.join(self.resume_profile.get('skills', [])) or 'None'}"
            )
            self.resume_status.setStyleSheet("color: #14B8A6; font-weight: 600;")
        self._update_start_state()

    def _face_verified(self):
        if self.latest_frame is None:
            return False
        verified, message = verify_single_face(self.latest_frame)
        self.face_clear = verified
        if verified:
            was_enrolled = self.face_enrolled
            if not was_enrolled and not enroll_face(self.candidate_id, self.latest_frame):
                self.face_clear = False
                self.status.setText("Face detected, but it could not be saved. Scan again.")
                self.status.setStyleSheet("color: #EF4444; font-weight: 600;")
                return False
            self.face_enrolled = True
            message = "Candidate face already enrolled and verified." if was_enrolled else "Face scan saved. Candidate face verified."
            self.status.setText(message)
            self.status.setStyleSheet("color: #14B8A6; font-weight: 600;")
        elif self.environment_clear:
            self.status.setText(message)
            self.status.setStyleSheet("color: #F59E0B; font-weight: 600;")
        return verified

    def _update_start_state(self):
        selected = self.jobs_list.currentItem()
        self.selected_job_id = selected.data(Qt.UserRole) if selected else None
        self._update_match_status()
        self.start_button.setEnabled(
            self.environment_clear
            and self.face_clear
            and self.selected_job_id is not None
            and self.resume_profile is not None
        )

    def _start_selected_interview(self):
        if self.selected_job_id is not None:
            self.start_interview_requested.emit(self.selected_job_id)

    def _update_face_state(self):
        if self.latest_frame is not None:
            self._face_verified()
        self._update_start_state()

    def cleanup(self):
        if self.capture is not None:
            self._stop_camera()
