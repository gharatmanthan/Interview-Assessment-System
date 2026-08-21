import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.core import db
from app.core.models import Candidate, JobPosting


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def seeded_candidate(fresh_db):
    fresh_db.save_job_posting(JobPosting(
        job_id="job-1",
        title="Backend Engineer",
        description="Python and SQL.",
        required_skills=["Python"],
        experience_level="Junior",
        department="Engineering",
    ))
    candidate = Candidate(
        candidate_id="cand-1",
        job_id="job-1",
        name="Jane Doe",
        email="jane@example.com",
        invite_code="CODE123",
    )
    fresh_db.save_candidate(candidate)
    return candidate


class TestRoleSelectWindow:
    def test_recruiter_card_emits_recruiter_selected(self, qapp):
        from app.ui.role_select_window import RoleSelectWindow

        window = RoleSelectWindow()
        received = []
        window.recruiter_selected.connect(lambda: received.append("recruiter"))
        window.candidate_selected.connect(lambda: received.append("candidate"))

        window.recruiter_btn.click()

        assert received == ["recruiter"]

    def test_candidate_card_emits_candidate_selected(self, qapp):
        from app.ui.role_select_window import RoleSelectWindow

        window = RoleSelectWindow()
        received = []
        window.recruiter_selected.connect(lambda: received.append("recruiter"))
        window.candidate_selected.connect(lambda: received.append("candidate"))

        window.candidate_btn.click()

        assert received == ["candidate"]


class TestCandidateEntryWindow:
    def _submit_code(self, window, code):
        window.code_input.setText(code)
        window.submit_btn.click()

    def test_invalid_code_shows_inline_error_and_stays(self, qapp, fresh_db):
        from app.ui.candidate_entry_window import CandidateEntryWindow

        window = CandidateEntryWindow()
        successes = []
        window.entry_success.connect(lambda c: successes.append(c))

        self._submit_code(window, "BOGUS")

        assert window.error_label.isVisible() or window.error_label.text() != ""
        assert "Invalid" in window.error_label.text()
        assert window.stack.currentIndex() == 0
        assert successes == []

    def test_completed_code_rejected_with_exact_message(self, qapp, fresh_db, seeded_candidate):
        from app.ui.candidate_entry_window import CandidateEntryWindow

        db.update_candidate_status("cand-1", "completed")
        window = CandidateEntryWindow()

        self._submit_code(window, "CODE123")

        assert window.error_label.text() == "This interview has already been completed."
        assert window.stack.currentIndex() == 0

    def test_valid_code_moves_to_consent_with_start_disabled(self, qapp, fresh_db, seeded_candidate):
        from app.ui.candidate_entry_window import CandidateEntryWindow

        window = CandidateEntryWindow()

        self._submit_code(window, "CODE123")

        assert window.error_label.text() == ""
        assert window.stack.currentIndex() == 1
        assert window.start_btn.isEnabled() is False

    def test_consent_checkbox_gates_start_button(self, qapp, fresh_db, seeded_candidate):
        from app.ui.candidate_entry_window import CandidateEntryWindow

        window = CandidateEntryWindow()
        self._submit_code(window, "CODE123")

        window.consent_checkbox.setChecked(True)
        assert window.start_btn.isEnabled() is True
        window.consent_checkbox.setChecked(False)
        assert window.start_btn.isEnabled() is False

    def test_start_emits_full_candidate_dict(self, qapp, fresh_db, seeded_candidate):
        from app.ui.candidate_entry_window import CandidateEntryWindow

        window = CandidateEntryWindow()
        received = []
        window.entry_success.connect(lambda c: received.append(c))
        self._submit_code(window, "CODE123")
        window.consent_checkbox.setChecked(True)
        window.start_btn.click()

        assert len(received) == 1
        assert received[0]["candidate_id"] == "cand-1"
        assert received[0]["job_id"] == "job-1"
        assert received[0]["name"] == "Jane Doe"
        assert received[0]["invite_code"] == "CODE123"


