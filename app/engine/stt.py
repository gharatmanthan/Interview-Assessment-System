"""
Owner: Member B

Speech-to-text via faster-whisper, running locally on CPU (the "base"
model, int8 quantized — fast enough for a laptop, no GPU required). This
keeps candidate audio on-device rather than sending it to a cloud API,
which is worth mentioning to your guide as a privacy-by-design choice.

First run downloads the model (~75MB) — needs internet once, then works
fully offline after that.
"""

import logging
import json
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

_model = None

_TRANSCRIBE_SCRIPT = r'''
import json
import sys
from faster_whisper import WhisperModel

model = WhisperModel(
    "base", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1
)
segments, _ = model.transcribe(
    sys.argv[1], language="en", beam_size=5, vad_filter=True
)
print(json.dumps(" ".join(segment.text.strip() for segment in segments).strip()))
'''


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        try:
            _model = WhisperModel(
                "base", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1
            )
        except Exception as err:
            logger.warning("Int8 compute_type failed, falling back to float32: %s", err)
            _model = WhisperModel(
                "base", device="cpu", compute_type="float32", cpu_threads=2, num_workers=1
            )
    return _model


def transcribe(audio_path: str) -> str:
    """Must return: plain transcript text."""
    if not audio_path or not os.path.exists(audio_path):
        return ""
    try:
        child_env = os.environ.copy()
        child_env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        result = subprocess.run(
            [sys.executable, "-c", _TRANSCRIBE_SCRIPT, audio_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "Whisper process exited unexpectedly"
            raise RuntimeError(detail[-1000:])
        output = result.stdout.strip().splitlines()
        return json.loads(output[-1]) if output else ""
    except Exception as exc:
        logger.warning("Transcription failed for %s: %s", audio_path, exc)
        return ""