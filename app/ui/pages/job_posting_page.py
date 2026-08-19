"""
Owner: Member C
Touches: this file only (registered into main_window.py + sidebar.py)

Recruiter-facing form to create/edit a job posting, plus a list of
existing postings with edit/delete actions. Saving writes a JobPosting
into the shared DB — Member B's rag.py and a future question_selector.py
will read it to ground question generation and scoring against the role.
"""
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QCheckBox, QPushButton, QScrollArea, QSlider,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal

from app.core import db
from app.core.models import JobPosting

EXPERIENCE_LEVELS = ["Fresher", "Junior", "Mid", "Senior"]
DEPARTMENTS = ["Software / CS", "Data / ML", "Electronics", "Mechanical", "Civil", "Other"]
COMPETENCY_CATEGORIES = ["DSA", "System Design", "Communication", "Domain Knowledge", "Problem Solving"]


class WeightSlider(QWidget):
    """One labeled 0-100 slider for a competency category's weight."""
    changed = Signal()

    def __init__(self, label):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        name = QLabel(label)
        name.setFixedWidth(140)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(100 // len(COMPETENCY_CATEGORIES))

        self.value_lbl = QLabel(f"{self.slider.value()}%")
        self.value_lbl.setFixedWidth(40)

        self.slider.valueChanged.connect(self._on_change)

        layout.addWidget(name)
        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.value_lbl)

    def _on_change(self, val):
        self.value_lbl.setText(f"{val}%")
        self.changed.emit()

    def value(self):
        return self.slider.value()

    def set_value(self, val):
        self.slider.setValue(val)


