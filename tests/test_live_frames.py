import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.core import db


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _initialized_db(isolated_env):
    """isolated_env repoints DB_PATH per-test; ensure schema exists there."""
    from app.core import db

    db.init_db()


@pytest.fixture
def frame_paths(tmp_path):
    final = tmp_path / "session-test.jpg"
    tmp = final.with_suffix(".tmp.jpg")
    return tmp, final


class TestSafeReplace:
    def test_renames_normally(self, frame_paths):
        from app.ui.pages.interview_page import _safe_replace

        src, dest = frame_paths
        src.write_bytes(b"frame-1")
        _safe_replace(src, dest)
        assert dest.read_bytes() == b"frame-1"
        assert not src.exists()

    def test_survives_destination_held_open(self, frame_paths):
        """Reproduces WinError 5: another handle (reader/AV) holds the dest open."""
        from app.ui.pages.interview_page import _safe_replace

        src, dest = frame_paths
        dest.write_bytes(b"stale-frame")
        src.write_bytes(b"fresh-frame")
        with open(dest, "rb") as holder:
            try:
                dest.replace(dest)  # sanity: even self-replace needs access
            except PermissionError:
                pass  # expected on Windows when locked; proves the lock exists
            # must not raise; falls back to overwrite after retries
            _safe_replace(src, dest, retries=2, delay=0.01)
        assert dest.read_bytes() == b"fresh-frame"
        assert not src.exists()

    def test_gives_up_silently_when_still_locked(self, frame_paths, monkeypatch):
        """A permanent lock must not crash the caller or corrupt the dest."""
        from app.ui.pages import interview_page

        src, dest = frame_paths
        dest.write_bytes(b"old-frame")
        src.write_bytes(b"new-frame")

        real_replace = Path.replace
        monkeypatch.setattr(
            Path,
            "replace",
            lambda self, other: real_replace(self, other),
        )

        def always_locked(self, target):
            raise PermissionError(5, "Access is denied")

        monkeypatch.setattr(Path, "replace", always_locked)

        import shutil as shutil_mod
        real_copy2 = shutil_mod.copy2

        def copy_also_fails(src_, dst_, **kw):
            raise OSError("simulated total failure")

        monkeypatch.setattr(interview_page.shutil, "copy2", copy_also_fails)

        # must swallow, never raise
        interview_page._safe_replace(src, dest, retries=1, delay=0.0)
        assert dest.read_bytes() == b"old-frame"


class TestUpdateFramePublishing:
    def _make_page(self, qapp):
        from app.ui.pages.interview_page import InterviewPage

        return InterviewPage(candidate_name="Test", job_title="QA")

    def test_publish_failure_warns_once_and_keeps_preview_alive(self, qapp, monkeypatch, caplog):
        page = self._make_page(qapp)

        class FakeCapture:
            def read(self):
                import numpy as np
                return True, np.zeros((4, 4, 3), dtype=np.uint8)

        page.capture = FakeCapture()
        page.video_label.resize(64, 48)

        calls = {"n": 0}

        def failing_write(path, frame):
            calls["n"] += 1
            return True  # imwrite succeeds; the replace below explodes

        monkeypatch.setattr("app.ui.pages.interview_page.cv2.imwrite", failing_write)

        def exploding_publish(src, dest):
            raise PermissionError(5, "Access is denied")

        monkeypatch.setattr("app.ui.pages.interview_page._safe_replace", exploding_publish)

        import logging
        with caplog.at_level(logging.WARNING, logger="app.ui.pages.interview_page"):
            for _ in range(10):  # ~10 timer ticks worth of failures
                page._update_frame()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, f"expected warn-once, got {len(warnings)}"
        assert calls["n"] == 10  # kept trying every tick, silently


class TestLiveMonitorReader:
    def test_reads_frame_without_holding_path(self, qapp, tmp_path):
        """Reader must load bytes and close the handle immediately."""
        from app.ui.pages.live_monitor_page import LiveMonitorPage

        frames_dir = db.DB_PATH.parent / "live_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame_file = frames_dir / "session-reader-test.jpg"

        import numpy as np
        import cv2
        img = np.full((32, 32, 3), 128, dtype=np.uint8)
        assert cv2.imwrite(str(frame_file), img)

        try:
            page = LiveMonitorPage()
            page.sessions_list.blockSignals(True)
            page.video_label.resize(64, 48)
            page._show_session({
                "session_id": "session-reader-test",
                "candidate_name": "Jane",
                "question": "Q?",
                "question_index": 0,
                "transcript": "hi",
            })
            assert page.video_label.pixmap() is not None
            assert not page.video_label.pixmap().isNull()
        finally:
            if "page" in locals():
                page.cleanup()
            frame_file.unlink(missing_ok=True)
