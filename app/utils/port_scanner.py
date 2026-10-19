import subprocess
import socket
import serial.tools.list_ports
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceObservation:
    kind: str
    name: str
    detail: str
    severity: str
    confidence: float


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

def scan_external_devices() -> list[DeviceObservation]:
    """Return external-device observations after applying safe local allowlists."""
    observations = []

    try:
        cmd = [
            "powershell",
            '-NoProfile', 
            '-Command', 
            "Get-WmiObject Win32_DiskDrive | Where-Object { $_.InterfaceType -eq 'USB' } | Select-Object -ExpandProperty Model"
        ]
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        result = subprocess.run(
            cmd, capture_output=True, text=True, creationflags=creation_flags,
            check=False, timeout=5,
        )
        if result.stdout:
            devices = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            for device in devices:
                observations.append(DeviceObservation(
                    kind="usb_storage",
                    name=device,
                    detail=f"USB storage device detected: {device}",
                    severity="high",
                    confidence=0.98,
                ))
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        ports = serial.tools.list_ports.comports()
        for port in ports:
            description = (port.description or "").lower()
            hwid = (port.hwid or "").lower()
            if "bluetooth" in description or "bthenum" in hwid:
                continue
            display_name = port.description or "Unknown serial device"
            allowlisted = os.getenv("INTERVIEWIQ_ALLOWED_SERIAL", "")
            allowed_markers = {
                marker.strip().lower()
                for marker in allowlisted.split(",")
                if marker.strip()
            }
            if any(marker in f"{port.device} {description} {hwid}" for marker in allowed_markers):
                continue
            observations.append(DeviceObservation(
                kind="serial_device",
                name=display_name,
                detail=f"External serial device detected on {port.device}: {display_name}",
                severity="medium",
                confidence=0.9,
            ))
    except (OSError, serial.SerialException):
        pass

    return observations


def get_unauthorized_devices() -> list[str]:
    """Backward-compatible display strings for the candidate setup screen."""
    return [observation.detail for observation in scan_external_devices()]