class JobPostingRow(QWidget):
    def __init__(self, job, on_edit, on_delete):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        title = QLabel(job["title"])
        title.setStyleSheet("font-size: 13px; font-weight: 700;")
        top.addWidget(title)
        top.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setFlat(True)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: on_edit(job["job_id"]))
        top.addWidget(edit_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setFlat(True)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet("color: #EF4444;")
        delete_btn.clicked.connect(lambda: on_delete(job["job_id"], job["title"]))
        top.addWidget(delete_btn)
        layout.addLayout(top)

        skills = ", ".join(job["required_skills"]) if job["required_skills"] else "—"
        meta = QLabel(f"{job['experience_level']} · {job['department']} · Skills: {skills}")
        meta.setStyleSheet("font-size: 11px; color: #6B7280;")
        meta.setWordWrap(True)
        layout.addWidget(meta)


class JobPostingPage(QWidget):
    def __init__(self):
        super().__init__()
        self.editing_job_id = None

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        self.header = QLabel("Create Job Posting")
        self.header.setObjectName("PageTitle")
        self.sub = QLabel("Defines the role, required skills, and competency rubric candidates are scored against")
        self.sub.setObjectName("PageSubtitle")
        root.addWidget(self.header)
        root.addWidget(self.sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        form_container = QWidget()
        form = QVBoxLayout(form_container)
        form.setSpacing(18)

        form.addWidget(self._section_label("Basic Information"))

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g. Backend Engineer")
        form.addWidget(self._field("Job Title", self.title_input))

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText(
            "Paste or write the full job description here — this grounds the "
            "RAG retrieval used to generate and score interview questions."
        )
        self.desc_input.setMinimumHeight(120)
        form.addWidget(self._field("Job Description", self.desc_input))

        self.skills_input = QLineEdit()
        self.skills_input.setPlaceholderText("Comma-separated, e.g. Python, SQL, System Design, REST APIs")
        form.addWidget(self._field("Required Skills", self.skills_input))

        row = QHBoxLayout()
        self.experience_combo = QComboBox()
        self.experience_combo.addItems(EXPERIENCE_LEVELS)
        row.addWidget(self._field("Experience Level", self.experience_combo))

        self.department_combo = QComboBox()
        self.department_combo.addItems(DEPARTMENTS)
        row.addWidget(self._field("Department", self.department_combo))
        form.addLayout(row)

        form.addWidget(self._section_label("Interview Parameters"))

        row2 = QHBoxLayout()
        self.rounds_input = QSpinBox()
        self.rounds_input.setRange(1, 5)
        self.rounds_input.setValue(1)
        row2.addWidget(self._field("Number of Rounds", self.rounds_input))

        self.time_limit_input = QSpinBox()
        self.time_limit_input.setRange(30, 600)
        self.time_limit_input.setSingleStep(15)
        self.time_limit_input.setValue(120)
        self.time_limit_input.setSuffix(" sec")
        row2.addWidget(self._field("Time Limit per Question", self.time_limit_input))
        form.addLayout(row2)

        self.adaptive_checkbox = QCheckBox(
            "Adaptive difficulty — question difficulty increases as the candidate answers well, "
            "decreases if they struggle"
        )
        self.adaptive_checkbox.setChecked(True)
        form.addWidget(self.adaptive_checkbox)

        form.addWidget(self._section_label("Competency Weightage"))
        weight_hint = QLabel("How much each category should count toward the final score. Should total 100%.")
        weight_hint.setObjectName("PageSubtitle")
        form.addWidget(weight_hint)

        self.weight_sliders = {}
        for cat in COMPETENCY_CATEGORIES:
            ws = WeightSlider(cat)
            ws.changed.connect(self._update_weight_total)
            self.weight_sliders[cat] = ws
            form.addWidget(ws)

        self.weight_total_lbl = QLabel()
        self.weight_total_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        form.addWidget(self.weight_total_lbl)
        self._update_weight_total()

        btn_row = QHBoxLayout()
        self.submit_btn = QPushButton("Create Job Posting")
        self.submit_btn.setObjectName("PrimaryButton")
        self.submit_btn.setCursor(Qt.PointingHandCursor)
        self.submit_btn.clicked.connect(self._submit)
        btn_row.addWidget(self.submit_btn)

        self.cancel_edit_btn = QPushButton("Cancel Edit")
        self.cancel_edit_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        self.cancel_edit_btn.hide()
        btn_row.addWidget(self.cancel_edit_btn)
        form.addLayout(btn_row)

        form.addWidget(self._section_label("Existing Job Postings"))
        self.postings_container = QVBoxLayout()
        form.addLayout(self.postings_container)

        form.addStretch()
        scroll.setWidget(form_container)
        root.addWidget(scroll, stretch=1)

        self.refresh()

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
        return lbl

    def _field(self, label_text, widget):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280;")
        layout.addWidget(lbl)
        layout.addWidget(widget)
        return wrapper

    def _update_weight_total(self):
        total = sum(ws.value() for ws in self.weight_sliders.values())
        color = "#10B981" if total == 100 else "#EF4444"
        self.weight_total_lbl.setText(f"Total: {total}%  {'✓' if total == 100 else '(should be 100%)'}")
        self.weight_total_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color};")

    def refresh(self):
        while self.postings_container.count():
            item = self.postings_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        jobs = db.get_all_job_postings()
        if jobs:
            for job in jobs:
                self.postings_container.addWidget(
                    JobPostingRow(job, self._start_edit, self._confirm_delete)
                )
        else:
            empty = QLabel("No job postings yet — create one above.")
            empty.setStyleSheet("color: #9CA3AF; font-size: 12px; padding: 12px;")
            self.postings_container.addWidget(empty)

    def _start_edit(self, job_id):
        jobs = {j["job_id"]: j for j in db.get_all_job_postings()}
        job = jobs.get(job_id)
        if not job:
            return

        self.editing_job_id = job_id
        self.header.setText("Edit Job Posting")
        self.sub.setText(f"Editing '{job['title']}'")
        self.submit_btn.setText("Update Job Posting")
        self.cancel_edit_btn.show()

        self.title_input.setText(job["title"])
        self.desc_input.setPlainText(job["description"])
        self.skills_input.setText(", ".join(job["required_skills"]))
        idx = self.experience_combo.findText(job["experience_level"])
        if idx >= 0:
            self.experience_combo.setCurrentIndex(idx)
        idx = self.department_combo.findText(job["department"])
        if idx >= 0:
            self.department_combo.setCurrentIndex(idx)
        self.rounds_input.setValue(job["num_rounds"])
        self.time_limit_input.setValue(job["time_limit_seconds"])
        self.adaptive_checkbox.setChecked(job["adaptive_difficulty"])
        for cat, ws in self.weight_sliders.items():
            ws.set_value(job["competency_weights"].get(cat, 0))

    def _cancel_edit(self):
        self.editing_job_id = None
        self.header.setText("Create Job Posting")
        self.sub.setText("Defines the role, required skills, and competency rubric candidates are scored against")
        self.submit_btn.setText("Create Job Posting")
        self.cancel_edit_btn.hide()
        self._reset_form()

    def _confirm_delete(self, job_id, title):
        reply = QMessageBox.question(
            self, "Delete job posting?",
            f"Delete '{title}'? This cannot be undone. Candidates already invited to it will keep their records.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            db.delete_job_posting(job_id)
            if self.editing_job_id == job_id:
                self._cancel_edit()
            self.refresh()

    def _submit(self):
        if not self.title_input.text().strip():
            QMessageBox.warning(self, "Missing field", "Job title is required.")
            return
        if not self.desc_input.toPlainText().strip():
            QMessageBox.warning(self, "Missing field", "Job description is required.")
            return

        skills = [s.strip() for s in self.skills_input.text().split(",") if s.strip()]
        weights = {cat: ws.value() for cat, ws in self.weight_sliders.items()}

        job = JobPosting(
            job_id=self.editing_job_id or str(uuid.uuid4()),
            title=self.title_input.text().strip(),
            description=self.desc_input.toPlainText().strip(),
            required_skills=skills,
            experience_level=self.experience_combo.currentText(),
            department=self.department_combo.currentText(),
            num_rounds=self.rounds_input.value(),
            time_limit_seconds=self.time_limit_input.value(),
            adaptive_difficulty=self.adaptive_checkbox.isChecked(),
            competency_weights=weights,
        )
        db.save_job_posting(job)

        was_editing = self.editing_job_id is not None
        QMessageBox.information(
            self, "Job posting updated" if was_editing else "Job posting created",
            f"'{job.title}' has been {'updated' if was_editing else 'created'}."
        )
        self._cancel_edit()
        self.refresh()

    def _reset_form(self):
        self.title_input.clear()
        self.desc_input.clear()
        self.skills_input.clear()
        self.experience_combo.setCurrentIndex(0)
        self.department_combo.setCurrentIndex(0)
        self.rounds_input.setValue(1)
        self.time_limit_input.setValue(120)
        self.adaptive_checkbox.setChecked(True)
        for ws in self.weight_sliders.values():
            ws.set_value(100 // len(COMPETENCY_CATEGORIES))
