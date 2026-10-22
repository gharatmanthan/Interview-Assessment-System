"""
Owner: Member C
Touches: this file only (registered into main_window.py)

Camera/mic device selection, LLM provider config for Member B's
scoring pipeline, and default export directory.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt

from app.core import settings_store
from app.core.remote_api import RemoteApiClient

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


def detect_cameras(max_check=4):
    """Probe camera indices 0..max_check-1, return list of indices that open."""
    if not HAS_CV2:
        return [0]
    found = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found or [0]


def detect_mic_devices():
    """Return list of (name, index) for input-capable audio devices."""
    if not HAS_SOUNDDEVICE:
        return [("Default", "default")]
    try:
        devices = sd.query_devices()
        inputs = [(d["name"], i) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
        return inputs or [("Default", "default")]
    except Exception:
        return [("Default", "default")]


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        header = QLabel("Settings")
        header.setObjectName("PageTitle")
        sub = QLabel("Device selection, scoring model configuration, export preferences")
        sub.setObjectName("PageSubtitle")
        root.addWidget(header)
        root.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        form = QVBoxLayout(container)
        form.setSpacing(18)

        form.addWidget(self._section_label("Devices"))

        self.camera_combo = QComboBox()
        for idx in detect_cameras():
            self.camera_combo.addItem(f"Camera {idx}", idx)
        form.addWidget(self._field("Camera", self.camera_combo))

        self.mic_combo = QComboBox()
        for name, idx in detect_mic_devices():
            self.mic_combo.addItem(name, idx)
        form.addWidget(self._field("Microphone", self.mic_combo))

        form.addWidget(self._section_label("Scoring Model"))

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Groq", "Gemini", "OpenAI"])
        form.addWidget(self._field("LLM Provider", self.provider_combo))

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Paste your API key")
        form.addWidget(self._field("API Key", self.api_key_input))

        form.addWidget(self._section_label("Shared Backend"))

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("This PC (local SQLite)", "local")
        self.backend_combo.addItem("Shared Render API", "remote")
        form.addWidget(self._field("Data backend", self.backend_combo))

        self.remote_api_input = QLineEdit()
        self.remote_api_input.setPlaceholderText(
            "https://interviewiq-api-736y.onrender.com/api/v1"
        )
        form.addWidget(self._field("Remote API URL", self.remote_api_input))

        form.addWidget(self._section_label("Export"))

        export_row = QHBoxLayout()
        self.export_dir_input = QLineEdit()
        self.export_dir_input.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_export_dir)
        export_row.addWidget(self.export_dir_input, stretch=1)
        export_row.addWidget(browse_btn)
        export_wrapper = QWidget()
        export_wrapper.setLayout(export_row)
        form.addWidget(self._field("Default Export Folder", export_wrapper))

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        form.addWidget(save_btn)

        form.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, stretch=1)

        self._load_current_settings()

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
        return lbl

    def _field(self, label_text, widget):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280;")
        layout.addWidget(lbl)
        layout.addWidget(widget)
        return wrapper

    def _browse_export_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choose export folder")
        if path:
            self.export_dir_input.setText(path)

    def _load_current_settings(self):
        s = settings_store.load_settings()
        cam_idx = self.camera_combo.findData(s["camera_index"])
        if cam_idx >= 0:
            self.camera_combo.setCurrentIndex(cam_idx)
        mic_idx = self.mic_combo.findData(s["mic_device"])
        if mic_idx >= 0:
            self.mic_combo.setCurrentIndex(mic_idx)
        provider_idx = self.provider_combo.findText(s["llm_provider"])
        if provider_idx >= 0:
            self.provider_combo.setCurrentIndex(provider_idx)
        self.api_key_input.setText(s["llm_api_key"])
        self.export_dir_input.setText(s["export_dir"])
        backend_idx = self.backend_combo.findData(s.get("backend_mode", "local"))
        if backend_idx >= 0:
            self.backend_combo.setCurrentIndex(backend_idx)
        self.remote_api_input.setText(s.get("remote_api_url", ""))

    def _save(self):
        remote_url = self.remote_api_input.text().strip().rstrip("/")
        if self.backend_combo.currentData() == "remote" or remote_url:
            try:
                remote_url = RemoteApiClient._normalize_base_url(remote_url)
            except ValueError as error:
                QMessageBox.warning(self, "Invalid API URL", str(error))
                self.remote_api_input.setFocus()
                return
        previous = settings_store.load_settings()
        backend_mode = self.backend_combo.currentData()
        backend_changed = (
            previous.get("backend_mode", "local") != backend_mode
            or (previous.get("remote_api_url", "") or "").rstrip("/") != remote_url
        )
        settings_store.save_settings({
            "camera_index": self.camera_combo.currentData(),
            "mic_device": self.mic_combo.currentData(),
            "llm_provider": self.provider_combo.currentText(),
            "llm_api_key": self.api_key_input.text(),
            "export_dir": self.export_dir_input.text(),
            "backend_mode": backend_mode,
            "remote_api_url": remote_url,
        })
        if backend_changed:
            from app.core import db
            db.reset_remote_client()
            QMessageBox.information(
                self,
                "Settings saved",
                "Backend connection changed.\n\n"
                "Restart the app and sign in again so the new backend is used "
                "and your session is authorized against it.",
            )
            return
        QMessageBox.information(self, "Settings saved", "Your settings have been saved.")
