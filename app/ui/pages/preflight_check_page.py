"""
Pre-interview checks for the candidate flow (integrated from the teammate's
candidate dashboard): environment scan (USB/serial devices) plus a camera
face check that enrolls the candidate's face on first pass. "Start Interview"
stays disabled until both gates pass.
"""
import cv2
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.candidate.face_recognition import enroll_face, has_enrolled_face, verify_single_face
from app.utils.port_scanner import get_unauthorized_devices


class PreflightCheckPage(QWidget):
    start_requested = Signal()

    def __init__(self, candidate_id=None, job_title=None):
        super().__init__()
        self.candidate_id = candidate_id
        self.capture = None
        self.latest_frame = None
        self.environment_clear = False
        self.face_clear = False
        self.face_enrolled = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_camera)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(14)

        title = QLabel("Pre-Interview Checks")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Complete the environment and camera checks before your interview")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        job_label = QLabel(f"Interview: {job_title or 'General Interview Session'}")
        job_label.setObjectName("PageSubtitle")
        job_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #1B1F2A;")
        layout.addWidget(job_label)

        self.camera_preview = QLabel("Camera preview\nClick 'Start Camera' to verify your face")
        self.camera_preview.setAlignment(Qt.AlignCenter)
        self.camera_preview.setMinimumSize(480, 300)
        self.camera_preview.setStyleSheet("background-color: #111827; color: #9CA3AF; border-radius: 8px;")
        layout.addWidget(self.camera_preview)

        self.status = QLabel("System check has not run.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons_row = QVBoxLayout()
        self.environment_button = QPushButton("Re-scan Environment")
        self.environment_button.setObjectName("SecondaryButton")
        self.environment_button.clicked.connect(self.check_environment)
        buttons_row.addWidget(self.environment_button)

        self.camera_button = QPushButton("Start Camera")
        self.camera_button.setObjectName("SecondaryButton")
        self.camera_button.clicked.connect(self._toggle_camera)
        buttons_row.addWidget(self.camera_button)
        layout.addLayout(buttons_row)

        self.start_button = QPushButton("Start Interview")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_requested.emit)
        layout.addWidget(self.start_button)

        if self.candidate_id:
            self.face_enrolled = has_enrolled_face(self.candidate_id)
        self.check_environment()

    def check_environment(self):
        devices = get_unauthorized_devices()
        self.environment_clear = not devices
        if devices:
            self.status.setText("Environment check failed:\n" + "\n".join(f"- {d}" for d in devices))
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
        if self.capture:
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
        self._check_face()
        self._update_start_state()

    def _check_face(self):
        if self.latest_frame is None:
            return
        verified, message = verify_single_face(self.latest_frame)
        self.face_clear = verified
        if verified:
            was_enrolled = self.face_enrolled
            if not was_enrolled:
                if not enroll_face(self.candidate_id, self.latest_frame):
                    self.face_clear = False
                    self.status.setText("Face detected, but it could not be saved. Scan again.")
                    self.status.setStyleSheet("color: #EF4444; font-weight: 600;")
                    return
                self.face_enrolled = True
            message = ("Candidate face already enrolled and verified." if was_enrolled
                       else "Face scan saved. Candidate face verified.")
            self.status.setText(message)
            self.status.setStyleSheet("color: #14B8A6; font-weight: 600;")
        elif self.environment_clear:
            self.status.setText(message)
            self.status.setStyleSheet("color: #F59E0B; font-weight: 600;")

    def _update_start_state(self):
        self.start_button.setEnabled(self.environment_clear and self.face_clear)

    def cleanup(self):
        if self.capture is not None:
            self._stop_camera()
