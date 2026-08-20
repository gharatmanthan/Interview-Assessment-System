"""
Owner: Member C
Touches: this file only (registered into main_window.py + sidebar.py)

Invite candidates to a job posting (generates a unique invite code) and
track their status end to end: invited -> in_progress -> completed.
This is what makes the dashboard's candidate view complete — candidates
who haven't started an interview yet still show up here, not just
finished sessions.

Also wires resume upload -> app/engine/resume_parser.py (Member B) ->
app/engine/jd_matcher.py (Member B) -> stored match score + skill gaps,
closing the "resume parsing" Objective 2 deliverable on the UI side.
"""
import os
import shutil
import uuid
import secrets
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QScrollArea, QMessageBox, QApplication, QFileDialog
)
from PySide6.QtCore import Qt

from app.core import db
from app.core.models import Candidate

RESUME_DIR = Path(__file__).parent.parent.parent.parent / "data" / "resumes"

STATUS_COLORS = {
    "invited": ("#EEF2FF", "#4338CA"),
    "in_progress": ("#FEF3C7", "#92400E"),
    "completed": ("#D1FAE5", "#065F46"),
    "expired": ("#F3F4F6", "#6B7280"),
}


def generate_invite_code() -> str:
    return secrets.token_urlsafe(6)


def _match_score_color(score):
    if score is None:
        return "#9CA3AF"
    if score >= 70:
        return "#10B981"
    if score >= 40:
        return "#F59E0B"
    return "#EF4444"


