"""
Thread-safe camera frame capture service.

Reads frames written by the inference process to a shared JPEG file
and stores the latest frame for consumption by the video streamer.
"""

import os
import time
import threading
from typing import Optional

from vln_web.config import SHARED_FRAME_PATH, FRAME_RATE


class FrameCapture:
    """Continuously reads the latest camera frame from disk."""

    def __init__(self, frame_path: str = SHARED_FRAME_PATH):
        self._frame_path = frame_path
        self._lock = threading.Lock()
        self._latest_frame: Optional[bytes] = None

    # ── public interface ──────────────────────────────────────

    def start(self) -> None:
        """Launch the capture loop in a daemon thread."""
        thread = threading.Thread(target=self._capture_loop, daemon=True)
        thread.start()

    def get_latest_frame(self) -> Optional[bytes]:
        """Return the most recent JPEG frame, or None."""
        with self._lock:
            return self._latest_frame

    # ── internal ──────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Poll the shared frame file at the configured frame rate."""
        interval = 1.0 / FRAME_RATE

        while True:
            self._read_frame()
            time.sleep(interval)

    def _read_frame(self) -> None:
        """Read and store a single frame from the shared file."""
        try:
            if not os.path.exists(self._frame_path):
                return

            with open(self._frame_path, "rb") as file:
                data = file.read()

            if data:
                with self._lock:
                    self._latest_frame = data

        except OSError:
            # File may be mid-write by inference process — skip
            pass
