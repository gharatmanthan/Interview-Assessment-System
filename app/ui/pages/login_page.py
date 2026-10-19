from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget
import requests

from app.core import db


class RoleLoginPage(QWidget):
    authenticated = Signal(dict)

    def __init__(self, role="candidate"):
        super().__init__()
        self.role = role
        self.setObjectName("LoginPage")

        root = QHBoxLayout(self)
        root.setContentsMargins(80, 60, 80, 60)
        root.setSpacing(80)

        brand = QVBoxLayout()
        brand.setSpacing(12)
        mark = QLabel("IQ")
        mark.setObjectName("LoginMark")
        brand.addWidget(mark)
        title = QLabel("InterviewIQ")
        title.setObjectName("LoginBrand")
        brand.addWidget(title)
        copy = QLabel("A clearer signal for every interview.\nStructured, explainable, and built for people.")
        copy.setObjectName("LoginBrandCopy")
        copy.setWordWrap(True)
        brand.addWidget(copy)
        brand.addStretch()
        root.addLayout(brand, stretch=1)

        panel = QWidget()
        panel.setObjectName("LoginPanel")
        panel.setMaximumWidth(440)
        form = QVBoxLayout(panel)
        form.setContentsMargins(36, 34, 36, 34)
        form.setSpacing(14)

        kicker = QLabel("SECURE WORKSPACE")
        kicker.setObjectName("LoginKicker")
        form.addWidget(kicker)
        heading = QLabel("Sign in to continue")
        heading.setObjectName("LoginTitle")
        form.addWidget(heading)
        description = QLabel("Access your interview workspace and pick up where you left off.")
        description.setObjectName("LoginCopy")
        description.setWordWrap(True)
        form.addWidget(description)
        form.addSpacing(8)

        role_row = QHBoxLayout()
        self.candidate_btn = QPushButton("Candidate")
        self.interviewer_btn = QPushButton("Interviewer")
        for button in (self.candidate_btn, self.interviewer_btn):
            button.setCheckable(True)
            button.setObjectName("RoleButton")
            role_row.addWidget(button)
        self.candidate_btn.clicked.connect(lambda: self._set_role("candidate"))
        self.interviewer_btn.clicked.connect(lambda: self._set_role("interviewer"))
        form.addLayout(role_row)

        self.identity = QLineEdit()
        self.identity.setPlaceholderText("Candidate ID" if role == "candidate" else "Interviewer ID")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self._login)
        form.addWidget(self.identity)
        form.addWidget(self.password)

        self.status = QLabel("Use the credentials provided by your organization.")
        self.status.setObjectName("LoginStatus")
        self.status.setWordWrap(True)
        form.addWidget(self.status)
        button = QPushButton("Enter workspace")
        button.setObjectName("PrimaryButton")
        button.setMinimumHeight(44)
        button.clicked.connect(self._login)
        form.addWidget(button)
        form.addStretch()
        root.addWidget(panel, stretch=1)
        self._set_role(role)

    def _set_role(self, role):
        self.role = role
        self.candidate_btn.setChecked(role == "candidate")
        self.interviewer_btn.setChecked(role == "interviewer")
        self.identity.setPlaceholderText("Candidate ID" if role == "candidate" else "Interviewer ID")
        self.status.setText("Candidate access is ready." if role == "candidate" else "Interviewer access is restricted to authorized staff.")

    def _login(self):
        identity = self.identity.text().strip()
        password = self.password.text()
        if not identity or not password:
            self._show_login_error("Enter both your ID and password.")
            return
        try:
            if self.role == "candidate":
                account = db.authenticate_candidate(identity, password)
            else:
                account = db.authenticate_interviewer(identity, password)
        except (requests.RequestException, RuntimeError, OSError) as error:
            self._show_login_error(f"Unable to reach the interview service: {error}")
            return
        if account:
            self.authenticated.emit(account)
            return

        if self.role == "interviewer":
            message = (
                "Interviewer credentials are configured by the organization. "
                "Set INTERVIEWER_ID and INTERVIEWER_PASSWORD, or use the values "
                "supplied by the Render deployment owner."
            )
        else:
            message = "That candidate ID and password do not match."
        self._show_login_error(message)

    def _show_login_error(self, message):
        self.status.setText(message)
        self.status.setStyleSheet("color: #C2413A; font-weight: 700;")
        QMessageBox.warning(self, "Sign in failed", message)


CandidateLoginPage = RoleLoginPage
InterviewerLoginPage = RoleLoginPage
