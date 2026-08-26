from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget

from app.utils.port_scanner import scan_ports


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


class InterviewerDashboard(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(16)

        title = QLabel("Interviewer Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Review interview readiness and scan an explicitly selected host")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.host_input = QLineEdit("127.0.0.1")
        self.start_port = QSpinBox()
        self.start_port.setRange(1, 65535)
        self.start_port.setValue(1)
        self.end_port = QSpinBox()
        self.end_port.setRange(1, 65535)
        self.end_port.setValue(1024)
        form.addRow("Host", self.host_input)
        form.addRow("Start port", self.start_port)
        form.addRow("End port", self.end_port)
        layout.addLayout(form)

        actions = QHBoxLayout()
        scan_button = QPushButton("Scan TCP Ports")
        scan_button.setObjectName("PrimaryButton")
        scan_button.clicked.connect(self.scan)
        actions.addWidget(scan_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("Scan results will appear here.")
        layout.addWidget(self.result, stretch=1)
        self.scan_thread = None
        self.scan_worker = None

    def scan(self):
        host = self.host_input.text().strip()
        if not host:
            self.result.setPlainText("Scan failed: enter a host or IP address.")
            return
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return

        self.result.setPlainText("Scanning... The dashboard remains responsive.")
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
            self.result.setPlainText("Open TCP ports:\n" + "\n".join(str(port) for port in ports))
        else:
            self.result.setPlainText("No open TCP ports found in the selected range.")

    def _show_error(self, message):
        self.result.setPlainText(f"Scan failed: {message}")

    def _finish_scan(self, *_):
        self.scan_thread.quit()
        self.scan_thread.wait()
        self.scan_worker.deleteLater()
        self.scan_thread.deleteLater()
        self.scan_worker = None
        self.scan_thread = None

    def cleanup(self):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait()
