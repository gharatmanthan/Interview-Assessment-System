"""
Owner: Member C
Touches: this file only (registered into main_window.py)

Surfaces fairness_flags produced by app/engine/fairness.py's counterfactual
audit (Mujtaba & Mahapatra-style — score deltas across demographic variants
of the same answer).
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt

from app.core import db


class FairnessFlagRow(QWidget):
    def __init__(self, flag):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        top = QHBoxLayout()
        candidate = QLabel(flag.get("candidate_name") or "Unknown candidate")
        candidate.setStyleSheet("font-size: 13px; font-weight: 700;")
        top.addWidget(candidate)
        top.addStretch()

        delta = flag.get("score_delta", 0.0)
        badge = QLabel(f"Δ {delta:+.1f} pts")
        badge.setObjectName("Badge-flagged" if abs(delta) >= 5 else "Badge-clear")
        top.addWidget(badge)
        layout.addLayout(top)

        job = QLabel(f"{flag.get('job_title', '—')} · Question: {flag.get('question_id', '—')}")
        job.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(job)

        if flag.get("note"):
            note = QLabel(flag["note"])
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 12px; color: #1B1F2A; margin-top: 4px;")
            layout.addWidget(note)


class BiasAuditPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        header = QLabel("Bias Audit")
        header.setObjectName("PageTitle")
        sub = QLabel("Fairness metrics across candidate groups — counterfactual score deltas")
        sub.setObjectName("PageSubtitle")
        root.addWidget(header)
        root.addWidget(sub)

        self.summary_lbl = QLabel()
        self.summary_lbl.setObjectName("Card")
        self.summary_lbl.setStyleSheet("padding: 16px; font-size: 13px; font-weight: 600;")
        root.addWidget(self.summary_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(self.scroll, stretch=1)

        self.refresh()

    def refresh(self):
        flags = db.get_all_fairness_flags()

        if flags:
            avg_delta = sum(abs(f["score_delta"]) for f in flags) / len(flags)
            high_risk = sum(1 for f in flags if abs(f["score_delta"]) >= 5)
            self.summary_lbl.setText(
                f"{len(flags)} fairness check(s) run · avg |Δ| = {avg_delta:.1f} pts · "
                f"{high_risk} flagged as high-disparity (≥5 pts)"
            )
        else:
            self.summary_lbl.setText("No fairness audits run yet.")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        if flags:
            for f in flags:
                layout.addWidget(FairnessFlagRow(f))
        else:
            empty = QLabel(
                "No bias audit data yet.\n\nThis populates once app/engine/fairness.py "
                "runs its counterfactual audit on scored interviews."
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 60px;")
            empty.setObjectName("Card")
            layout.addWidget(empty)

        layout.addStretch()
        self.scroll.setWidget(container)
