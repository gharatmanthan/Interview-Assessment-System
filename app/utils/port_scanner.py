import serial.tools.list_ports
import psutil


def get_unauthorized_devices():
    """
    Scans for USB storage drives and external serial hardware.
    Returns a list of detected device descriptions.

    Uses psutil + pyserial so the whole scan completes in milliseconds
    (the old WMI/subprocess approach took seconds and froze the UI).
    Bluetooth virtual COM ports are built into most laptops and are not
    removable hardware, so they are ignored to avoid false alarms.
    """
    unauthorized_devices = []

    # 1. Detect removable / USB storage drives
    try:
        for part in psutil.disk_partitions(all=False):
            opts = (part.opts or "").lower()
            if "removable" in opts:
                unauthorized_devices.append(f"USB Storage: {part.device} ({part.fstype})")
    except Exception as e:
        print(f"Error checking USB drives: {e}")

    # 2. Detect External Serial/Hardware Ports (e.g., Arduinos, Debuggers)
    try:
        for port in serial.tools.list_ports.comports():
            if "bluetooth" in (port.description or "").lower():
                continue
            unauthorized_devices.append(f"Serial Device: {port.device} ({port.description})")
    except Exception as e:
        print(f"Error checking Serial ports: {e}")

    return unauthorized_devices


def scan_ports(host="127.0.0.1", start_port=1, end_port=1024, timeout=0.08):
    """Return open TCP ports for an explicitly supplied host and range."""
    import socket

    if not 1 <= start_port <= end_port <= 65535:
        raise ValueError("Port range must be between 1 and 65535.")

    open_ports = []
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex((host, port)) == 0:
                open_ports.append(port)
    return open_ports
