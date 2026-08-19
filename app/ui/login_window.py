"""
Owner: Member C
Touches: this file, app/main.py

Standalone login window shown before MainWindow. Emits `authenticated`
with the logged-in username once login succeeds.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QStackedWidget
)
from PySide6.QtCore import Qt, Signal

from app.core import auth


class LoginForm(QWidget):
    def __init__(self, on_login_success, switch_to_register):
        super().__init__()
        self.on_login_success = on_login_success

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Recruiter Login")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._submit)
        layout.addWidget(self.password_input)

        login_btn = QPushButton("Log In")
        login_btn.setObjectName("PrimaryButton")
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.clicked.connect(self._submit)
        layout.addWidget(login_btn)

        switch_row = QHBoxLayout()
        switch_row.addStretch()
        switch_link = QPushButton("Don't have an account? Register")
        switch_link.setFlat(True)
        switch_link.setCursor(Qt.PointingHandCursor)
        switch_link.clicked.connect(switch_to_register)
        switch_row.addWidget(switch_link)
        layout.addLayout(switch_row)

    def _submit(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Missing info", "Enter both username and password.")
            return

        success, message = auth.verify_recruiter(username, password)
        if success:
            self.on_login_success(username)
        else:
            QMessageBox.warning(self, "Login failed", message)


class RegisterForm(QWidget):
    def __init__(self, on_register_success, switch_to_login):
        super().__init__()
        self.on_register_success = on_register_success

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Create Recruiter Account")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Full name")
        layout.addWidget(self.name_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Choose a username")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Choose a password (6+ characters)")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._submit)
        layout.addWidget(self.password_input)

        register_btn = QPushButton("Create Account")
        register_btn.setObjectName("PrimaryButton")
        register_btn.setCursor(Qt.PointingHandCursor)
        register_btn.clicked.connect(self._submit)
        layout.addWidget(register_btn)

        switch_row = QHBoxLayout()
        switch_row.addStretch()
        switch_link = QPushButton("Already have an account? Log in")
        switch_link.setFlat(True)
        switch_link.setCursor(Qt.PointingHandCursor)
        switch_link.clicked.connect(switch_to_login)
        switch_row.addWidget(switch_link)
        layout.addLayout(switch_row)

    def _submit(self):
        name = self.name_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Missing info", "Username and password are required.")
            return

        success, message = auth.register_recruiter(username, password, name)
        if success:
            QMessageBox.information(self, "Account created", "You can now log in.")
            self.on_register_success(username)
        else:
            QMessageBox.warning(self, "Could not create account", message)


class LoginWindow(QWidget):
    authenticated = Signal(str)  # emits username on success

    def __init__(self):
        super().__init__()
        self.setWindowTitle("InterviewIQ — Recruiter Login")
        self.resize(420, 360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 50, 40, 50)

        card = QWidget()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)

        self.stack = QStackedWidget()
        self.login_form = LoginForm(self._on_success, self._show_register)
        self.register_form = RegisterForm(self._on_success, self._show_login)
        self.stack.addWidget(self.login_form)
        self.stack.addWidget(self.register_form)

        card_layout.addWidget(self.stack)
        outer.addWidget(card)

    def _show_register(self):
        self.stack.setCurrentWidget(self.register_form)

    def _show_login(self):
        self.stack.setCurrentWidget(self.login_form)

    def _on_success(self, username):
        self.authenticated.emit(username)
