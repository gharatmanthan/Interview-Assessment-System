"""
Central filesystem-path resolution for InterviewIQ.

Single source of truth for where the application reads/writes data, so
dev mode (repo `data/`) and packaged Electron mode (a per-user writable
app-data directory under %APPDATA%/InterviewIQ) resolve consistently across
the Python backend AND the Electron main process.

Two inputs:
  * $INTERVIEWIQ_DATA_DIR  — Electron sets this to app.getPath("userData")
                             in packaged mode. Points at the ONE writable,
                             per-user data root (app.db, recordings, uploads,
                             resumes, live_frames, face_profiles, settings).
                             Dev/tests leave it unset and fall back to the
                             repo `data/` directory.
  * $INTERVIEWIQ_WHISPER_MODEL_DIR — Electron sets this to the bundled
                             Whisper model directory in packaged mode. When
                             unset, faster-whisper's default HuggingFace
                             cache is used (dev behavior).

Never assume cwd, and never resolve the repo-root via path traversal that
would break once app/ and api/ live under process.resourcesPath.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_app_data_dir() -> Path:
    """The authoritative writable data root (one per install).

    - Packaged: $INTERVIEWIQ_DATA_DIR (set by Electron to userData).
    - Dev/tests: the repository's `data/` directory.
    """
    override = os.environ.get("INTERVIEWIQ_DATA_DIR", "").strip()
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return PROJECT_ROOT / "data"


def get_settings_path() -> Path:
    """settings.json lives at the app-data root next to app.db."""
    return get_app_data_dir() / "settings.json"


def get_db_path() -> Path:
    """The single authoritative SQLite database."""
    return get_app_data_dir() / "app.db"


def get_recordings_dir() -> Path:
    return get_app_data_dir() / "recordings"


def get_resumes_dir() -> Path:
    return get_app_data_dir() / "resumes"


def get_uploads_dir() -> Path:
    return get_app_data_dir() / "uploads"


def get_live_frames_dir() -> Path:
    return get_app_data_dir() / "live_frames"


def get_face_profiles_dir() -> Path:
    return get_app_data_dir() / "face_profiles"


def get_models_dir() -> Path:
    return get_app_data_dir() / "models"


def get_client_secret_path() -> Path:
    """OAuth client config. NOT bundled; in packaged mode it is a user/enterprise
    provided file placed in the app-data directory. If absent, integrations
    report a clear, actionable error instead of crashing."""
    return get_app_data_dir() / "client_secret.json"


def get_whisper_model_dir() -> Path | None:
    """Directory faster-whisper should load the bundled model from.

    - Packaged: $INTERVIEWIQ_WHISPER_MODEL_DIR (set by Electron to the
      bundled resources/whisper/faster-whisper-base directory).
    - Dev: unset -> None, meaning faster-whisper uses its default
      HuggingFace cache/download_root behaviour.
    """
    override = os.environ.get("INTERVIEWIQ_WHISPER_MODEL_DIR", "").strip()
    if override:
        return Path(override)
    return None


def get_env_file_path() -> Path:
    """User-provided secrets/config `.env` in the app-data dir.

    Bundled as an empty/template on install but the OPERATOR provides real
    values here (never in the installer). python-dotenv is configured to NOT
    override existing environment variables, so a real OS env var wins.
    """
    return get_app_data_dir() / ".env"
