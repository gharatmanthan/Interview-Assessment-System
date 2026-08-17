"""
AI-Powered Interview Assessment System
Entry point for the desktop application.
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.ui.main_window import MainWindow
from app.utils.theme import STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Interview Assessment System")
    app.setStyleSheet(STYLESHEET)

    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
