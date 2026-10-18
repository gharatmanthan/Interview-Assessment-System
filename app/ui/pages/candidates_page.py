from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import db


class CandidatesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(14)

        title = QLabel("Candidate Accounts")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Create login credentials for a new interview candidate")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_panel = QGroupBox("New candidate")
        form_layout = QFormLayout(form_panel)
        form_layout.setContentsMargins(18, 22, 18, 18)
        form_layout.setVerticalSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Candidate full name")
        form_layout.addRow("Full name", self.name_input)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Unique login ID")
        form_layout.addRow("Candidate ID", self.id_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Temporary password")
        self.password_input.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Password", self.password_input)
        layout.addWidget(form_panel)

        create_button = QPushButton("Create Candidate Account")
        create_button.setObjectName("PrimaryButton")
        create_button.clicked.connect(self.create_account)
        layout.addWidget(create_button)

        self.result = QLabel("No candidate account created in this session.")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch()

    def create_account(self):
        full_name = self.name_input.text().strip()
        candidate_id = self.id_input.text().strip()
        password = self.password_input.text()

        if not full_name or not candidate_id or not password:
            QMessageBox.warning(self, "Missing details", "Enter a name, candidate ID, and password.")
            return

        if not db.create_candidate_account(candidate_id, password, full_name):
            QMessageBox.warning(self, "ID already exists", "Choose a different candidate ID.")
            return

        self.name_input.clear()
        self.id_input.clear()
        self.password_input.clear()
        self.result.setText(f"Created account for {full_name}. They can now sign in as a candidate.")