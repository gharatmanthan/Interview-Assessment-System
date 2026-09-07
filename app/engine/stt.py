"""
Owner: Member B

Speech-to-text via faster-whisper, running locally on CPU (the "base"
model, int8 quantized — fast enough for a laptop, no GPU required). This
keeps candidate audio on-device rather than sending it to a cloud API,
which is worth mentioning to your guide as a privacy-by-design choice.

Model resolution:
  * Packaged (InterviewIQ desktop): loads the bundled model from
    $INTERVIEWIQ_WHISPER_MODEL_DIR (set by Electron to the installer's
    resources/whisper/faster-whisper-base directory). No network access and
    no dependence on the developer's HuggingFace cache. A missing/malformed
    bundled model fails fast with an explicit, actionable error instead of
    silently trying to download.
  * Dev / tests: no env override -> faster-whisper uses its default
    HuggingFace cache (first run downloads ~75MB, then works offline).
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

from app.core.paths import get_whisper_model_dir

_model = None
_model_lock = threading.Lock()
# Thread pool for running transcription with timeout
_transcribe_executor = ThreadPoolExecutor(max_workers=1)
# Transcription timeout in seconds (adjust based on expected audio length)
_TRANSCRIBE_TIMEOUT_SECONDS = 60
# Max retries for transient failures
_MAX_TRANSCRIBE_RETRIES = 2


def _resolve_model_source() -> str:
    """Return the value passed to WhisperModel as `model_size_or_path`.

    Prefers the bundled model directory, else falls back to the default
    ("base" -> faster-whisper's download_root / HuggingFace cache).
    """
    bundled = get_whisper_model_dir()
    if bundled is not None:
        if not bundled.is_dir():
            raise FileNotFoundError(
                f"Bundled Whisper model directory not found: {bundled}. "
                "The InterviewIQ installation is incomplete or corrupted. "
                "Reinstall the application to restore the speech model."
            )
        required = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]
        missing = [name for name in required if not (bundled / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"Bundled Whisper model is incomplete at {bundled}; missing: "
                f"{', '.join(missing)}. Reinstall InterviewIQ to restore it."
            )
        return str(bundled)
    return "base"


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(
                _resolve_model_source(),
                device="cpu",
                compute_type="int8",
                local_files_only=get_whisper_model_dir() is not None,
            )
    return _model


def _transcribe_with_timeout(audio_path: str) -> str:
    """Run transcription in a thread pool with timeout."""
    model = _get_model()
    segments, _ = model.transcribe(audio_path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe(audio_path: str) -> str:
    """Must return: plain transcript text.
    
    Runs with timeout and retries on transient failures.
    """
    if not audio_path:
        return ""
    
    last_error = None
    for attempt in range(_MAX_TRANSCRIBE_RETRIES + 1):
        try:
            future = _transcribe_executor.submit(_transcribe_with_timeout, audio_path)
            return future.result(timeout=_TRANSCRIBE_TIMEOUT_SECONDS)
        except FuturesTimeoutError:
            last_error = f"Transcription timed out after {_TRANSCRIBE_TIMEOUT_SECONDS}s"
            # Cancel the future to free resources
            future.cancel()
        except Exception as e:
            last_error = f"Transcription failed: {e}"
        
        if attempt < _MAX_TRANSCRIBE_RETRIES:
            time.sleep(1 * (attempt + 1))  # Exponential backoff: 1s, 2s
    
    raise RuntimeError(f"Transcription failed after {_MAX_TRANSCRIBE_RETRIES + 1} attempts: {last_error}")