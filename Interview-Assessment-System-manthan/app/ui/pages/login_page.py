from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from app.core import db


class CandidateLoginPage(QWidget):
    authenticated = Signal(dict)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(120, 80, 120, 80)
        layout.setSpacing(18)

        title = QLabel("Candidate Sign In")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Sign in to access your interview dashboard")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_panel = QGroupBox("Candidate access")
        form = QFormLayout(form_panel)
        form.setContentsMargins(18, 22, 18, 18)
        form.setVerticalSpacing(14)
        self.candidate_id = QLineEdit()
        self.candidate_id.setPlaceholderText("Enter your candidate ID")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter your password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self._login)
        form.addRow("Candidate ID", self.candidate_id)
        form.addRow("Password", self.password)
        layout.addWidget(form_panel)

        self.status = QLabel("Use the candidate credentials provided by your interviewer.")
        self.status.setObjectName("PageSubtitle")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        login_button = QPushButton("Sign In")
        login_button.setObjectName("PrimaryButton")
        login_button.clicked.connect(self._login)
        layout.addWidget(login_button)
        layout.addStretch()

    def _login(self):
        candidate_id = self.candidate_id.text().strip()
        password = self.password.text()
        account = db.authenticate_candidate(candidate_id, password)
        if account:
            self.authenticated.emit(account)
            return
        self.status.setText("Invalid candidate ID or password.")
        self.status.setStyleSheet("color: #EF4444; font-weight: 600;")
        QMessageBox.warning(self, "Sign in failed", "Please check your candidate ID and password.")
