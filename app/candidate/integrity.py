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


# Cross-platform suspicious process patterns (lowercase, matched against process name)
SUSPICIOUS_PROCESSES = {
    # Remote desktop (cross-platform)
    "teamviewer": "TeamViewer remote desktop detected",
    "anydesk": "AnyDesk remote desktop detected",
    "ammyy": "Ammyy Admin remote desktop detected",
    "splashtop": "Splashtop remote desktop detected",
    "chrome_remote_desktop": "Chrome Remote Desktop detected",
    "parallels": "Parallels Access detected",
    "rdp": "RDP client detected",
    "vnc": "VNC client detected",
    "tightvnc": "TightVNC detected",
    "realvnc": "RealVNC detected",
    # Virtual machines
    "vmware": "VMware virtual machine detected",
    "vmware-vmx": "VMware VM process detected",
    "virtualbox": "VirtualBox detected",
    "vboxsvc": "VirtualBox service detected",
    "qemu": "QEMU virtual machine detected",
    # Scripting/automation
    "autohotkey": "AutoHotkey automation detected",
    "pyautogui": "PyAutoGUI automation detected",
    "xautomation": "XAutomation detected",
    "xdotool": "xdotool automation detected",
}


def process_scan() -> list[dict]:
    """Scan running processes for suspicious software."""
    findings = []
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info["name"].lower()
                for pattern, detail in SUSPICIOUS_PROCESSES.items():
                    if pattern in name:
                        findings.append({
                            "flag_type": "suspicious_process",
                            "detail": detail,
                            "severity": "high",
                            "pid": proc.info["pid"],
                            "process_name": proc.info["name"],
                        })
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        pass
    return findings


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


# In-memory deduplication cache for server-side run_checks
# Key: (session_id, flag_type, detail) -> timestamp
_seen_integrity_flags: dict[tuple[str, str, str], float] = {}
_SEEN_FLAG_TTL = 300  # 5 minutes


def run_checks(session_id: str) -> list:
    """Combine all integrity signals into IntegrityFlag objects.
    Must return: list[IntegrityFlag] — this is what app/core/db.save_integrity_flag()
    and the Integrity Log page (Member C) expect.
    
    Deduplicates flags within a TTL window to prevent the 5s polling from
    generating the same flags repeatedly.
    """
    import time
    now = time.time()
    flags = []
    
    # Clean expired entries
    expired_keys = [k for k, ts in _seen_integrity_flags.items() if now - ts > _SEEN_FLAG_TTL]
    for k in expired_keys:
        del _seen_integrity_flags[k]
    
    for port, tool in port_scan():
        key = (session_id, "remote_access_port", f"{tool} port {port} is open")
        if key in _seen_integrity_flags:
            continue
        _seen_integrity_flags[key] = now
        flags.append(
            IntegrityFlag(
                session_id=session_id,
                flag_type="remote_access_port",
                detail=f"{tool} port {port} is open",
                severity="high",
            )
        )
    for finding in process_scan():
        key = (session_id, finding["flag_type"], finding["detail"])
        if key in _seen_integrity_flags:
            continue
        _seen_integrity_flags[key] = now
        flags.append(
            IntegrityFlag(
                session_id=session_id,
                flag_type=finding["flag_type"],
                detail=finding["detail"],
                severity=finding["severity"],
            )
        )
    # TODO: append CV-based flags here too
    return flags
