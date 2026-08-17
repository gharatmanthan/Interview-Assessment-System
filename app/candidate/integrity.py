"""
Owner: Member A
Touches: this file only

Runs locally on the candidate's machine during the interview (this is a
native desktop app, so no browser-sandbox limitation — direct socket
and process checks are fine here, unlike a web-based client).

TODO (Member A):
- port_scan(): check localhost for known remote-access ports
- process_scan(): check running processes for remote-access tools
- run_checks(): combine both + any CV-based checks (gaze, extra person,
  phone detection via mediapipe/OpenCV) into a list of IntegrityFlag
"""
import socket
import json
import platform
import subprocess

from app.core.models import IntegrityFlag

REMOTE_ACCESS_PORTS = {
    3389: "RDP",
    5900: "VNC",
    5938: "TeamViewer",
    7070: "AnyDesk",
}

MONITORED_DEVICE_CLASSES = {
    "AudioEndpoint",
    "Bluetooth",
    "Camera",
    "DiskDrive",
    "HIDClass",
    "Image",
    "Keyboard",
    "Media",
    "Modem",
    "Mouse",
    "Net",
    "Ports",
    "SmartCardReader",
    "USB",
    "WPD",
}


def port_scan(timeout=0.3) -> list:
    """Returns list of (port, tool_name) for anything listening locally."""
    found = []
    for port, name in REMOTE_ACCESS_PORTS.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if result == 0:
            found.append((port, name))
    return found


def process_scan() -> list:
    """TODO: use psutil to check for teamviewer.exe, anydesk.exe, vncserver, etc.
    (add psutil to requirements.txt when you start this)
    """
    raise NotImplementedError


def _run_powershell_device_query(timeout=4) -> list:
    """Return present Windows PnP devices as dictionaries."""
    classes = ",".join(f"'{item}'" for item in sorted(MONITORED_DEVICE_CLASSES))
    script = (
        "$classes = @(" + classes + "); "
        "Get-PnpDevice -PresentOnly | "
        "Where-Object { $classes -contains $_.Class } | "
        "Select-Object Class,FriendlyName,InstanceId | "
        "ConvertTo-Json -Compress"
    )
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def list_connected_devices() -> list:
    """List currently attached external-ish devices that are visible to the OS."""
    devices = []

    if platform.system() == "Windows":
        for item in _run_powershell_device_query():
            instance_id = item.get("InstanceId")
            if not instance_id:
                continue
            devices.append(
                {
                    "id": f"pnp:{instance_id}",
                    "name": item.get("FriendlyName") or "Unknown device",
                    "device_class": item.get("Class") or "Unknown",
                }
            )

    devices.extend(_list_storage_devices())
    devices.extend(_list_audio_devices())
    return _dedupe_devices(devices)


def _list_storage_devices() -> list:
    try:
        import psutil
    except ImportError:
        return []

    devices = []
    for partition in psutil.disk_partitions(all=False):
        opts = (partition.opts or "").lower()
        is_removable = "removable" in opts or "cdrom" in opts
        if not is_removable:
            continue
        device_id = partition.device or partition.mountpoint
        devices.append(
            {
                "id": f"storage:{device_id}",
                "name": partition.mountpoint or partition.device or "Removable storage",
                "device_class": "RemovableStorage",
            }
        )
    return devices


def _list_audio_devices() -> list:
    try:
        import sounddevice as sd
    except (ImportError, OSError):
        return []

    try:
        audio_devices = sd.query_devices()
    except Exception:
        return []

    devices = []
    for index, device in enumerate(audio_devices):
        input_channels = device.get("max_input_channels", 0)
        output_channels = device.get("max_output_channels", 0)
        if input_channels <= 0 and output_channels <= 0:
            continue
        name = device.get("name") or f"Audio device {index}"
        hostapi = device.get("hostapi", "unknown")
        devices.append(
            {
                "id": f"audio:{hostapi}:{name}:{input_channels}:{output_channels}",
                "name": name,
                "device_class": "Audio",
            }
        )
    return devices


def _dedupe_devices(devices: list) -> list:
    unique = []
    seen = set()
    for device in devices:
        device_id = device["id"]
        if device_id in seen:
            continue
        unique.append(device)
        seen.add(device_id)
    return unique


class ExternalDeviceMonitor:
    """Tracks devices added after interview monitoring begins."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._known_ids = set()
        self.is_supported = True

    def start(self):
        """Capture the baseline so only newly connected devices are flagged."""
        self._known_ids = {device["id"] for device in list_connected_devices()}

    def poll(self) -> list:
        if not self.is_supported:
            return []

        current_devices = list_connected_devices()
        current_ids = {device["id"] for device in current_devices}
        new_devices = [device for device in current_devices if device["id"] not in self._known_ids]
        self._known_ids = current_ids

        if not new_devices:
            return []

        detail = _format_device_event(new_devices)
        return [
            IntegrityFlag(
                session_id=self.session_id,
                flag_type="external_device_connected",
                detail=detail,
                severity="high",
            )
        ]


def _format_device_event(devices: list) -> str:
    labels = []
    seen = set()
    for device in devices:
        label = f"{device['name']} ({device['device_class']})"
        if label not in seen:
            labels.append(label)
            seen.add(label)

    if len(labels) == 1:
        return f"New external device detected during interview: {labels[0]}"
    return "New external devices detected during interview: " + "; ".join(labels)


def run_checks(session_id: str) -> list:
    """Combine all integrity signals into IntegrityFlag objects.
    Must return: list[IntegrityFlag] — this is what app/core/db.save_integrity_flag()
    and the Integrity Log page (Member C) expect.
    """
    flags = []
    for port, tool in port_scan():
        flags.append(
            IntegrityFlag(
                session_id=session_id,
                flag_type="remote_access_port",
                detail=f"{tool} port {port} is open",
                severity="high",
            )
        )
    # TODO: append process_scan() results and CV-based flags here too
    return flags