class TestCandidateSessionWindow:
    def make_window(self, qapp, seeded_candidate):
        from app.ui.candidate_session_window import CandidateSessionWindow

        candidate = db.get_candidate_by_invite_code("CODE123")
        return CandidateSessionWindow(candidate)

    def test_opening_marks_candidate_in_progress_with_session_id(self, qapp, seeded_candidate):
        window = self.make_window(qapp, seeded_candidate)

        row = db.get_all_candidates()[0]
        assert row["status"] == "in_progress"
        assert row["session_id"] == window.interview_page.session_id

    def test_window_has_no_sidebar_and_hosts_interview_page(self, qapp, seeded_candidate):
        from app.ui.sidebar import Sidebar

        window = self.make_window(qapp, seeded_candidate)

        assert not isinstance(window.centralWidget(), Sidebar)
        children = window.interview_page.findChildren(Sidebar)
        assert children == []
        assert window.interview_page.candidate_id == "cand-1"
        assert window.interview_page.job_id == "job-1"

    def test_finish_marks_completed_and_shows_done_screen(self, qapp, seeded_candidate):
        from app.ui.candidate_session_window import DoneScreen

        window = self.make_window(qapp, seeded_candidate)

        window.interview_page.interview_finished.emit()

        assert db.get_all_candidates()[0]["status"] == "completed"
        assert isinstance(window.stack.currentWidget(), DoneScreen)

    def test_reset_button_emits_closed_for_next_candidate(self, qapp, seeded_candidate):
        window = self.make_window(qapp, seeded_candidate)
        window.interview_page.interview_finished.emit()

        closed = []
        window.closed.connect(lambda: closed.append(True))
        window.reset_btn.click()

        assert closed == [True]


class TestSidebarDevGate:
    def test_interview_tab_hidden_by_default(self, qapp, monkeypatch):
        monkeypatch.delenv("DEV_MODE", raising=False)
        from app.ui.sidebar import Sidebar

        sidebar = Sidebar()

        assert "interview" not in sidebar.buttons

    def test_interview_tab_visible_in_dev_mode(self, qapp, monkeypatch):
        monkeypatch.setenv("DEV_MODE", "1")
        from app.ui.sidebar import Sidebar

        sidebar = Sidebar()

        assert "interview" in sidebar.buttons


class TestMainWindowDevGate:
    def test_interview_page_absent_by_default(self, qapp, fresh_db, monkeypatch):
        monkeypatch.delenv("DEV_MODE", raising=False)
        from app.ui.main_window import MainWindow

        mw = MainWindow(logged_in_as="alice")

        assert "interview" not in mw.pages

    def test_interview_page_present_in_dev_mode(self, qapp, fresh_db, monkeypatch):
        monkeypatch.setenv("DEV_MODE", "1")
        from app.ui.main_window import MainWindow

        mw = MainWindow(logged_in_as="alice")

        assert "interview" in mw.pages


class TestAppControllerRouting:
    def test_app_starts_on_role_select(self, qapp, fresh_db):
        from app.main import AppController
        from app.ui.role_select_window import RoleSelectWindow

        controller = AppController(qapp)
        controller.start()

        assert isinstance(controller.role_window, RoleSelectWindow)
        assert controller.role_window.isVisible()

    def test_recruiter_path_login_then_logout_returns_to_role_select(self, qapp, fresh_db):
        from app.main import AppController
        from app.ui.login_window import LoginWindow
        from app.ui.main_window import MainWindow
        from app.ui.role_select_window import RoleSelectWindow

        controller = AppController(qapp)
        controller.start()

        controller.role_window.recruiter_btn.click()
        assert isinstance(controller.login_window, LoginWindow)

        controller.login_window.authenticated.emit("alice")
        assert isinstance(controller.main_window, MainWindow)

        controller.main_window.logout_requested.emit()
        assert controller.main_window is None
        assert isinstance(controller.role_window, RoleSelectWindow)
        assert controller.role_window.isVisible()

    def test_candidate_path_end_to_end_returns_to_role_select(self, qapp, fresh_db, seeded_candidate):
        from app.main import AppController
        from app.ui.candidate_entry_window import CandidateEntryWindow
        from app.ui.candidate_session_window import CandidateSessionWindow
        from app.ui.role_select_window import RoleSelectWindow

        controller = AppController(qapp)
        controller.start()

        controller.role_window.candidate_btn.click()
        assert isinstance(controller.entry_window, CandidateEntryWindow)

        controller.entry_window.code_input.setText("CODE123")
        controller.entry_window.submit_btn.click()
        controller.entry_window.consent_checkbox.setChecked(True)
        controller.entry_window.start_btn.click()

        assert isinstance(controller.session_window, CandidateSessionWindow)
        assert db.get_all_candidates()[0]["status"] == "in_progress"

        controller.session_window.interview_page.interview_finished.emit()
        assert db.get_all_candidates()[0]["status"] == "completed"

        controller.session_window.reset_btn.click()
        assert isinstance(controller.role_window, RoleSelectWindow)
        assert controller.role_window.isVisible()
