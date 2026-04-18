"""
Page routes — serves the HTML pages and streaming endpoints.

Handles:
    GET /           → Home / landing page
    GET /dashboard  → Live inference dashboard
    GET /video_feed → MJPEG camera stream
    GET /events     → SSE log stream
"""

from flask import Blueprint, Response, render_template

from vln_web.services.video_stream import generate_mjpeg
from vln_web.services.log_stream import generate_sse

pages_blueprint = Blueprint("pages", __name__)

# ── Frame capture instance (set by main.py at startup) ────────
_frame_capture = None


def set_frame_capture(capture) -> None:
    """Inject the FrameCapture instance for the video feed route."""
    global _frame_capture
    _frame_capture = capture


# ── Page routes ───────────────────────────────────────────────

@pages_blueprint.route("/")
def home():
    """Render the marketing / landing page."""
    return render_template("home.html")


@pages_blueprint.route("/dashboard")
def dashboard():
    """Render the live inference dashboard."""
    return render_template("dashboard.html")


# ── Streaming routes ─────────────────────────────────────────

@pages_blueprint.route("/video_feed")
def video_feed():
    """Stream MJPEG frames from the camera."""
    return Response(
        generate_mjpeg(_frame_capture),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@pages_blueprint.route("/events")
def events():
    """Stream SSE log events from the inference process."""
    return Response(
        generate_sse(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
