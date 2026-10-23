"""
Owner: Member C
Touches: this file, app/ui/pages/settings_page.py

Simple JSON-backed app settings — camera/mic device selection, LLM
provider config, export preferences. Deliberately not in the SQLite DB
since this is app-level config, not interview data.
"""
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "settings.json"

DEFAULTS = {
    "camera_index": 0,
    "mic_device": "default",
    "llm_provider": "Groq",
    "llm_api_key": "",
    "export_dir": str(Path.home() / "Documents"),
    "backend_mode": "local",
    "lan_api_url": "",
}


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        # Do not carry forward the old cloud/remote setting into the desktop
        # LAN architecture.
        if merged.get("backend_mode") == "remote":
            merged["backend_mode"] = "local"
        if not merged.get("lan_api_url"):
            merged["lan_api_url"] = ""
        merged.pop("remote_api_url", None)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = load_settings()
    merged.update(settings)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(merged, f, indent=2)
    return merged
