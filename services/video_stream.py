"""
MJPEG video stream generator.

Produces a multipart JPEG stream from frames provided by the
FrameCapture service, with a placeholder when no camera is available.
"""

import time
from typing import Generator

import cv2
import numpy as np

from vln_web.config import FRAME_RATE
from vln_web.services.frame_capture import FrameCapture

# Placeholder image dimensions
PLACEHOLDER_WIDTH = 640
PLACEHOLDER_HEIGHT = 480
PLACEHOLDER_TEXT = "Waiting for inference..."
PLACEHOLDER_FONT_SCALE = 1
PLACEHOLDER_COLOR = (100, 100, 100)
PLACEHOLDER_THICKNESS = 2
PLACEHOLDER_POSITION = (80, 240)


def _build_placeholder() -> bytes:
    """Create a dark placeholder JPEG with a status message."""
    image = np.zeros(
        (PLACEHOLDER_HEIGHT, PLACEHOLDER_WIDTH, 3),
        dtype=np.uint8,
    )
    cv2.putText(
        image,
        PLACEHOLDER_TEXT,
        PLACEHOLDER_POSITION,
        cv2.FONT_HERSHEY_SIMPLEX,
        PLACEHOLDER_FONT_SCALE,
        PLACEHOLDER_COLOR,
        PLACEHOLDER_THICKNESS,
    )
    _, buffer = cv2.imencode(".jpg", image)
    return buffer.tobytes()


def generate_mjpeg(
    frame_capture: FrameCapture,
) -> Generator[bytes, None, None]:
    """Yield MJPEG frames for Flask's streaming response.

    Args:
        frame_capture: The service providing camera frames.

    Yields:
        Multipart JPEG boundary + frame data.
    """
    placeholder = None
    interval = 1.0 / FRAME_RATE
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"

    while True:
        frame = frame_capture.get_latest_frame()

        if frame is None:
            if placeholder is None:
                placeholder = _build_placeholder()
            frame = placeholder

        yield boundary + frame + b"\r\n"
        time.sleep(interval)
