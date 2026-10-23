"""
AI-Powered Interview Assessment System
Entry point for the desktop application.
"""
import sys
import os
import argparse
import traceback

# Prevent OpenMP library collision aborts on Windows between OpenCV and faster-whisper
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

def _global_exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = _global_exception_hook

from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PySide6.QtGui import QFont

from app.ui.main_window import MainWindow
from app.utils.theme import STYLESHEET


class RoleSelector(QDialog):
    def __init__(self):
        super().__init__()
        self.role = None
        self.setWindowTitle("InterviewIQ - Select role")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        title = QLabel("How will you use InterviewIQ?")
        title.setObjectName("LoginTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("Choose a role to open the desktop workspace."))
        buttons = QHBoxLayout()
        for role, label in (("candidate", "Candidate"), ("interviewer", "Interviewer")):
            button = QPushButton(label)
            button.setMinimumHeight(48)
            button.setObjectName("PrimaryButton")
            button.clicked.connect(lambda checked=False, value=role: self._choose(value))
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _choose(self, role):
        self.role = role
        self.accept()


def main():
    parser = argparse.ArgumentParser(description="Run InterviewIQ.")
    parser.add_argument(
        "--role", choices=("candidate", "interviewer"),
        help="Skip the role selector (useful for shortcuts and testing).",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Interview Assessment System")
    app.setStyleSheet(STYLESHEET)

    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    selector = None
    if args.role is None:
        selector = RoleSelector()
        if selector.exec() != QDialog.Accepted:
            return
        args.role = selector.role

    window = MainWindow(user_role=args.role)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
