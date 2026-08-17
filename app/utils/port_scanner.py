import subprocess
import serial.tools.list_ports
import os

def get_unauthorized_devices():
    """
    Scans for USB storage drives and external hardware ports.
    Returns a list of detected device descriptions.
    """
    unauthorized_devices = []
    
    # 1. Detect USB Storage Drives using Windows WMI (Highly accurate)
    try:
        # Query Windows specifically for drives connected via a USB interface
        cmd = [
            'powershell', 
            '-NoProfile', 
            '-Command', 
            "Get-WmiObject Win32_DiskDrive | Where-Object { $_.InterfaceType -eq 'USB' } | Select-Object -ExpandProperty Model"
        ]
        
        # 0x08000000 is CREATE_NO_WINDOW on Windows. 
        # This prevents a black terminal window from flashing when the UI button is clicked.
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
        
        if result.stdout:
            # Read the output line by line and add detected devices
            devices = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            for device in devices:
                unauthorized_devices.append(f"USB Storage: {device}")
    except Exception as e:
        print(f"Error checking USB drives: {e}")
        
    # 2. Detect External Serial/Hardware Ports (e.g., Arduinos, Debuggers)
    try:
        ports = serial.tools.list_ports.comports()
        for port in ports:
            unauthorized_devices.append(f"Serial Device: {port.device} ({port.description})")
    except Exception as e:
        print(f"Error checking Serial ports: {e}")
        
    return unauthorized_devices