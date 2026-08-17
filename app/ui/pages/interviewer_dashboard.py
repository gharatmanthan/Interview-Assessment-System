from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from app.utils.port_scanner import get_unauthorized_devices

class InterviewerDashboard(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # Scan for unauthorized hardware ports and USBs
        devices = get_unauthorized_devices()
        
        if devices:
            # Join the devices with a newline character so they list vertically
            port_text = "Detected External Devices:\n" + "\n".join(f"• {device}" for device in devices)
        else:
            port_text = "No unauthorized external devices detected."
        
        # Display the result
        self.label = QLabel(f"Interviewer Control Panel\n\n{port_text}")
        layout.addWidget(self.label)