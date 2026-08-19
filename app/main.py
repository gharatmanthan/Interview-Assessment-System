"""
AI-Powered Interview Assessment System
Entry point for the desktop application.
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow
from app.utils.theme import STYLESHEET
from app.core import db


class AppController:
    """Holds references so LoginWindow and MainWindow don't get
    garbage-collected between the login -> main-window handoff.
    """
    def __init__(self, app):
        self.app = app
        self.login_window = LoginWindow()
        self.login_window.authenticated.connect(self._on_authenticated)
        self.main_window = None

    def _on_authenticated(self, username):
        self.main_window = MainWindow(logged_in_as=username)
        self.main_window.logout_requested.connect(self._on_logout)
        self.main_window.show()
        self.login_window.close()

    def _on_logout(self):
        if self.main_window:
            self.main_window.close()
            self.main_window = None
        # fresh LoginWindow instance so login/password fields start empty
        self.login_window = LoginWindow()
        self.login_window.authenticated.connect(self._on_authenticated)
        self.login_window.show()

    def start(self):
        self.login_window.show()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Interview Assessment System")
    app.setStyleSheet(STYLESHEET)

    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    db.init_db()

    controller = AppController(app)
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
