from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QApplication
from PySide6.QtCore import Qt, Signal
from app.utils.port_scanner import get_unauthorized_devices

class CandidateDashboard(QWidget):
    # 1. Create a custom signal to communicate with the main window
    start_interview_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter) 
        
        self.label = QLabel("Candidate Dashboard\n\nWelcome to your interview assessment.")
        self.label.setAlignment(Qt.AlignCenter)
        
        self.instructions = QLabel("Checking system environment for unauthorized devices...")
        self.instructions.setAlignment(Qt.AlignCenter)
        
        self.device_status = QLabel("")
        self.device_status.setAlignment(Qt.AlignCenter)
        
        self.refresh_button = QPushButton("Re-scan System")
        self.refresh_button.setFixedSize(200, 35)
        self.refresh_button.clicked.connect(self.check_environment)
        
        self.start_button = QPushButton("Start Interview")
        self.start_button.setFixedSize(200, 45) 
        self.start_button.setEnabled(False)
        
        # 2. Connect the start button to our custom signal
        self.start_button.clicked.connect(self.start_interview_requested.emit)
        
        layout.addWidget(self.label)
        layout.addSpacing(10)
        layout.addWidget(self.instructions)
        layout.addWidget(self.device_status)
        layout.addSpacing(20)
        layout.addWidget(self.refresh_button, alignment=Qt.AlignCenter)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)

        self.check_environment()

    def check_environment(self):
        # 3. Add visual feedback so you know the button was clicked
        self.instructions.setText("Scanning system... Please wait.")
        self.instructions.setStyleSheet("color: #f39c12; font-weight: bold;") # Orange text
        self.device_status.setText("")
        
        # Force the UI to update the text immediately before running the scan
        QApplication.processEvents() 
        
        devices = get_unauthorized_devices()
        
        if devices:
            self.instructions.setText("SECURITY ALERT: External devices detected.\nPlease detach all USB drives and external hardware to continue.")
            self.instructions.setStyleSheet("color: #e74c3c; font-weight: bold;") # Red text
            
            devices_text = "\n".join(f"• {device}" for device in devices)
            self.device_status.setText(f"Please remove:\n{devices_text}")
            
            self.start_button.setEnabled(False)
        else:
            self.instructions.setText("System check passed. No external devices detected.")
            self.instructions.setStyleSheet("color: #2ecc71; font-weight: bold;") # Green text
            
            self.device_status.setText("")
            
            self.start_button.setEnabled(True)