class CandidateRow(QWidget):
    def __init__(self, candidate, on_copy, on_resend, on_revoke, on_attach_resume):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(candidate["name"])
        name.setStyleSheet("font-size: 13px; font-weight: 700;")
        top.addWidget(name)
        top.addStretch()

        status = candidate["status"]
        bg, fg = STATUS_COLORS.get(status, STATUS_COLORS["invited"])
        badge = QLabel(status.replace("_", " ").title())
        badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 6px; "
            f"padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(badge)

        match_score = candidate.get("match_score")
        if match_score is not None:
            m_badge = QLabel(f"JD Match: {match_score:.0f}%")
            m_badge.setStyleSheet(
                f"color: {_match_score_color(match_score)}; font-size: 11px; font-weight: 700; margin-left: 8px;"
            )
            top.addWidget(m_badge)
        layout.addLayout(top)

        email = QLabel(candidate["email"])
        email.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(email)

        if candidate.get("resume_path"):
            skills = candidate.get("resume_skills") or []
            matched = candidate.get("matched_skills") or []
            missing = candidate.get("missing_skills") or []
            resume_lbl = QLabel(
                f"Resume: {len(skills)} skill(s) found · "
                f"{len(matched)} matched · {len(missing)} missing"
                + (f" ({', '.join(missing[:4])}{'…' if len(missing) > 4 else ''})" if missing else "")
            )
            resume_lbl.setWordWrap(True)
            resume_lbl.setStyleSheet("font-size: 11px; color: #6B7280; margin-top: 2px;")
            layout.addWidget(resume_lbl)

        code_row = QHBoxLayout()
        code_lbl = QLabel(f"Invite code: {candidate['invite_code']}")
        code_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF; font-family: monospace;")
        code_row.addWidget(code_lbl)
        code_row.addStretch()

        attach_btn = QPushButton("Attach resume" if not candidate.get("resume_path") else "Replace resume")
        attach_btn.setFlat(True)
        attach_btn.setCursor(Qt.PointingHandCursor)
        attach_btn.clicked.connect(lambda: on_attach_resume(candidate["candidate_id"], candidate["job_id"]))
        code_row.addWidget(attach_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.setFlat(True)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(lambda: on_copy(candidate["invite_code"]))
        code_row.addWidget(copy_btn)

        resend_btn = QPushButton("Resend (new code)")
        resend_btn.setFlat(True)
        resend_btn.setCursor(Qt.PointingHandCursor)
        resend_btn.clicked.connect(lambda: on_resend(candidate["candidate_id"], candidate["name"]))
        code_row.addWidget(resend_btn)

        revoke_btn = QPushButton("Revoke")
        revoke_btn.setFlat(True)
        revoke_btn.setCursor(Qt.PointingHandCursor)
        revoke_btn.setStyleSheet("color: #EF4444;")
        revoke_btn.clicked.connect(lambda: on_revoke(candidate["candidate_id"], candidate["name"]))
        code_row.addWidget(revoke_btn)

        layout.addLayout(code_row)


class CandidatesPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        header = QLabel("Candidates")
        header.setObjectName("PageTitle")
        sub = QLabel("Invite candidates, attach resumes for JD matching, and track status")
        sub.setObjectName("PageSubtitle")
        root.addWidget(header)
        root.addWidget(sub)

        # invite form
        form_card = QWidget()
        form_card.setObjectName("Card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setSpacing(10)

        form_title = QLabel("Invite a Candidate")
        form_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        form_layout.addWidget(form_title)

        self.job_combo = QComboBox()
        form_layout.addWidget(self.job_combo)

        row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Candidate name")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Candidate email")
        row.addWidget(self.name_input)
        row.addWidget(self.email_input)
        form_layout.addLayout(row)

        resume_row = QHBoxLayout()
        self.resume_path_lbl = QLabel("No resume attached (optional)")
        self.resume_path_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        self._pending_resume_path = None
        attach_btn = QPushButton("Attach Resume (PDF/DOCX)")
        attach_btn.setCursor(Qt.PointingHandCursor)
        attach_btn.clicked.connect(self._pick_resume_for_new_invite)
        resume_row.addWidget(self.resume_path_lbl, stretch=1)
        resume_row.addWidget(attach_btn)
        form_layout.addLayout(resume_row)

        invite_btn = QPushButton("Generate Invite")
        invite_btn.setObjectName("PrimaryButton")
        invite_btn.setCursor(Qt.PointingHandCursor)
        invite_btn.clicked.connect(self._invite_candidate)
        form_layout.addWidget(invite_btn)

        root.addWidget(form_card)

        # candidate list
        list_header = QLabel("Invited Candidates")
        list_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
        root.addWidget(list_header)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(self.list_scroll, stretch=1)

        self.refresh()

    def refresh(self):
        jobs = db.get_all_job_postings()
        self.job_combo.clear()
        if jobs:
            for job in jobs:
                self.job_combo.addItem(job["title"], job["job_id"])
        else:
            self.job_combo.addItem("Create a job posting first", None)

        candidates = db.get_all_candidates()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        if candidates:
            for c in candidates:
                layout.addWidget(CandidateRow(
                    c, self._copy_code, self._resend_invite, self._revoke_invite, self._attach_resume
                ))
        else:
            empty = QLabel("No candidates invited yet.")
            empty.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 40px;")
            empty.setAlignment(Qt.AlignCenter)
            empty.setObjectName("Card")
            layout.addWidget(empty)

        layout.addStretch()
        self.list_scroll.setWidget(container)

    def _pick_resume_for_new_invite(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select resume", "", "Resumes (*.pdf *.docx *.txt)")
        if path:
            self._pending_resume_path = path
            self.resume_path_lbl.setText(f"Attached: {os.path.basename(path)}")
            self.resume_path_lbl.setStyleSheet("font-size: 11px; color: #10B981; font-weight: 600;")

    def _invite_candidate(self):
        job_id = self.job_combo.currentData()
        if not job_id:
            QMessageBox.warning(self, "No job posting", "Create a job posting before inviting candidates.")
            return

        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        if not name or not email:
            QMessageBox.warning(self, "Missing info", "Enter both candidate name and email.")
            return

        candidate = Candidate(
            candidate_id=str(uuid.uuid4()),
            job_id=job_id,
            name=name,
            email=email,
            invite_code=generate_invite_code(),
            status="invited",
        )
        db.save_candidate(candidate)

        if self._pending_resume_path:
            self._process_resume(candidate.candidate_id, job_id, self._pending_resume_path)

        QMessageBox.information(
            self, "Invite created",
            f"Invite code for {name}: {candidate.invite_code}\n\n"
            f"Share this code with the candidate to start their interview."
        )
        self.name_input.clear()
        self.email_input.clear()
        self._pending_resume_path = None
        self.resume_path_lbl.setText("No resume attached (optional)")
        self.resume_path_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        self.refresh()

    def _attach_resume(self, candidate_id, job_id):
        path, _ = QFileDialog.getOpenFileName(self, "Select resume", "", "Resumes (*.pdf *.docx *.txt)")
        if not path:
            return
        self._process_resume(candidate_id, job_id, path)
        self.refresh()

    def _process_resume(self, candidate_id, job_id, source_path):
        try:
            RESUME_DIR.mkdir(parents=True, exist_ok=True)
            dest = RESUME_DIR / f"{candidate_id}{Path(source_path).suffix}"
            shutil.copy(source_path, dest)

            from app.engine.resume_parser import parse_resume
            from app.engine.jd_matcher import match_resume_to_jd

            resume_data = parse_resume(str(dest))

            jobs = {j["job_id"]: j for j in db.get_all_job_postings()}
            job = jobs.get(job_id)
            job_description = job["description"] if job else ""

            match = match_resume_to_jd(resume_data, job_description)

            db.save_candidate_resume(
                candidate_id=candidate_id,
                resume_path=str(dest),
                resume_skills=resume_data.get("skills", []),
                experience_years=resume_data.get("experience_years"),
                match_score=match.get("match_score"),
                matched_skills=match.get("matched_skills", []),
                missing_skills=match.get("missing_skills", []),
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Resume processing failed",
                f"Could not parse/match this resume:\n{e}\n\n"
                f"(Needs pdfplumber/python-docx installed for PDF/DOCX files.)"
            )

    def _copy_code(self, code):
        QApplication.clipboard().setText(code)

    def _resend_invite(self, candidate_id, name):
        new_code = generate_invite_code()
        db.regenerate_invite_code(candidate_id, new_code)
        QApplication.clipboard().setText(new_code)
        QMessageBox.information(
            self, "New invite code generated",
            f"New code for {name}: {new_code}\n\n(copied to clipboard, and status reset to 'invited')"
        )
        self.refresh()

    def _revoke_invite(self, candidate_id, name):
        reply = QMessageBox.question(
            self, "Revoke invite?",
            f"Revoke and delete {name}'s invite? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            db.delete_candidate(candidate_id)
            self.refresh()
