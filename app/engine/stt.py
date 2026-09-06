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

from pathlib import Path

from app.core.paths import get_whisper_model_dir

_model = None


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
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            _resolve_model_source(),
            device="cpu",
            compute_type="int8",
            local_files_only=get_whisper_model_dir() is not None,
        )
    return _model


def transcribe(audio_path: str) -> str:
    """Must return: plain transcript text."""
    if not audio_path:
        return ""
    model = _get_model()
    segments, _ = model.transcribe(audio_path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()