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

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.ui.main_window import MainWindow
from app.utils.theme import STYLESHEET


def main():
    parser = argparse.ArgumentParser(description="Run InterviewIQ.")
    parser.add_argument("--role", choices=("candidate", "interviewer"), default="candidate")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Interview Assessment System")
    app.setStyleSheet(STYLESHEET)

    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    window = MainWindow(user_role=args.role)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
