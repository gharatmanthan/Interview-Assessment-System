"""
Owner: Member C
Touches: this file only (registered into main_window.py)

Surfaces integrity_flags produced by app/candidate/integrity.py — port
scans, process checks, and (later) gaze/device CV detections.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt

from app.core import db

SEVERITY_COLORS = {
    "high": ("#FEE2E2", "#991B1B"),
    "medium": ("#FEF3C7", "#92400E"),
    "low": ("#F3F4F6", "#374151"),
}


class IntegrityFlagRow(QWidget):
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

        severity = flag.get("severity", "low")
        bg, fg = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["low"])
        badge = QLabel(severity.upper())
        badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 6px; "
            f"padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(badge)
        layout.addLayout(top)

        job = QLabel(f"{flag.get('job_title', '—')} · {flag.get('timestamp', '')}")
        job.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(job)

        detail = QLabel(f"{flag.get('flag_type', '')}: {flag.get('detail', '')}")
        detail.setWordWrap(True)
        detail.setStyleSheet("font-size: 12px; color: #1B1F2A; margin-top: 4px;")
        layout.addWidget(detail)


class IntegrityLogPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)

        header = QLabel("Integrity Log")
        header.setObjectName("PageTitle")
        sub = QLabel("Remote-access, VM, and device-integrity flags raised during interviews")
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
        flags = db.get_all_integrity_flags()

        if flags:
            high = sum(1 for f in flags if f.get("severity") == "high")
            self.summary_lbl.setText(f"{len(flags)} flag(s) total · {high} high-severity")
        else:
            self.summary_lbl.setText("No integrity flags raised yet — all clear.")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        if flags:
            for f in flags:
                layout.addWidget(IntegrityFlagRow(f))
        else:
            empty = QLabel(
                "No integrity flags yet.\n\nThis populates once app/candidate/integrity.py's "
                "run_checks() runs during a live interview."
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #9CA3AF; font-size: 13px; padding: 60px;")
            empty.setObjectName("Card")
            layout.addWidget(empty)

        layout.addStretch()
        self.scroll.setWidget(container)
