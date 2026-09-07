"""
Owner: Member A
Touches: this file only, plus app/ui/pages/interview_page.py

Webcam + mic capture for a live interview session. The existing
InterviewPage already handles the webcam preview with OpenCV directly —
this module is where that gets formalized into start/stop recording
that actually saves files, plus mic audio via sounddevice.

TODO (Member A):
- start_recording(session_id): begin writing video + audio to disk
- stop_recording(): finalize files, return their paths
- Wire sounddevice (already in requirements.txt) alongside the existing
  cv2.VideoCapture loop in interview_page.py
"""
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "recordings"


class MediaCapture:
    def __init__(self, session_id: str):
        self.session_id = session_id
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def start_recording(self):
        """TODO: begin video (cv2.VideoWriter) + audio (sounddevice) capture."""
        raise NotImplementedError

    def stop_recording(self) -> dict:
        """TODO: stop capture, finalize files.
        Must return: {"video_path": str, "audio_path": str}
        This return shape is what app/core/models.InterviewSession expects.
        """
        raise NotImplementedError
