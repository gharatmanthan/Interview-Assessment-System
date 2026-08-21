"""
Owner: Member C
Touches: this file only (registered into main_window.py)

Surfaces integrity_flags produced by app/candidate/integrity.py — port
scans, process checks, and (later) gaze/device CV detections. Also hosts
the on-demand environment scanner (TCP ports + USB/serial devices)
integrated from the teammate's interviewer dashboard.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QLineEdit,
    QPushButton, QSpinBox, QTextEdit,
)
from PySide6.QtCore import Qt, QObject, QThread, Signal

from app.core import db
from app.utils.port_scanner import scan_ports, get_unauthorized_devices

SEVERITY_COLORS = {
    "high": ("#FEE2E2", "#991B1B"),
    "medium": ("#FEF3C7", "#92400E"),
    "low": ("#F3F4F6", "#374151"),
}


class PortScanWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, host, start_port, end_port):
        super().__init__()
        self.host = host
        self.start_port = start_port
        self.end_port = end_port

    def run(self):
        try:
            self.finished.emit(scan_ports(self.host, self.start_port, self.end_port))
        except (OSError, ValueError) as error:
            self.failed.emit(str(error))


class EnvironmentScanCard(QWidget):
    """On-demand TCP port scan (background thread) and USB/serial device check."""
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.scan_thread = None
        self.scan_worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        heading = QLabel("Environment Scanner")
        heading.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(heading)

        form = QHBoxLayout()
        form.addWidget(QLabel("Host"))
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setMaximumWidth(140)
        form.addWidget(self.host_input)
        form.addWidget(QLabel("Ports"))
        self.start_port = QSpinBox()
        self.start_port.setRange(1, 65535)
        self.start_port.setValue(1)
        self.end_port = QSpinBox()
        self.end_port.setRange(1, 65535)
        self.end_port.setValue(1024)
        form.addWidget(self.start_port)
        form.addWidget(QLabel("to"))
        form.addWidget(self.end_port)
        form.addStretch()

        self.scan_btn = QPushButton("Scan TCP Ports")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.clicked.connect(self._start_scan)
        form.addWidget(self.scan_btn)

        self.usb_btn = QPushButton("Check USB / Serial Devices")
        self.usb_btn.setObjectName("SecondaryButton")
        self.usb_btn.clicked.connect(self._check_devices)
        form.addWidget(self.usb_btn)
        layout.addLayout(form)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMaximumHeight(120)
        self.result.setPlaceholderText("Scan results will appear here.")
        layout.addWidget(self.result)

    def _start_scan(self):
        host = self.host_input.text().strip()
        if not host:
            self.result.setPlainText("Scan failed: enter a host or IP address.")
            return
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return
        self.result.setPlainText("Scanning... the page stays responsive.")
        self.scan_thread = QThread(self)
        self.scan_worker = PortScanWorker(host, self.start_port.value(), self.end_port.value())
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self._show_results)
        self.scan_worker.failed.connect(self._show_error)
        self.scan_worker.finished.connect(self._finish_scan)
        self.scan_worker.failed.connect(self._finish_scan)
        self.scan_thread.start()

    def _show_results(self, ports):
        if ports:
            self.result.setPlainText(
                f"Open TCP ports on {self.host_input.text().strip()}:\n"
                + ", ".join(str(p) for p in ports)
            )
        else:
            self.result.setPlainText("No open TCP ports found in the selected range.")

    def _show_error(self, message):
        self.result.setPlainText(f"Scan failed: {message}")

    def _finish_scan(self, *_):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait()
        if self.scan_worker is not None:
            self.scan_worker.deleteLater()
        if self.scan_thread is not None:
            self.scan_thread.deleteLater()
        self.scan_worker = None
        self.scan_thread = None

    def _check_devices(self):
        devices = get_unauthorized_devices()
        if devices:
            self.result.setPlainText(
                "Connected USB/serial devices:\n" + "\n".join(f"- {d}" for d in devices)
            )
        else:
            self.result.setPlainText("No USB storage or serial devices detected.")

    def cleanup(self):
        self._finish_scan()


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

        self.scan_card = EnvironmentScanCard()
        root.addWidget(self.scan_card)

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

    def cleanup(self):
        self.scan_card.cleanup()
