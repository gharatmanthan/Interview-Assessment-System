import subprocess
import socket
import serial.tools.list_ports
import os


def scan_ports(host="127.0.0.1", start_port=1, end_port=1024, timeout=0.08):
    """Return open TCP ports for an explicitly supplied host and range."""
    if not 1 <= start_port <= end_port <= 65535:
        raise ValueError("Port range must be between 1 and 65535.")

    open_ports = []
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex((host, port)) == 0:
                open_ports.append(port)
    return open_ports

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
            description = (port.description or "").lower()
            hwid = (port.hwid or "").lower()
            if "bluetooth" in description or "bthenum" in hwid:
                continue
            unauthorized_devices.append(f"Serial Device: {port.device} ({port.description})")
    except Exception as e:
        print(f"Error checking Serial ports: {e}")
        
    return unauthorized_devices