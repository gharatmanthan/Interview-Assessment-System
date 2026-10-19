from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core import db


class JobPostingPage(QWidget):
    jobs_changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(14)

        title = QLabel("Create Job Posting")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Publish an interview opportunity for candidates")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_panel = QGroupBox("Role details")
        form_layout = QFormLayout(form_panel)
        form_layout.setContentsMargins(18, 22, 18, 18)
        form_layout.setVerticalSpacing(12)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Job title, for example: Python Developer")
        form_layout.addRow("Job title", self.title_input)

        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Describe the role, skills, and interview expectations")
        self.description_input.setMinimumHeight(180)
        form_layout.addRow("Description", self.description_input)
        layout.addWidget(form_panel)

        publish_button = QPushButton("Publish Job")
        publish_button.setObjectName("PrimaryButton")
        publish_button.clicked.connect(self.publish)
        layout.addWidget(publish_button)

        self.result = QLabel("No job published in this session.")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch()

    def publish(self):
        title = self.title_input.text().strip()
        description = self.description_input.toPlainText().strip()
        if not title or not description:
            QMessageBox.warning(self, "Missing details", "Enter both a job title and description.")
            return
        db.save_job_posting(title, description)
        self.title_input.clear()
        self.description_input.clear()
        self.result.setText(f"Published: {title}. Candidates can now see this posting.")
        self.jobs_changed.emit()
