"""
Owner: Member A
Touches: this file only, plus app/ui/pages/interview_page.py

Webcam + mic capture for a live interview session. The existing
InterviewPage already handles the webcam preview with OpenCV directly —
this module is where that gets formalized into start/stop recording
that actually saves files, plus mic audio via sounddevice.
"""
import os
import threading

import cv2
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from pathlib import Path

from app.core.paths import get_recordings_dir

OUTPUT_DIR = get_recordings_dir()


class MediaCapture:
    def __init__(self, session_id: str, output_dir: str | None = None):
        self.session_id = session_id
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._recording = False
        self._video_frames: list = []
        self._audio_frames: list = []
        self._video_thread: threading.Thread | None = None
        self._audio_thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None
        self._sample_rate = 44100

    def start_recording(self):
        if self._recording:
            return
        self._recording = True
        self._video_frames = []
        self._audio_frames = []

        self._video_thread = threading.Thread(target=self._capture_video, daemon=True)
        self._audio_thread = threading.Thread(target=self._capture_audio, daemon=True)
        self._video_thread.start()
        self._audio_thread.start()

    def stop_recording(self) -> dict:
        if not self._recording:
            return {"video_path": None, "audio_path": None}
        self._recording = False
        if self._video_thread:
            self._video_thread.join(timeout=5)
        if self._audio_thread:
            self._audio_thread.join(timeout=5)
        if self._cap:
            self._cap.release()
            self._cap = None

        video_path = self._save_video()
        audio_path = self._save_audio()
        return {"video_path": video_path, "audio_path": audio_path}

    def _capture_video(self):
        try:
            self._cap = cv2.VideoCapture(0)
            if not self._cap.isOpened():
                return
            while self._recording:
                ret, frame = self._cap.read()
                if ret:
                    self._video_frames.append(frame)
                cv2.waitKey(33)
        except Exception:
            pass

    def _capture_audio(self):
        try:
            with sd.InputStream(
                samplerate=self._sample_rate, channels=1, dtype="int16"
            ) as stream:
                while self._recording:
                    data, _ = stream.read(1024)
                    self._audio_frames.append(data.copy())
        except Exception:
            pass

    def _save_video(self) -> str | None:
        if not self._video_frames:
            return None
        path = self.output_dir / f"{self.session_id}_video.avi"
        try:
            h, w = self._video_frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(str(path), fourcc, 30.0, (w, h))
            for frame in self._video_frames:
                writer.write(frame)
            writer.release()
            return str(path)
        except Exception:
            return None

    def _save_audio(self) -> str | None:
        if not self._audio_frames:
            return None
        path = self.output_dir / f"{self.session_id}_audio.wav"
        try:
            audio_data = np.concatenate(self._audio_frames, axis=0)
            wavfile.write(str(path), self._sample_rate, audio_data)
            return str(path)
        except Exception:
            return None
