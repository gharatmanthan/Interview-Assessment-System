"""
AI-Powered Interview Assessment System
Entry point for the desktop application.

Routing: RoleSelectWindow is the first screen. Recruiters go through the
existing LoginWindow -> MainWindow flow; candidates go straight to
CandidateEntryWindow -> CandidateSessionWindow with their invite code.
All exits (logout, interview finished, window closed) return to the role
selector so one machine can serve the next person without a restart.
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.ui.role_select_window import RoleSelectWindow
from app.ui.login_window import LoginWindow
from app.ui.candidate_entry_window import CandidateEntryWindow
from app.ui.candidate_session_window import CandidateSessionWindow
from app.ui.main_window import MainWindow
from app.utils.theme import STYLESHEET
from app.core import db


class AppController:
    """Holds references so windows don't get garbage-collected between
    handoffs, and routes between the recruiter and candidate flows.
    """
    def __init__(self, app):
        self.app = app
        self._quitting = False
        app.aboutToQuit.connect(self._on_about_to_quit)

        self.role_window = None
        self.login_window = None
        self.main_window = None
        self.entry_window = None
        self.session_window = None

    def _on_about_to_quit(self):
        self._quitting = True

    def start(self):
        self._show_role_select()

    # --- shared ---

    def _show_role_select(self):
        if self._quitting:
            return
        self.role_window = RoleSelectWindow()
        self.role_window.recruiter_selected.connect(self._on_recruiter_selected)
        self.role_window.candidate_selected.connect(self._on_candidate_selected)
        self.role_window.show()

    def _return_to_role_select(self):
        if not self._quitting:
            self._show_role_select()

    # --- recruiter flow (unchanged behavior) ---

    def _on_recruiter_selected(self):
        self._close_role_select()
        self.login_window = LoginWindow()
        self.login_window.authenticated.connect(self._on_authenticated)
        self.login_window.closed.connect(self._on_login_closed)
        self.login_window.show()

    def _on_authenticated(self, username):
        if self.login_window:
            self.login_window.closed.disconnect(self._on_login_closed)
            self.login_window.close()
            self.login_window = None

        self.main_window = MainWindow(logged_in_as=username)
        self.main_window.logout_requested.connect(self._on_logout)
        self.main_window.show()

    def _on_login_closed(self):
        self.login_window = None
        self._return_to_role_select()

    def _on_logout(self):
        if self.main_window:
            self.main_window.close()
            self.main_window = None
        self._return_to_role_select()

    # --- candidate flow ---

    def _on_candidate_selected(self):
        self._close_role_select()
        self.entry_window = CandidateEntryWindow()
        self.entry_window.entry_success.connect(self._on_entry_success)
        self.entry_window.closed.connect(self._on_entry_closed)
        self.entry_window.show()

    def _on_entry_success(self, candidate):
        if self.entry_window:
            self.entry_window.closed.disconnect(self._on_entry_closed)
            self.entry_window.close()
            self.entry_window = None

        self.session_window = CandidateSessionWindow(candidate)
        self.session_window.closed.connect(self._on_session_closed)
        self.session_window.show()

    def _on_entry_closed(self):
        self.entry_window = None
        self._return_to_role_select()

    def _on_session_closed(self):
        self.session_window = None
        self._return_to_role_select()

    def _close_role_select(self):
        if self.role_window:
            self.role_window.close()
            self.role_window = None


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
