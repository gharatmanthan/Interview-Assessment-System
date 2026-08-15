"""
Owner: Member B

Speech-to-text via faster-whisper, running locally on CPU (the "base"
model, int8 quantized — fast enough for a laptop, no GPU required). This
keeps candidate audio on-device rather than sending it to a cloud API,
which is worth mentioning to your guide as a privacy-by-design choice.

First run downloads the model (~75MB) — needs internet once, then works
fully offline after that.
"""

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path: str) -> str:
    """Must return: plain transcript text."""
    if not audio_path:
        return ""
    model = _get_model()
    segments, _ = model.transcribe(audio_path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()