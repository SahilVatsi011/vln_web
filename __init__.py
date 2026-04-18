"""
VLN Web UI — modular Flask application for robot navigation.

Provides a landing page and live inference dashboard with
webcam feed, real-time log streaming, and voice commands.
"""

from vln_web.app import create_app

__all__ = ["create_app"]
